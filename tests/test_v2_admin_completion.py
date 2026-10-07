"""V2 管理接口验收：一次性内存 SQLite、临时材料、替代模型与进程。"""
import asyncio
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import review, kb, jobs, knowledge
from app.core import trusted_sources, evaluation
from app.db import knowledge_repo, review_repo, staging_repo
from app.db.models import Review, QaExtractionStaging
from app.kb.review_publish import publish_review
from tests.test_kb_read_queries import database


def client():
    app = FastAPI()
    for module in (review, kb, jobs, knowledge):
        app.include_router(module.router)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def test_review_legacy_queue_contract(monkeypatch):
    """分页和搜索 API 已删除；保留现存队列的上限、顺序、状态过滤契约。"""
    async def run():
        async with database(monkeypatch) as factory:
            async with factory() as session:
                session.add_all([Review(id=i+1, question=f"问题 {i}", suggestion="建议", status="pending" if i % 2 else "rejected") for i in range(104)])
                session.add(Review(id=105, question="50% x_y", suggestion="", answer="全文末尾依据", status="approved"))
                await session.commit()
            async with client() as api:
                legacy = (await api.get("/api/review/queue")).json()
                assert len(legacy["items"]) == 100 and "total" not in legacy
                assert [row["id"] for row in legacy["items"]] == list(range(105, 5, -1))
                pending = (await api.get("/api/review/queue", params={"status": "待审"})).json()
                assert len(pending["items"]) == 52
                assert all(row["status"] == "pending" and row["review_status"] == "待审" for row in pending["items"])
                assert (await api.get("/api/review/queue?status=invalid")).status_code == 400
    asyncio.run(run())


def test_review_approve_partial_retry_same_chunk_and_reject(monkeypatch,tmp_path):
    answer='请保留全部配件并核对商品状态。'
    (tmp_path/'returns-policy.md').write_text('# 测试材料\n'+answer,encoding='utf-8')
    monkeypatch.setattr(trusted_sources,'KB_DIR',tmp_path)
    class Index:
        fail=True
        ids=[]
        async def upsert(self,chunk):
            self.ids.append(chunk['id'])
            if self.fail:raise RuntimeError('一次性向量故障')
        async def visible(self,chunk):return True
    index=Index()
    async def publish(id):return await publish_review(id,index=index)
    monkeypatch.setattr(review,'publish_review',publish)
    async def run():
        async with database(monkeypatch) as factory:
            async with factory() as session:
                session.add_all([Review(id=1,question='退货配件要求',suggestion='未经核准'),Review(id=2,question='订单个案',suggestion='不入库')])
                await session.commit()
            async with client() as api:
                bad=await api.post('/api/review/1/approve',json={'approved_answer':'编造答案','source_ref':'returns-policy.md'})
                assert bad.status_code==422
                assert (await review_repo.get_review_detail(1))['status']=='pending'
                payload={'approved_answer':answer,'source_ref':'returns-policy.md'}
                partial=await api.post('/api/review/1/approve',json=payload)
                assert partial.status_code==202 and partial.json()['status']=='publishing'
                pending=await knowledge_repo.list_pending_chunks()
                assert len(pending)==1
                assert (await api.post('/api/review/1/reject')).status_code==409
                index.fail=False
                done=await api.post('/api/review/1/publish')
                assert done.status_code==200 and done.json()['status']=='approved'
                assert done.json()['chunk_id']==pending[0].id
                assert (await api.post('/api/review/1/publish')).status_code==200
                assert len(set(index.ids))==1 and not await knowledge_repo.list_pending_chunks()
                rejected=await api.post('/api/review/2/reject')
                assert rejected.json()['status']=='rejected'
                assert (await knowledge_repo.knowledge_stats())['total']==1
    asyncio.run(run())


