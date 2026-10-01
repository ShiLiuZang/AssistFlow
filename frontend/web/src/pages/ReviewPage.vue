<!-- 知识缺口（飞轮待审）：低置信度问题归并成待审项，人工核对材料后发布进知识库 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  approveReview,
  getKbOverview,
  getMaterial,
  getReview,
  listReviews,
  processReviews,
  rejectReview,
  retryPublish,
} from '../api/endpoints'
import AppDialog from '../components/AppDialog.vue'
import PageHeader from '../components/PageHeader.vue'
import Pager from '../components/Pager.vue'
import Panel from '../components/Panel.vue'
import Pill from '../components/Pill.vue'
import StateBlock from '../components/StateBlock.vue'
import { confirm } from '../composables/useConfirm'
import { useUrlNumber, useUrlState } from '../composables/useUrlState'
import { errorText, toast } from '../composables/useToast'
import { reviewStatus } from '../utils/labels'
import { dateTime, DASH } from '../utils/format'

const client = useQueryClient()
// 后端按中文状态名筛选
const filters: [string, string][] = [
  ['', '全部'],
  ['待审', '待审'],
  ['发布中', '发布中'],
  ['通过', '已通过'],
  ['驳回', '已驳回'],
]
const status = useUrlState('status', '待审')
const q = useUrlState('q', '')
const page = useUrlNumber('page', 1)
const draft = ref(q.value)
watch(q, (v) => (draft.value = v))
function submitSearch() {
  q.value = draft.value.trim()
  page.value = 1
}

const params = computed(() => ({ status: status.value === 'all' ? '' : status.value, page: page.value, size: 20, q: q.value }))
const list = useQuery({
  queryKey: computed(() => ['review', 'list', params.value]),
  queryFn: () => listReviews(params.value),
  placeholderData: keepPreviousData,
})
function setStatus(value: string) {
  status.value = value === '' ? 'all' : value
  page.value = 1
}
const activeStatus = computed(() => (status.value === 'all' ? '' : status.value))

const invalidate = () => client.invalidateQueries({ queryKey: ['review'] })

/* 归并待处理问题 */
const processMut = useMutation({
  mutationFn: () => processReviews(20),
  onSuccess: (d) => {
    toast(`新增待审 ${d.created} 条，归并 ${d.merged} 条，跳过 ${d.skipped} 条`)
    invalidate()
  },
  onError: (err) => toast(errorText(err), 'error'),
})
async function runProcess() {
  const ok = await confirm({
    title: '归并待处理问题',
    body: '从低置信度问题池取最多 20 条，用模型标准化问法并归并到待审队列。会调用付费聊天模型。',
    confirmText: '开始归并',
  })
  if (ok) processMut.mutate()
}

/* 审核详情 */
const openId = ref<number | null>(null)
const dialogOpen = computed({
  get: () => openId.value !== null,
  set: (v: boolean) => {
    if (!v) openId.value = null
  },
})
const detail = useQuery({
  queryKey: computed(() => ['review', 'item', openId.value]),
  queryFn: () => getReview(openId.value as number),
  enabled: computed(() => openId.value !== null),
})
const kb = useQuery({ queryKey: ['kb', 'overview'], queryFn: getKbOverview })
const sourceFiles = computed(() => (kb.data.value?.sources ?? []).filter((s) => s.present).map((s) => s.file))

const answer = ref('')
const sourceRef = ref('')
watch(
  () => detail.data.value,
  (item) => {
    if (!item) return
    answer.value = item.answer ?? item.suggestion ?? ''
    sourceRef.value = item.source_ref ?? ''
  },
)
const material = useQuery({
  queryKey: computed(() => ['review', 'material', sourceRef.value]),
  queryFn: () => getMaterial(sourceRef.value),
  enabled: computed(() => dialogOpen.value && !!sourceRef.value),
})

const done = (msg: string) => {
  toast(msg)
  invalidate()
  client.invalidateQueries({ queryKey: ['kb'] })
}
const approveMut = useMutation({
  mutationFn: () => approveReview(openId.value as number, answer.value.trim(), sourceRef.value),
  onSuccess: (item) => {
    done(item.status === 'approved' ? '已通过并发布到知识库' : '已通过，发布尚未完成，可稍后重试发布')
    openId.value = null
  },
  onError: (err) => toast(errorText(err), 'error'),
})
const rejectMut = useMutation({
  mutationFn: () => rejectReview(openId.value as number),
  onSuccess: () => {
    done('已驳回')
    openId.value = null
  },
  onError: (err) => toast(errorText(err), 'error'),
})
const publishMut = useMutation({
  mutationFn: () => retryPublish(openId.value as number),
  onSuccess: (item) => done(item.status === 'approved' ? '发布完成' : '发布仍未完成，请检查嵌入服务与 Milvus'),
  onError: (err) => toast(errorText(err), 'error'),
})
const busy = computed(() => approveMut.isPending.value || rejectMut.isPending.value || publishMut.isPending.value)

async function approve() {
  const ok = await confirm({
    title: '通过并发布',
    body: `答案会先在"${sourceRef.value}"中核对，通过后写入知识库并向量化。审核人会被记录。`,
    confirmText: '通过并发布',
  })
  if (ok) approveMut.mutate()
}
async function reject() {
  const ok = await confirm({ title: '驳回这条知识缺口', body: '驳回后不会进入知识库。', confirmText: '确认驳回', danger: true })
  if (ok) rejectMut.mutate()
}
</script>

