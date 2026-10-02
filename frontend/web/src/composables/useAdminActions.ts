// 写操作的统一确认流程（对应 V2 admin-actions.js）：
// 先重新读取对象最新状态 → 弹窗列出对象、范围和影响 → 勾选确认后提交 → 显示真实结果。
// 超时或 5xx 视为"结果待核对"，提示先查询再决定，不自动重试。
import { reactive, ref } from 'vue'
import { request } from '../api/client'
import type { Job, ReviewItem, StagingDetail } from '../api/types'
import { queryClient } from '../queryClient'
import ActionModal from '../components/ActionModal.vue'
import { closeModal, modalState, openModal } from './useModal'

export interface ActionSpec {
  title: string
  button?: string
  path: string
  data?: unknown
  timeout?: number
  fields?: [string, unknown][]
  fulls?: [string, string][]
  intro?: string
  notice?: string
  valid: (data: any, status: number) => boolean
  result: (data: any, status: number) => string
  reopen?: () => void
}

export const actionBusy = ref(false)
export const actionNotice = ref('')
export const actionState = reactive<{
  phase: 'loading' | 'confirm' | 'error' | 'running' | 'result'
  spec: ActionSpec | null
  message: string
  uncertain: boolean
  token: number
}>({ phase: 'loading', spec: null, message: '', uncertain: false, token: 0 })

const stillOpen = (token: number) => token === actionState.token && modalState.open && modalState.view === ActionModal

function show(title: string) {
  if (modalState.open && modalState.view === ActionModal) modalState.title = title
  else openModal({ title, view: ActionModal, cls: 'knowledge-dialog' })
}

export async function prepare(build: () => Promise<ActionSpec>) {
  if (actionBusy.value) return
  const token = ++actionState.token
  actionState.phase = 'loading'
  actionState.spec = null
  actionBusy.value = true
  show('核对操作范围')
  try {
    const spec = await build()
    if (!stillOpen(token)) return
    actionState.spec = spec
    actionState.phase = 'confirm'
    show(spec.title)
  } catch (error) {
    if (!stillOpen(token)) return
    actionState.message = error instanceof Error ? error.message : String(error)
    actionState.phase = 'error'
    show('暂不能执行')
  } finally {
    actionBusy.value = false
  }
}

export async function execute() {
  const spec = actionState.spec
  if (!spec || actionState.phase !== 'confirm' || actionBusy.value) return
  const token = actionState.token
  actionBusy.value = true
  actionNotice.value = `${spec.title}：请求正在执行，关闭弹窗不会停止后台操作。`
  actionState.phase = 'running'
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), spec.timeout ?? 60000)
  let message = ''
  let uncertain = false
  try {
    const response = await fetch(spec.path, {
      method: 'POST',
      signal: controller.signal,
      headers: { Accept: 'application/json', ...(spec.data !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      ...(spec.data !== undefined ? { body: JSON.stringify(spec.data) } : {}),
    })
    let data: any
    try {
      data = await response.json()
    } catch {
      throw new Error('服务没有返回完整结果。')
    }
    if (!response.ok)
      throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : `请求未完成（HTTP ${response.status}）。`), {
        uncertain: response.status >= 500,
        status: response.status,
      })
    if (!spec.valid(data, response.status)) throw new Error('返回结果不完整，需要查询真实状态。')
    message = spec.result(data, response.status)
  } catch (error: any) {
    uncertain = error.uncertain !== false
    message =
      (error.name === 'AbortError' ? '请求超时，结果待核对。' : error.message) +
      (error.status === 409
        ? ' 状态已变化，请重新读取对象。'
        : uncertain
          ? ' 可能已完成部分步骤；请先查询库存、记录或作业状态，勿直接重复提交。'
          : ' 请修正输入或重新核对条件。')
  } finally {
    clearTimeout(timer)
    actionBusy.value = false
    actionNotice.value = `${spec.title}：${message}`
    queryClient.invalidateQueries()
  }
  if (stillOpen(token)) {
    actionState.message = message
    actionState.uncertain = uncertain
    actionState.phase = 'result'
    show(uncertain ? '结果待核对' : '操作结果')
  }
}

export function cancelOrReopen() {
  const reopen = actionState.spec?.reopen
  actionState.token++
  if (reopen) reopen()
  else closeModal()
}

const statusNames: Record<string, string> = {
  pending: '待审',
  publishing: '发布中',
  approved: '已通过',
  rejected: '已驳回',
  idle: '本次未运行',
  running: '运行中',
  ok: '进程执行完成',
  failed: '进程执行失败',
  stopped: '已停止',
}

