<!-- 知识内容（对应 V2 contentPage）：全库筛选、搜索与分页，条件写在 URL 上 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { keepPreviousData, useQuery, type UseQueryReturnType } from '@tanstack/vue-query'
import { listChunks } from '../../api/endpoints'
import type { ContentType, KbOverview, VectorStatus } from '../../api/types'
import DataState from '../../components/DataState.vue'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { openModal } from '../../composables/useModal'
import { useUrlNumber, useUrlState } from '../../composables/useUrlState'
import ChunkDetailModal from './ChunkDetailModal.vue'
import KnowledgeMetrics from './KnowledgeMetrics.vue'
import { listStamp, num, typeName, typeNames } from './state'

const props = defineProps<{ overview: UseQueryReturnType<KbOverview, Error> }>()
const filter = useUrlState('status', 'all')
const type = useUrlState('type', 'all')
const query = useUrlState('q', '')
const page = useUrlNumber('page', 1)
const size = useUrlNumber('size', 20)
const draft = ref(query.value)
watch(query, (v) => (draft.value = v))

const params = computed(() => ({
  page: page.value,
  size: size.value,
  q: query.value || undefined,
  status: filter.value === 'all' ? undefined : (filter.value as VectorStatus),
  content_type: type.value === 'all' ? undefined : (type.value as ContentType),
}))
const list = useQuery({
  queryKey: computed(() => ['kb', 'chunks', params.value]),
  queryFn: () => listChunks(params.value),
  placeholderData: keepPreviousData,
})

function setFilter(value: string) {
  filter.value = value
  page.value = 1
}
function setType(value: string) {
  type.value = value
  page.value = 1
}
function setSize(value: string) {
  size.value = Number(value)
  page.value = 1
}
function submit() {
  query.value = draft.value.trim()
  page.value = 1
}
function clear() {
  draft.value = ''
  query.value = ''
  page.value = 1
}
const vector = (status: string) =>
  status === 'done' ? ['已向量化', ''] : status === 'pending' ? ['待向量化', 'amber'] : [status || '未知', 'neutral']
const showChunk = (id: number) => openModal({ title: '知识块详情', view: ChunkDetailModal, props: { id }, cls: 'knowledge-dialog' })
const emptyText = computed(() =>
  query.value || filter.value !== 'all' || type.value !== 'all' ? '全库中没有符合条件的知识块' : '尚无知识块，可先预览材料',
)
const data = computed(() => props.overview.data.value)
</script>

<template>
  <KnowledgeMetrics :data="data ?? {}" />
  <div v-if="data?.db_error" class="notice data-alert" role="alert">库存统计暂不可读取，未知值显示为 —；列表单独查询。</div>
  <VPanel title="知识内容">
    <template #extra><StatusPill color="neutral">全库查询</StatusPill></template>
    <div class="panel-toolbar data-toolbar">
      <div class="data-filters">
        <button
          v-for="[value, label] in [['all', '全部'], ['done', '已向量化'], ['pending', '待向量化']]"
          :key="value"
          class="filter-chip"
          :class="{ active: filter === value }"
          :aria-pressed="filter === value"
          @click="setFilter(value)"
        >
          {{ label }}
        </button>
      </div>
      <div class="data-table-tools">
        <select id="data-type" aria-label="筛选内容类型" :value="type" @change="setType(($event.target as HTMLSelectElement).value)">
          <option value="all">全部类型</option>
          <option v-for="key in [...Object.keys(typeNames), 'unmarked']" :key="key" :value="key">
            {{ key === 'unmarked' ? '未标注' : typeName(key) }}
          </option>
        </select>
        <form id="data-inventory-form" class="data-inventory-search" @submit.prevent="submit">
          <label class="search"><Icon name="search" /><input id="data-query" v-model="draft" maxlength="200" aria-label="搜索全库知识" placeholder="搜索问法、正文或章节" autocomplete="off" /></label>
          <button class="btn soft" type="submit">搜索</button>
          <button v-if="query || draft" class="btn text-btn" type="button" @click="clear">清除</button>
        </form>
      </div>
    </div>

    <div v-if="list.data.value" class="table-wrap">
      <table class="data-chunk-table">
        <thead>
          <tr>
            <th v-for="h in ['ID', '类型', '章节', '问法', '正文摘要', '状态 / 标记', '操作']" :key="h">{{ h }}</th>
          </tr>
        </thead>
        <tbody id="data-chunk-rows">
          <tr v-for="row in list.data.value.items" :key="row.id" :class="{ 'knowledge-pending': row.status === 'pending' }">
            <td class="mono muted">#{{ row.id }}</td>
            <td>{{ typeName(row.content_type) }}</td>
            <td>{{ row.section_path || row.category || '未标注章节' }}</td>
            <td><strong>{{ row.questions || '未标注问法' }}</strong></td>
            <td><p class="knowledge-answer">{{ row.answer }}</p></td>
            <td class="knowledge-markers"><StatusPill :color="vector(row.status)[1]">{{ vector(row.status)[0] }}</StatusPill><span v-if="row.is_key_clause" class="key-clause-label">关键条款</span><small class="table-sub">{{ listStamp(row.created_at) }}</small></td>
            <td>
              <button class="table-actions" @click="showChunk(row.id)">查看全文 <Icon name="arrow" /></button>
            </td>
          </tr>
          <tr v-if="!list.data.value.items.length">
            <td colspan="7"><div class="empty">{{ emptyText }}</div></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="panel-pad"><DataState :loading="list.isPending.value" :error="list.error.value" /></div>

    <div class="data-table-footer data-inventory-footer">
      <span>
        <template v-if="list.data.value">
          筛选结果 {{ num(list.data.value.total) }} 块<template v-if="list.data.value.total">
            · 本页 {{ (list.data.value.page - 1) * list.data.value.size + 1 }}–{{
              (list.data.value.page - 1) * list.data.value.size + list.data.value.items.length
            }}</template
          >
        </template>
        <template v-else>筛选结果 —</template>
        <template v-if="query"> · 搜索「{{ query }}」</template>
        <small>统计卡为全库总数；搜索范围包含完整正文。</small>
      </span>
      <div class="data-pagination">
        <label
          >每页<select id="data-size" aria-label="知识列表每页条数" :value="size" @change="setSize(($event.target as HTMLSelectElement).value)">
            <option v-for="n in [5, 10, 20, 50]" :key="n" :value="n">{{ n }}</option></select
          >块</label
        >
        <button class="btn" :disabled="!list.data.value || list.data.value.page <= 1" @click="page = (list.data.value?.page ?? 2) - 1">上一页</button>
        <span>{{ list.data.value ? `${list.data.value.page} / ${list.data.value.pages}` : '— / —' }}</span>
        <button class="btn" :disabled="!list.data.value || list.data.value.page >= list.data.value.pages" @click="page = (list.data.value?.page ?? 0) + 1">
          下一页
        </button>
      </div>
    </div>
  </VPanel>
</template>
