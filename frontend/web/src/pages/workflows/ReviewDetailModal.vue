<!-- 审核依据与处理结果（对应 V2 reviewBody / reviewFooter） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { getMaterial, getReview } from '../../api/endpoints'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { actionBusy, reviewAction } from '../../composables/useAdminActions'
import { closeModal, openModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import ReviewDetailModal from './ReviewDetailModal.vue'
import { materialNames, reviewColor, reviewDraft, reviewLabels, sourceLabels, stamp } from './shared'

const props = defineProps<{ id: number; preserve?: boolean }>()
const router = useRouter()
const { data: row, error, isPending, refetch } = useQuery({ queryKey: ['review', 'item', props.id], queryFn: () => getReview(props.id), gcTime: 0 })

watch(
  row,
  (r) => {
    if (!r) return
    if (!props.preserve || reviewDraft.id !== props.id) {
      reviewDraft.answer = r.answer || ''
      reviewDraft.source = r.source_ref || ''
    }
    reviewDraft.id = props.id
  },
  { immediate: true },
)

const material = useQuery({
  queryKey: computed(() => ['review', 'material', reviewDraft.source]),
  queryFn: () => getMaterial(reviewDraft.source),
  enabled: computed(() => row.value?.status === 'pending' && !!reviewDraft.source),
})

const steps = computed(() => {
  const r = row.value
  if (!r) return []
  const checked = r.status === 'publishing' || r.status === 'approved'
  return [
    ['问题已归并', true],
    [r.status === 'rejected' ? '审核已驳回' : checked ? '人工核准已保存' : '待人工核准', checked || r.status === 'rejected'],
    [r.status === 'rejected' ? '不发布知识' : r.status === 'approved' ? '知识发布已完成' : '待完成发布', r.status === 'approved'],
  ] as [string, boolean][]
})

// 快照里存的是精排分 rerank_score（app/core/confidence.py），旧数据兼容 score
const scoreText = (v?: number | null) => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(3) : '—')
const reopen = () => openModal({ title: '审核依据与处理结果', view: ReviewDetailModal, props: { id: props.id, preserve: true }, cls: 'workflow-dialog' })
const approve = () => reviewAction(props.id, 'approve', reviewDraft.answer, reviewDraft.source, reopen)
const reject = () => reviewAction(props.id, 'reject', reviewDraft.answer, reviewDraft.source, reopen)
const publish = () => reviewAction(props.id, 'publish', reviewDraft.answer, reviewDraft.source, reopen)
function publicationJobs() {
  closeModal()
  router.push('/jobs?group=知识处理')
  toast('审核发布仍需在审核详情重试；作业结果需单独核对')
}
function toKnowledge() {
  closeModal()
  router.push('/knowledge')
}
</script>