<template>
  <PageHeader eyebrow="KNOWLEDGE REVIEW" title="知识缺口" desc="飞轮待审：从未解决的问题出发，核对依据，再确认可复用的答案。">
    <button class="btn" type="button" :disabled="processMut.isPending.value" @click="runProcess">
      {{ processMut.isPending.value ? '归并中…' : '归并待处理问题' }}
    </button>
  </PageHeader>

  <p class="notice">审核三问：是不是垃圾或重复问题？答案会不会过时？出现次数值不值得沉淀？三项都通过再发布。</p>

  <Panel title="审核队列">
    <template #extra>
      <button
        v-for="[value, label] in filters"
        :key="label"
        type="button"
        class="btn small"
        :class="{ primary: activeStatus === value }"
        @click="setStatus(value)"
      >
        {{ label }}
      </button>
    </template>

    <form class="toolbar" @submit.prevent="submitSearch">
      <input v-model="draft" class="grow" type="search" aria-label="搜索问题" placeholder="搜索问题…" autocomplete="off" />
      <button class="btn" type="submit">搜索</button>
    </form>

    <StateBlock
      :loading="list.isPending.value"
      :error="list.error.value"
      :empty="list.data.value && !list.data.value.items.length ? '没有符合条件的审核项' : ''"
      @retry="list.refetch()"
    />

    <div v-if="list.data.value?.items.length" class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>ID</th>
            <th>标准化问题</th>
            <th class="num">出现次数</th>
            <th>状态</th>
            <th>审核人</th>
            <th>创建</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in list.data.value.items" :key="item.id">
            <td class="mono">#{{ item.id }}</td>
            <td>
              <strong>{{ item.question }}</strong>
              <div v-if="item.suggestion" class="clamp muted small">AI 建议：{{ item.suggestion }}</div>
            </td>
            <td class="num">{{ item.occurrence_count }}</td>
            <td><Pill :tone="reviewStatus[item.status][1]">{{ reviewStatus[item.status][0] }}</Pill></td>
            <td>{{ item.reviewer || DASH }}</td>
            <td class="small">{{ dateTime(item.created_at) }}</td>
            <td><button class="btn small ghost" type="button" @click="openId = item.id">核对</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <Pager
      v-if="list.data.value?.items.length"
      :page="list.data.value.page"
      :pages="list.data.value.pages"
      :total="list.data.value.total"
      @go="page = $event"
    />
  </Panel>

  <AppDialog v-model="dialogOpen" :title="`审核项 #${openId ?? ''}`" wide>
    <StateBlock :loading="detail.isPending.value" :error="detail.error.value" @retry="detail.refetch()" />
    <template v-if="detail.data.value">
      <dl class="kv">
        <dt>问题</dt>
        <dd><strong>{{ detail.data.value.question }}</strong></dd>
        <dt>状态</dt>
        <dd><Pill :tone="reviewStatus[detail.data.value.status][1]">{{ reviewStatus[detail.data.value.status][0] }}</Pill></dd>
        <dt>出现次数</dt>
        <dd>{{ detail.data.value.occurrence_count }}</dd>
        <dt>审核人</dt>
        <dd>{{ detail.data.value.reviewer || DASH }} · {{ dateTime(detail.data.value.reviewed_at) }}</dd>
      </dl>
      <p v-if="detail.data.value.publish_error" class="notice error">发布失败：{{ detail.data.value.publish_error }}</p>

      <template v-if="detail.data.value.status === 'pending'">
        <div class="grid-2 edit">
          <div>
            <label class="field">
              审核后的答案（会写入知识库）
              <textarea v-model="answer" rows="8" maxlength="4000" />
            </label>
            <label class="field">
              依据材料
              <select v-model="sourceRef">
                <option value="" disabled>选择可信材料文件</option>
                <option v-for="f in sourceFiles" :key="f" :value="f">{{ f }}</option>
              </select>
            </label>
            <p class="small muted">答案中的关键内容必须能在所选材料中找到，否则后端会拒绝发布。</p>
          </div>
          <div class="material">
            <div class="small muted">材料原文</div>
            <p v-if="!sourceRef" class="muted">先选择依据材料。</p>
            <p v-else-if="material.isPending.value" class="muted">读取中…</p>
            <p v-else-if="material.error.value" class="notice error">{{ errorText(material.error.value) }}</p>
            <pre v-else-if="material.data.value" class="pre small">{{ material.data.value.text }}</pre>
          </div>
        </div>
      </template>
      <template v-else-if="detail.data.value.answer">
        <h3 class="sub">已审核答案</h3>
        <p class="pre">{{ detail.data.value.answer }}</p>
        <p class="small muted">依据：{{ detail.data.value.source_ref || DASH }}</p>
      </template>
    </template>

    <template v-if="detail.data.value?.status === 'pending' || detail.data.value?.status === 'publishing'" #footer>
      <template v-if="detail.data.value.status === 'pending'">
        <button class="btn danger" type="button" :disabled="busy" @click="reject">驳回</button>
        <button class="btn primary" type="button" :disabled="busy || !answer.trim() || !sourceRef" @click="approve">
          {{ approveMut.isPending.value ? '发布中…' : '通过并发布' }}
        </button>
      </template>
      <button v-else class="btn primary" type="button" :disabled="busy" @click="publishMut.mutate()">
        {{ publishMut.isPending.value ? '发布中…' : '重试发布' }}
      </button>
    </template>
  </AppDialog>
</template>

<style scoped>
.edit {
  margin-top: 16px;
  gap: 16px;
}
.edit .field {
  margin-bottom: 12px;
}
.material pre {
  max-height: 300px;
  overflow: auto;
  background: var(--canvas);
  padding: 12px;
  border-radius: 8px;
  margin: 6px 0 0;
}
.sub {
  font-size: 14px;
  margin: 16px 0 6px;
}
</style>