/* ---------- 候选问答：采纳 / 弃用 ---------- */
export function candidateAction(id: number, action: 'approve' | 'reject', reopen?: () => void) {
  return prepare(async () => {
    const fresh = await request<StagingDetail>(`/api/kb/staging/${id}`)
    if (fresh.status !== 'kept') throw new Error('候选已不在待审状态，请重新查看。')
    if (action === 'approve' && fresh.material?.valid !== true) throw new Error('当前材料校验未通过，不能采纳。')
    const approved = action === 'approve'
    return {
      title: approved ? '采纳候选问答' : '弃用候选问答',
      button: approved ? '确认采纳' : '确认弃用',
      path: `/api/kb/staging/${action}`,
      data: { ids: [fresh.id] },
      fields: [
        ['候选 ID', `#${fresh.id}`],
        ['可信材料', fresh.source_ref],
      ],
      fulls: [
        ['问题', fresh.question],
        ['完整答案', fresh.answer],
      ],
      notice: approved
        ? '将保存此问答，并调用现有全库 pending 向量补齐（包含历史待补原文），会使用嵌入服务；全部完成后才标为已采纳。失败可能保留待补块。'
        : '保留候选记录并标为弃用，不新增知识，不调用模型。',
      valid: (d) =>
        approved
          ? d.approved === 1 && Array.isArray(d.chunk_ids) && d.chunk_ids.length === 1 && d.chunk_ids.every(Number.isInteger)
          : d.rejected === 1,
      result: (d) =>
        approved ? `已采纳 1 条，返回知识块 ID：${d.chunk_ids.join('、')}。请核对候选状态和库存。` : '已弃用 1 条，原记录保留。',
      reopen,
    }
  })
}

/* ---------- 知识缺口：核准发布 / 驳回 / 重试发布 ---------- */
export function reviewAction(
  id: number,
  action: 'approve' | 'reject' | 'publish',
  answer: string,
  source: string,
  reopen?: () => void,
) {
  return prepare(async () => {
    const row = await request<ReviewItem & { source_digest?: string }>(`/api/review/${id}`)
    if (action === 'publish' ? row.status !== 'publishing' : row.status !== 'pending') throw new Error('审核状态已变化，请重新查看记录。')
    let material: { text: string; sha256: string } | undefined
    if (action === 'approve') {
      if (!answer.trim() || !source) throw new Error('请填写人工确认答案并选择可信材料。')
      material = await request(`/api/review/materials/${encodeURIComponent(source)}`)
      if (!material!.text.includes(answer.trim())) throw new Error('核准答案必须是可信材料中的连续原文，请返回修改。')
    }
    const labels = { approve: '核准并发布', reject: '驳回审核', publish: '重试发布' }
    return {
      title: labels[action],
      path: `/api/review/${id}/${action}`,
      data: action === 'approve' ? { approved_answer: answer.trim(), source_ref: source } : undefined,
      timeout: 120000,
      fields: [
        ['审核 ID', `#${id}`],
        ['当前状态', statusNames[row.status] ?? '未知'],
        ['可信材料', source || row.source_ref],
        ['材料指纹', material?.sha256 || row.source_digest],
      ],
      fulls: [
        ['标准问题', row.question],
        ['人工确认答案', action === 'approve' ? answer.trim() : row.answer || '未核准'],
      ],
      notice:
        action === 'reject'
          ? '保留审核记录，标为驳回，不新增知识。'
          : '将复用现有定向发布流程，保存核准结果、写知识块并调用嵌入服务。返回 202 表示发布尚未完成，需核对后重试；不会重新核准。',
      valid: (d, status) =>
        d.id === id &&
        ['publishing', 'approved', 'rejected'].includes(d.status) &&
        (status === 202 ? d.status === 'publishing' : action === 'reject' ? d.status === 'rejected' : d.status === 'approved'),
      result: (d, status) =>
        status === 202
          ? '核准记录已保存，发布尚未完成。请查看当前状态与发布异常，修复依赖后人工重试。'
          : d.status === 'rejected'
            ? '已驳回，未新增知识。'
            : `审核与发布已完成。${d.chunk_id ? `知识块 #${d.chunk_id}。` : ''}`,
      reopen,
    }
  })
}

/* ---------- 作业：启动 / 停止 ---------- */
export const jobEffects: Record<string, string> = {
  'kb-preview': '读取现有材料并输出切块预览日志，不写知识库、不调用模型。',
  'kb-build': '读取现有材料并写入 MySQL pending 原文，之后另行补齐向量。',
  'kb-vectorize': '处理启动时全库 pending 原文，调用嵌入服务并写入 Milvus。',
  'finetune-golden': '调用聊天模型核对黄金样例，并更新校验报告。',
  'finetune-corpus': '从现有数据构建语料，调用聊天模型并更新语料产物。',
  'finetune-dataset': '划分、增强数据集，调用聊天模型并更新数据集文件。',
  'finetune-train': '训练分类器，消耗本机计算资源并更新模型产物。',
  'finetune-eval': '读取已有权重与测试集，更新测试集评测报告。',
  'finetune-export': '读取已有权重并更新 ONNX 导出产物和对齐报告。',
  'finetune-threshold-scan': '使用验证集与分类服务更新扫描报告，按现有脚本执行。',
  'classifier-up': '启动本地分类服务，进程持续运行，直至停止。',
  'classify-pool': '分类现有问题池并写入归类结果。',
  'classify-pool-force': '强制处理不足一批的问题池，写入归类结果。',
  'classify-history': '分类历史用户提问，写入现有隔离结果库，不改业务表。',
}

