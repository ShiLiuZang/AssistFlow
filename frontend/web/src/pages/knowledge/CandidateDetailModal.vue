<!-- 候选问答详情（对应 V2 candidateDetailView），待审核时可核对后采纳或弃用 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getStaging } from '../../api/endpoints'
import RecordFields from '../../components/RecordFields.vue'
import StatusPill from '../../components/StatusPill.vue'
import { actionBusy, candidateAction } from '../../composables/useAdminActions'
import { closeModal, openModal } from '../../composables/useModal'
import CandidateDetailModal from './CandidateDetailModal.vue'
import { stamp } from './state'

const props = defineProps<{ id: number }>()
const { data: row, error, isPending, refetch } = useQuery({
  queryKey: ['kb', 'staging', props.id],
  queryFn: () => getStaging(props.id),
  gcTime: 0,
})
const labels: Record<string, string> = { kept: '待审核', extracted: '已抽取', discarded: '去重已丢弃', approved: '已采纳', rejected: '人工已弃用' }
const stateLabels: Record<string, string> = { available: '可信材料可读', missing: '材料缺失', untrusted: '来源不可信', read_error: '材料读取失败' }
const m = computed(() => row.value?.material ?? ({} as NonNullable<typeof row.value>['material']))
const conclusion = computed(() => (m.value.valid === true ? '当前校验通过' : m.value.valid === false ? '当前校验未通过' : '暂无法核对'))
const fields = computed<[string, unknown][]>(() =>
  row.value
    ? [
        ['来源标记', row.value.source_ref || '未标注'],
        ['抽取批次', row.value.batch_no || '未标注'],
        ['抽取时间', stamp(row.value.created_at)],
        ['当前状态', labels[row.value.status] || row.value.status || '未知'],
      ]
    : [],
)
const reopen = () => openModal({ title: '候选问答详情', view: CandidateDetailModal, props: { id: props.id }, cls: 'knowledge-dialog' })
const act = (action: 'approve' | 'reject') => candidateAction(props.id, action, reopen)
</script>

<template>
  <div class="modal-body">
    <div v-if="isPending" class="empty" role="status">正在读取完整内容…</div>
    <div v-else-if="error" class="data-empty-state compact">
      <h2>详情暂时无法读取</h2>
      <p>{{ error.message }}</p>
      <button class="btn" @click="refetch()">重新读取</button>
    </div>
    <template v-else-if="row">
      <div class="data-detail-meta">
        <StatusPill color="neutral">#{{ row.id }}</StatusPill>
        <StatusPill color="neutral">{{ labels[row.status] || row.status || '未知' }}</StatusPill>
        <StatusPill color="neutral">核对后操作</StatusPill>
      </div>
      <h3>{{ row.question }}</h3>
      <RecordFields :fields="fields" />
      <div class="data-candidate-evidence">
        <section class="data-full-answer">
          <div class="between">
            <h3>候选完整答案</h3>
            <span class="small muted">{{ row.answer.length }} 字</span>
          </div>
          <div class="data-detail-text">{{ row.answer }}</div>
        </section>
        <section class="data-full-answer">
          <div class="between">
            <h3>当前材料依据</h3>
            <StatusPill :color="m.status === 'available' ? '' : 'amber'">{{ stateLabels[m.status] || '未提供' }}</StatusPill>
          </div>
          <div class="data-validation" :class="{ attention: m.valid === false }">
            <strong>{{ conclusion }}</strong>
            <p>
              {{ m.reason || (m.valid === true ? '问题与答案符合现有可信来源校验。仍需人工判断适用范围与内容质量。' : '尚无可读取的可信材料。') }}
            </p>
          </div>
          <details v-if="m.text != null" class="data-source-excerpt" :open="m.valid === false">
            <summary>阅读完整材料 · {{ m.file || '未标注' }}<span>{{ m.text.length }} 字</span></summary>
            <div class="data-detail-text">{{ m.text }}</div>
          </details>
          <p v-if="m.sha256" class="field-hint section-gap">材料 SHA-256 <span class="mono">{{ m.sha256 }}</span></p>
        </section>
      </div>
      <p class="field-hint section-gap">核对使用当前材料，不代表抽取时的历史快照或人工审核结果。现有记录没有审核理由、操作人及入库知识块关联字段；这些信息保留为未提供。</p>
    </template>
  </div>
  <div class="modal-foot">
    <template v-if="row?.status === 'kept'">
      <button class="btn" @click="closeModal">关闭</button>
      <button class="btn" :disabled="actionBusy" @click="act('reject')">核对并弃用</button>
      <button class="btn primary" :disabled="actionBusy || row.material?.valid !== true" @click="act('approve')">核对并采纳</button>
    </template>
    <button v-else class="btn" @click="closeModal">知道了</button>
  </div>
</template>
