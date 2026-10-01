<!-- 知识内容：分页表格 + 状态/类型筛选 + 搜索，全部条件同步到 URL -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { getChunk, listChunks } from '../../api/endpoints'
import type { ContentType, VectorStatus } from '../../api/types'
import AppDialog from '../../components/AppDialog.vue'
import Pager from '../../components/Pager.vue'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import StateBlock from '../../components/StateBlock.vue'
import { useUrlNumber, useUrlState } from '../../composables/useUrlState'
import { contentTypeNames, vectorStatus } from '../../utils/labels'
import { dateTime, DASH } from '../../utils/format'

const status = useUrlState('status', 'all')
const type = useUrlState('type', 'all')
const q = useUrlState('q', '')
const page = useUrlNumber('page', 1)
const size = 20

// 输入框先写草稿，按回车或点"搜索"才更新 URL，避免每敲一个字发一次请求
const draft = ref(q.value)
watch(q, (v) => (draft.value = v))
function submitSearch() {
  q.value = draft.value.trim()
  page.value = 1
}
// 注意：模板里的 ref 会被自动解包成普通值，所以不能把 ref 本身当参数传进函数
function setStatus(value: string) {
  status.value = value
  page.value = 1
}
function setType(value: string) {
  type.value = value
  page.value = 1
}

const params = computed(() => ({
  page: page.value,
  size,
  q: q.value || undefined,
  status: status.value === 'all' ? undefined : (status.value as VectorStatus),
  content_type: type.value === 'all' ? undefined : (type.value as ContentType),
}))

const { data, error, isPending, refetch } = useQuery({
  queryKey: computed(() => ['kb', 'chunks', params.value]),
  queryFn: () => listChunks(params.value),
  placeholderData: keepPreviousData, // 翻页时先保留上一页，避免闪烁
})

/* 详情弹窗 */
const detailId = ref<number | null>(null)
const detailOpen = computed({
  get: () => detailId.value !== null,
  set: (v: boolean) => {
    if (!v) detailId.value = null
  },
})
const detail = useQuery({
  queryKey: computed(() => ['kb', 'chunk', detailId.value]),
  queryFn: () => getChunk(detailId.value as number),
  enabled: computed(() => detailId.value !== null),
})
</script>

<template>
  <Panel title="知识内容">
    <template #extra>
      <div class="seg" role="group" aria-label="向量状态">
        <button
          v-for="[key, label] in [['all', '全部'], ['done', '已向量化'], ['pending', '待向量化'], ['failed', '失败']]"
          :key="key"
          type="button"
          :class="{ active: status === key }"
          @click="setStatus(key)"
        >
          {{ label }}
        </button>
      </div>
    </template>

    <form class="toolbar" @submit.prevent="submitSearch">
      <select :value="type" aria-label="内容类型" @change="setType(($event.target as HTMLSelectElement).value)">
        <option value="all">全部类型</option>
        <option v-for="(name, key) in contentTypeNames" :key="key" :value="key">{{ name }}</option>
      </select>
      <input v-model="draft" class="grow" type="search" aria-label="搜索知识" placeholder="搜索问法、正文或章节…" maxlength="200" autocomplete="off" />
      <button class="btn" type="submit">搜索</button>
    </form>

    <StateBlock :loading="isPending" :error="error" :empty="data && !data.items.length ? '没有符合条件的记录' : ''" @retry="refetch()" />

    <div v-if="data && data.items.length" class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>ID</th>
            <th>问法与答案摘要</th>
            <th>类型 / 分类</th>
            <th>向量状态</th>
            <th>录入时间</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data.items" :key="row.id">
            <td class="mono">#{{ row.id }}</td>
            <td>
              <strong>{{ row.questions }}</strong>
              <div class="clamp muted">{{ row.answer }}</div>
              <div class="small muted">
                {{ row.section_path || DASH }}<Pill v-if="row.is_key_clause" tone="amber" class="gap">关键条款</Pill>
              </div>
            </td>
            <td>
              {{ contentTypeNames[row.content_type ?? 'unmarked'] ?? row.content_type }}
              <div class="small muted">{{ row.category || DASH }}</div>
            </td>
            <td><Pill :tone="vectorStatus[row.status]?.[1]">{{ vectorStatus[row.status]?.[0] ?? row.status }}</Pill></td>
            <td class="small">{{ dateTime(row.created_at) }}</td>
            <td><button class="btn small ghost" type="button" @click="detailId = row.id">查看全文</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <Pager v-if="data && data.items.length" :page="data.page" :pages="data.pages" :total="data.total" @go="page = $event" />
  </Panel>

  <AppDialog v-model="detailOpen" :title="`知识块 #${detailId ?? ''}`" wide>
    <StateBlock :loading="detail.isPending.value" :error="detail.error.value" @retry="detail.refetch()" />
    <template v-if="detail.data.value">
      <dl class="kv">
        <dt>问法</dt>
        <dd>{{ detail.data.value.questions }}</dd>
        <dt>章节</dt>
        <dd>{{ detail.data.value.section_path || DASH }}</dd>
        <dt>类型</dt>
        <dd>{{ contentTypeNames[detail.data.value.content_type ?? 'unmarked'] }} · {{ detail.data.value.category || DASH }}</dd>
        <dt>向量</dt>
        <dd>{{ vectorStatus[detail.data.value.status]?.[0] }} · {{ detail.data.value.vector_id || '未写入' }}</dd>
        <dt>字数</dt>
        <dd>{{ detail.data.value.answer_chars }}</dd>
      </dl>
      <h3 class="sub">正文</h3>
      <p class="pre">{{ detail.data.value.answer }}</p>
    </template>
  </AppDialog>
</template>

<style scoped>
.seg {
  display: inline-flex;
  padding: 3px;
  background: var(--canvas);
  border-radius: 8px;
}
.seg button {
  border: 0;
  background: none;
  padding: 4px 10px;
  border-radius: 6px;
  color: var(--muted);
  font-size: 13px;
}
.seg button.active {
  background: var(--white);
  color: var(--brand-deep);
  box-shadow: var(--small-shadow);
}
.gap {
  margin-left: 6px;
}
.sub {
  font-size: 14px;
  margin: 16px 0 6px;
}
</style>
