<!-- 知识缺口（对应 V2 admin-workflows.js 的 reviewPage） -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { getAdminOverview, listReviews } from '../api/endpoints'
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

// 顶部计数取自管理总览的审核模块（全量统计）
const admin = useQuery({ queryKey: ['admin', 'overview'], queryFn: getAdminOverview })
const counts = computed(() => {
  const card = admin.data.value?.modules.find((m) => m.key === 'review')
  const get = (label: string) => (card?.status === 'error' ? null : (card?.metrics.find((m) => m.label === label)?.value ?? null))
  return { pending: get('待审'), publishing: get('发布中'), approved: get('已通过'), rejected: get('已驳回') }
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
      <button class="btn soft" @click="processLive">归并待处理问题</button>
      <button class="btn primary" @click="nextReview">核对下一条</button>
    </template>

    <div class="stat-strip data-metrics">
      <VStat label="待审" :value="counts.pending" unit="条" foot="等待人工核对依据" />
      <VStat label="发布中" :value="counts.publishing" unit="条" foot="核准已保存，等待完成发布" />
      <VStat label="已通过" :value="counts.approved" unit="条" foot="审核及发布已完成" />
      <VStat label="已驳回" :value="counts.rejected" unit="条" foot="保留记录，不新增知识" />
    </div>
    <div class="wf-review-guide">
      <VPanel title="飞轮待审 · 人工审核三道关">
        <template #extra><StatusPill color="neutral">审核指引</StatusPill></template>
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
      </VPanel>
    </div>
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
              <td colspan="7"><div class="empty">尚无审核记录</div></td>
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
