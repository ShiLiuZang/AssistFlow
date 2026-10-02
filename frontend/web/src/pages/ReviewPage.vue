<!-- 知识缺口（对应 V2 admin-workflows.js 的 reviewPage） -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { listReviews } from '../api/endpoints'
import { get } from '../api/client'
import DataPage from '../components/DataPage.vue'
import DataState from '../components/DataState.vue'
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import VPanel from '../components/VPanel.vue'
import VStat from '../components/VStat.vue'
import { processReviewsAction } from '../composables/useAdminActions'
import { reportDataTime } from '../composables/useDataTime'
import { closeModal, openModal } from '../composables/useModal'
import { toast } from '../composables/useToast'
import { useUrlNumber, useUrlState } from '../composables/useUrlState'
import ReviewDetailModal from './workflows/ReviewDetailModal.vue'
import { listStamp, reviewApiStatus, reviewColor, reviewLabels } from './workflows/shared'

const router = useRouter()
const pipeline = useQuery({ queryKey: ['review', 'stats'], queryFn: () => get<{ saved_turns: number; pool_total: number; unmerged: number; reviews: Record<string, number> }>('/api/review/stats') })
const filter = useUrlState('status', 'pending')
const query = useUrlState('q', '')
const page = useUrlNumber('page', 1)
const size = useUrlNumber('size', 20)
const draft = ref(query.value)
watch(query, (v) => (draft.value = v))

const params = computed(() => ({
  page: page.value,
  size: size.value,
  q: query.value,
  status: filter.value === 'all' ? undefined : reviewApiStatus[filter.value],
}))
const list = useQuery({
  queryKey: computed(() => ['review', 'list', params.value]),
  queryFn: () => listReviews(params.value),
  placeholderData: keepPreviousData,
})
watch(list.dataUpdatedAt, reportDataTime, { immediate: true })

// 与问题池进度共用全量统计，不依赖当前列表的筛选条件。
const counts = computed(() => {
  const stats = pipeline.data.value
  const get = (status: string) => stats ? stats.reviews[status] ?? 0 : null
  return { pending: get('pending'), publishing: get('publishing'), approved: get('approved'), rejected: get('rejected') }
})

function setFilter(key: string) {
  filter.value = key
  page.value = 1
}
function setSize(v: string) {
  size.value = Number(v)
  page.value = 1
}
function submit() {
  query.value = draft.value.trim()
  page.value = 1
}
const gates = [
  ['01', '垃圾过滤', '乱输入、测试或不当言论', '驳回无知识价值的内容'],
  ['02', '时效', '活动截止、单笔订单进度', '不沉淀易过期或仅适用当次的事实'],
  ['03', '频次', '低频冷门、重复已有知识', '先判断是否值得沉淀，再核对通用答案'],
]
// 与原飞轮待审页一致：归并 3 次及以上的问题标为高频，提示优先处理
const hot = (row: { occurrence_count?: number | null }) => (row.occurrence_count ?? 0) >= 3
const openReview = (id: number) => openModal({ title: '审核依据与处理结果', view: ReviewDetailModal, props: { id }, cls: 'workflow-dialog' })

async function nextReview() {
  try {
    const value = await listReviews({ status: '待审', page: 1, size: 1 })
    const row = value.items?.[0]
    if (row) openReview(row.id)
    else toast('当前没有可读取的待审记录')
  } catch (error: any) {
    toast(error.message)
  }
}
const processLive = () =>
  processReviewsAction(() => {
    closeModal()
    router.push('/review')
  })
</script>