export function jobAction(name: string, stop: boolean, reopen?: () => void) {
  return prepare(async () => {
    if (!Object.hasOwn(jobEffects, name)) throw new Error('此作业没有登记操作范围。')
    const row = await request<Job>(`/api/jobs/${encodeURIComponent(name)}`)
    if (row.name !== name || !['idle', 'running', 'ok', 'failed', 'stopped'].includes(row.status)) throw new Error('作业状态暂无法确认。')
    if (stop ? row.status !== 'running' : row.status === 'running')
      throw new Error(stop ? '此作业已经不在运行。' : '同一作业正在运行，请查看日志。')
    if (!stop && name === 'kb-vectorize') {
      const kb = await request<any>('/api/kb/overview')
      if (kb.db_error || !Number.isInteger(kb.chunks?.pending) || kb.chunks.pending < 1 || kb.milvus?.online !== true)
        throw new Error('当前没有可补齐原文，或原文/向量服务不可用。请先核对索引状态。')
    }
    return {
      title: stop ? '停止作业' : '启动作业',
      path: `/api/jobs/${name}${stop ? '/stop' : ''}`,
      timeout: 30000,
      fields: [
        ['作业', row.title],
        ['登记名称', name],
        ['当前状态', statusNames[row.status] ?? '未知'],
        ['执行条件', row.needs],
        ['开始时间', row.started_at],
      ],
      notice: stop
        ? '将终止当前作业及其子进程。已经完成的数据库写入、文件产物不会撤回，停止后需核对部分结果。'
        : `${jobEffects[name]} 本次日志将按现有运行器重建；请确认依赖、材料和运行资源已就绪。`,
      valid: (d) => d.name === name && ['running', 'ok', 'failed', 'stopped'].includes(d.status) && (!stop || ['stopped', 'ok', 'failed'].includes(d.status)),
      result: (d) =>
        `后端当前状态：${({ running: '运行中', ok: '进程执行完成', failed: '进程执行失败', stopped: '已停止' } as Record<string, string>)[d.status]}。请查看日志，再到业务页核对结果。`,
      reopen,
    }
  })
}

/* ---------- RAG 评估 ---------- */
export function evaluationAction(topK: number, generate: boolean, reopen?: () => void) {
  return prepare(async () => {
    const state = await request<{ running: boolean }>('/api/knowledge/evaluation-state')
    const cases = await request<{ cases: unknown[] }>('/api/knowledge/cases')
    if (state.running) throw new Error('已有评估正在运行，请先查看状态。')
    if (!Array.isArray(cases.cases) || !cases.cases.length) throw new Error('固定题集为空或不可读取。')
    if (!Number.isInteger(topK) || topK < 1 || topK > 50) throw new Error('top_k 需为 1–50 的整数。')
    return {
      title: '运行 RAG 评估',
      path: '/api/knowledge/evaluate',
      data: { top_k: topK, generate },
      timeout: 610000,
      fields: [
        ['当前固定题集', `${cases.cases.length} 题`],
        ['每题检索 top_k', topK],
        ['生成回答', generate ? '启用' : '关闭'],
      ],
      notice: `执行现有四策略评估并更新 RAG 报告，最长约 10 分钟。检索可能使用嵌入和重排服务；${
        generate ? '同时调用聊天模型生成回答。' : '仅评估检索，不生成回答。'
      }失败保留旧报告，页面不会将旧报告标为本次成功。`,
      valid: (d) => typeof d.created_at === 'string' && Array.isArray(d.dataset) && Array.isArray(d.details) && d.generation === generate,
      result: (d) => `本次评估已返回并保存报告，时间：${d.created_at}。请核对逐题结果与失败调用。`,
      reopen,
    }
  })
}

/* ---------- 飞轮：生成待审建议 ---------- */
export function processReviewsAction(reopen?: () => void) {
  return prepare(async () => ({
    title: '生成待审建议',
    path: '/api/review/process?limit=20',
    timeout: 180000,
    intro: '按现有处理器读取最多 20 条尚未归并的问题，检索知识并调用聊天模型生成建议，写入待审队列。不会自动核准或发布知识。',
    notice: '已有归并、隐私与来源约束继续由后端执行；生成建议仍需人工核对。',
    valid: (d) => ['created', 'merged', 'skipped'].every((key) => Number.isInteger(d[key]) && d[key] >= 0),
    result: (d) => `新增待审 ${d.created} 条，归并 ${d.merged} 条，跳过 ${d.skipped} 条。请查询当前队列。`,
    reopen,
  }))
}
