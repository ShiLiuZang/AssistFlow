"""时延基准脚本能跑通（耗时缩到很小，只检查结构，不比较快慢）。"""
from scripts import latency_bench


async def test_runs_all_scenarios():
    rows = await latency_bench.run(0.002)
    assert [row[0] for row in rows] == [label for label, _ in latency_bench.SCENARIOS]
    assert all(before > 0 and after > 0 for _, before, after in rows)