def test_candidate_partial_recovery_and_kept_only(monkeypatch,tmp_path):
    answer='核对物流后由人工客服处理。'
    (tmp_path/'returns-policy.md').write_text(answer,encoding='utf-8')
    monkeypatch.setattr(trusted_sources,'KB_DIR',tmp_path)
    vector=AsyncMock(side_effect=RuntimeError('一次性嵌入故障'))
    monkeypatch.setattr(kb.dualwrite,'vectorize_pending',vector)
    async def complete():
        rows=await knowledge_repo.list_pending_chunks()
        for row in rows:await knowledge_repo.mark_chunk_vectorized(row.id,str(row.id))
        return len(rows)
    async def run():
        async with database(monkeypatch) as factory:
            async with factory() as session:
                session.add_all([QaExtractionStaging(id=i,question=f'物流核对 {i}',answer=answer,source_ref='returns-policy.md',batch_no='test',status='kept') for i in (1,2)])
                await session.commit()
            async with client() as api:
                first=await api.post('/api/kb/staging/approve',json={'ids':[1]})
                assert first.status_code==502 and (await knowledge_repo.knowledge_stats())['pending']==1
                assert (await staging_repo.list_staging_by_ids([1]))[0].status=='kept'
                vector.side_effect=complete
                done=await api.post('/api/kb/staging/approve',json={'ids':[1]})
                assert done.status_code==200 and done.json()['approved']==1
                assert (await knowledge_repo.knowledge_stats())['total']==1
                assert (await api.post('/api/kb/staging/approve',json={'ids':[1]})).status_code==409
                assert (await api.post('/api/kb/staging/reject',json={'ids':[2]})).json()['rejected']==1
    asyncio.run(run())


def test_all_registered_jobs_start_stop_and_conflicts(monkeypatch):
    start=AsyncMock();stop=AsyncMock()
    monkeypatch.setattr(jobs.jobs,'start',start);monkeypatch.setattr(jobs.jobs,'stop',stop)
    monkeypatch.setattr(jobs.jobs,'status',lambda name,with_log=False:{'name':name,'status':'stopped','log':'临时日志'})
    async def run():
        async with client() as api:
            for name in jobs.jobs.JOBS:
                assert (await api.post('/api/jobs/'+name)).status_code==200
                assert (await api.post('/api/jobs/'+name+'/stop')).status_code==200
            stop.side_effect=RuntimeError('不在运行')
            assert (await api.post('/api/jobs/kb-preview/stop')).status_code==409
            assert (await api.post('/api/jobs/unknown/stop')).status_code==404
    asyncio.run(run())
    assert start.await_count==len(jobs.jobs.JOBS)


def test_process_suggestions_uses_existing_batch_limit(monkeypatch):
    process=AsyncMock(return_value={"created":1,"merged":2,"skipped":0})
    monkeypatch.setattr(review,"process_pending",process)
    async def run():
        async with client() as api:
            assert (await api.post('/api/review/process?limit=20')).json()['created']==1
            assert (await api.post('/api/review/process?limit=21')).status_code==422
    asyncio.run(run())
    process.assert_awaited_once_with(batch_size=20)


def test_rag_lock_report_write_and_conflict(monkeypatch,tmp_path):
    monkeypatch.setattr(knowledge,'REPORT_PATH',tmp_path/'report.json')
    monkeypatch.setattr(knowledge,'EVAL_LOCK',asyncio.Lock())
    monkeypatch.setattr(knowledge,'load_cases',lambda:[{'id':'test','query':'测试问题'}])
    evaluate=AsyncMock(return_value={'generation':False,'details':[],'summary':{}})
    monkeypatch.setattr(evaluation,'evaluate',evaluate)
    async def run():
        async with client() as api:
            assert not knowledge.EVAL_LOCK.locked() and not knowledge.REPORT_PATH.exists()
            await knowledge.EVAL_LOCK.acquire()
            assert knowledge.EVAL_LOCK.locked()
            assert (await api.post('/api/knowledge/evaluate',json={})).status_code==409
            knowledge.EVAL_LOCK.release()
            done=await api.post('/api/knowledge/evaluate',json={'top_k':5,'generate':False})
            assert done.status_code==200 and done.json()['dataset'][0]['id']=='test'
            assert knowledge.REPORT_PATH.stat().st_mtime > 0
            assert not knowledge.EVAL_LOCK.locked()
            assert (await api.get('/api/rag-eval/report')).json()==done.json()
    asyncio.run(run())
    evaluate.assert_awaited_once()