<template>
  <div class="modal-body">
    <div v-if="isPending" class="empty" role="status">正在读取完整审核记录…</div>
    <div v-else-if="error" class="notice" role="alert">{{ error.message }}</div>
    <template v-else-if="row">
      <div class="workflow-detail-top">
        <div>
          <span class="mono muted">#{{ row.id }}</span>
          <h3>{{ row.question || row.normalized_question }}</h3>
        </div>
        <StatusPill :color="reviewColor(row.status)">{{ reviewLabels[row.status] || row.status || '未知' }}</StatusPill>
      </div>
      <ol class="workflow-steps">
        <li v-for="[label, done] in steps" :key="label" :class="{ done }"><Icon :name="done ? 'check' : 'clock'" /><span>{{ label }}</span></li>
      </ol>
      <div v-if="row.status === 'publishing'" class="notice workflow-notice">
        审核记录已保存，发布尚未完成。<template v-if="row.publish_error">发布异常：{{ row.publish_error }}。</template>修复依赖后可重试发布，无需重新审核。
      </div>
      <div v-if="row.status === 'rejected'" class="notice workflow-notice">这条记录已驳回，保留审核记录，不新增通用知识。</div>
      <div class="workflow-detail-grid">
        <section>
          <div class="workflow-section-title">
            <h3>原始问题与检索依据</h3>
            <span class="small muted">归并 {{ row.occurrence_count ?? '—' }} 次</span>
          </div>
          <article v-for="(raw, index) in row.raws ?? []" :key="index" class="workflow-evidence">
            <div class="between">
              <strong>原始提问 {{ index + 1 }}</strong>
              <StatusPill color="neutral">{{ (raw.source && sourceLabels[raw.source]) || raw.source || '来源未标注' }}</StatusPill>
            </div>
            <p class="workflow-quote">{{ raw.raw_question }}</p>
            <div class="small muted">{{ raw.reason || '未提供原因' }} · {{ stamp(raw.created_at) }}</div>
            <details class="workflow-snapshot">
              <summary>当时检索快照 {{ Array.isArray(raw.retrieved_chunks) ? `· ${raw.retrieved_chunks.length} 条` : '· 未记录' }}</summary>
              <p v-if="raw.retrieved_chunks == null" class="muted">未记录快照，无法据此判断当时检索结果。</p>
              <p v-else-if="!raw.retrieved_chunks.length" class="muted">快照为空，当时没有保留命中的知识块。</p>
              <div v-for="(chunk, i) in raw.retrieved_chunks ?? []" v-else :key="i" class="workflow-hit">
                <strong>{{ chunk.question || chunk.section_path || '未标注问法' }}</strong>
                <p>{{ chunk.answer || '未提供内容' }}</p>
                <span class="small muted">精排分 {{ scoreText(chunk.rerank_score ?? chunk.score) }}<template v-if="chunk.question && chunk.section_path"> · {{ chunk.section_path }}</template></span>
              </div>
            </details>
          </article>
          <div v-if="!row.raws?.length" class="empty">未提供原始问题与检索快照</div>
        </section>
        <section>
          <h3 class="workflow-section-title">答案与可信材料</h3>
          <div class="workflow-suggestion">
            <span class="small muted">AI 建议 · 尚不能作为核准依据</span>
            <p>{{ row.suggestion || row.ai_suggested_answer || '尚无 AI 建议' }}</p>
          </div>
          <form v-if="row.status === 'pending'" id="wf-review-form" @submit.prevent="approve">
            <label class="field"
              >人工确认答案<textarea id="wf-answer" v-model="reviewDraft.answer" required maxlength="4000" placeholder="核对可信材料后填写答案"></textarea
            ></label>
            <label class="field"
              >可信材料<select id="wf-source" v-model="reviewDraft.source" required>
                <option value="">请选择材料</option>
                <option v-for="name in materialNames" :key="name" :value="name">{{ name }}</option>
              </select></label
            >
            <div id="wf-material-evidence">
              <p v-if="!reviewDraft.source" class="field-hint">选择材料后读取完整可信原文。</p>
              <p v-else-if="material.isPending.value" role="status">正在读取可信材料…</p>
              <p v-else-if="material.error.value" role="alert">{{ material.error.value.message }}；核准前需重新核对材料。</p>
              <template v-else-if="material.data.value">
                <details class="data-source-excerpt" open>
                  <summary>完整可信材料 · {{ material.data.value.file }}</summary>
                  <div class="data-detail-text">{{ material.data.value.text }}</div>
                </details>
                <p class="field-hint section-gap">材料 SHA-256 <span class="mono">{{ material.data.value.sha256 }}</span></p>
              </template>
            </div>
            <p class="field-hint">核准答案必须取自可信材料的连续原文；核对后才提交，后端仍会再次校验。</p>
            <div id="wf-review-error" role="alert" class="workflow-form-error"></div>
          </form>
          <div v-else class="workflow-confirmed">
            <span class="small muted">人工确认答案</span>
            <p>{{ row.answer || '没有已核准答案' }}</p>
            <dl class="workflow-meta">
              <dt>可信材料</dt>
              <dd>{{ row.source_ref || '未提供' }}</dd>
              <dt>审核人</dt>
              <dd>{{ row.reviewer || '—' }}</dd>
              <dt>审核时间</dt>
              <dd>{{ stamp(row.reviewed_at) }}</dd>
            </dl>
          </div>
        </section>
      </div>
    </template>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">关闭</button>
    <button v-if="error" class="btn primary" @click="refetch()">重新读取</button>
    <template v-else-if="row?.status === 'pending'">
      <button class="btn" :disabled="actionBusy" @click="reject">核对并驳回</button>
      <button class="btn primary" type="submit" form="wf-review-form" :disabled="actionBusy">核对并发布</button>
    </template>
    <template v-else-if="row?.status === 'publishing'">
      <button class="btn soft" @click="publicationJobs">查看作业中心</button>
      <button class="btn primary" :disabled="actionBusy" @click="publish">核对并重试发布</button>
    </template>
    <button v-else-if="row?.status === 'approved'" class="btn primary" @click="toKnowledge">查看知识库存</button>
  </div>
</template>