<template>
  <DataPage page="review">
    <template #actions>
      <button class="btn soft" :disabled="!pipeline.data.value?.unmerged" @click="processLive">归并待处理问题<span v-if="pipeline.data.value?.unmerged"> · {{ pipeline.data.value.unmerged }}</span></button>
      <button class="btn primary" @click="nextReview">核对下一条</button>
    </template>

    <div class="stat-strip data-metrics">
      <VStat label="待审" :value="counts.pending" unit="条" foot="等待人工核对依据" />
      <VStat label="发布中" :value="counts.publishing" unit="条" foot="核准已保存，等待完成发布" />
      <VStat label="已通过" :value="counts.approved" unit="条" foot="审核及发布已完成" />
      <VStat label="已驳回" :value="counts.rejected" unit="条" foot="保留记录，不新增知识" />
    </div>
    <div v-if="pipeline.data.value" class="review-pipeline">
      <span>对话快照 <strong>{{ pipeline.data.value.saved_turns }}</strong></span><span>→ 问题池 <strong>{{ pipeline.data.value.pool_total }}</strong></span><span>→ 待归并 <strong>{{ pipeline.data.value.unmerged }}</strong></span><span>→ 人工审核</span>
      <RouterLink class="text-button" to="/client">进入真实聊天 →</RouterLink>
    </div>
    <p v-if="pipeline.error.value" class="notice amber">问题池统计读取失败，可刷新重试。</p>
    <details class="wf-review-guide compact-guide">
        <summary><strong>人工审核三道关</strong>垃圾过滤 → 时效 → 频次 · 展开指引</summary>
        <div class="wf-review-gates">
          <article v-for="[no, title, detail, tip] in gates" :key="no">
            <span class="wf-gate-no">{{ no }}</span>
            <h3>{{ title }}</h3>
            <p>{{ detail }}</p>
            <small>{{ tip }}</small>
          </article>
        </div>
        <p class="field-hint panel-pad wf-review-guide-note">
          这是人工审核提示。剩余问题需核对可信依据、适用范围和完整答案，确认后再发布；提示不代表后端已自动执行这三项筛选。
        </p>
    </details>
    <div class="workflow-scope">
      <span><Icon name="info" />知识缺口来自未解决的问题；候选问答是另一条材料审核队列。</span>
      <button class="text-button" @click="router.push('/knowledge?tab=mining')">查看候选问答 <Icon name="arrow" /></button>
    </div>

    <DataState v-if="!list.data.value" :loading="list.isPending.value" :error="list.error.value" />
    <VPanel v-else title="完整审核队列">
      <template #extra><StatusPill color="neutral">核对后操作</StatusPill></template>
      <div class="panel-toolbar data-toolbar">
        <div class="data-filters">
          <button
            v-for="(label, key) in { all: '全部', ...reviewLabels }"
            :key="key"
            class="filter-chip"
            :class="{ active: filter === key }"
            :aria-pressed="filter === key"
            @click="setFilter(String(key))"
          >
            {{ label }}
          </button>
        </div>
        <form id="wf-queue-form" class="data-table-tools" @submit.prevent="submit">
          <label class="search"><input id="wf-review-query" v-model="draft" aria-label="搜索完整审核队列" placeholder="搜索问题、答案或材料" maxlength="200" autocomplete="off" /></label>
          <button class="btn" type="submit">搜索</button>
        </form>
      </div>
      <div class="table-wrap">
        <table class="workflow-review-table">
          <thead>
            <tr>
              <th v-for="h in ['标准问题', '归并频次', '状态', '可信材料', '创建时间', '审核人', '操作']" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody id="wf-review-rows">
            <tr v-for="row in list.data.value.items" :key="row.id">
              <td class="data-content-cell">
                <strong>{{ row.question }}</strong
                ><span class="table-sub wf-suggestion-preview" :title="row.suggestion || undefined">{{ row.suggestion ? `AI 建议：${row.suggestion}` : '尚无 AI 建议' }}</span
                ><span class="table-sub">#{{ row.id }} · 需人工核对</span>
              </td>
              <td :title="hot(row) ? '归并次数多，建议优先补充知识' : undefined">
                <StatusPill v-if="hot(row)" color="amber">{{ row.occurrence_count }} 次 · 高频</StatusPill><template v-else>{{ row.occurrence_count ?? '—' }} 次</template>
              </td>
              <td><StatusPill :color="reviewColor(row.status)">{{ reviewLabels[row.status] || row.status || '未知' }}</StatusPill></td>
              <td>{{ row.source_ref || '待核对可信材料' }}</td>
              <td class="data-time-cell">{{ listStamp(row.created_at) }}</td>
              <td>{{ row.reviewer || '—' }}</td>
              <td>
                <button class="table-actions" @click="openReview(row.id)">{{ row.status === 'pending' ? '查看与核对' : '查看结果' }} <Icon name="arrow" /></button>
              </td>
            </tr>
            <tr v-if="!list.data.value.items.length">
              <td colspan="7"><div class="empty">
                <strong>当前筛选下没有审核记录</strong>
                <p v-if="pipeline.data.value?.unmerged">问题池有 {{ pipeline.data.value.unmerged }} 条尚未归并，可点击上方“归并待处理问题”。</p>
                <p v-else-if="pipeline.data.value?.pool_total === 0">尚未采集到低置信度或负反馈问题。真实聊天中的拒答、低置信度或“未解决”反馈会先进入问题池。</p>
                <p v-else>可切换“全部”查看历史审核记录，或等待新的未解决问题。</p>
              </div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="data-table-footer">
        <span
          >筛选结果 {{ list.data.value.total }} 条 · 第 {{ list.data.value.page }} / {{ list.data.value.pages }} 页<br />顶部计数为全量统计，搜索覆盖完整队列。</span
        >
        <div class="data-table-tools">
          <select id="wf-review-size" aria-label="审核每页条数" :value="size" @change="setSize(($event.target as HTMLSelectElement).value)">
            <option v-for="n in [10, 20, 50]" :key="n" :value="n">{{ n }}</option>
          </select>
          <button class="btn" :disabled="list.data.value.page <= 1" @click="page = list.data.value!.page - 1">上一页</button>
          <button class="btn" :disabled="list.data.value.page >= list.data.value.pages" @click="page = list.data.value!.page + 1">下一页</button>
        </div>
      </div>
    </VPanel>
  </DataPage>
</template>
