<!-- 咨询主题（对应 V2 admin-classification.js 的 topicsPage） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { getTopicCatalog, getTopicDistribution, listTopicQuestions } from '../api/endpoints'
import type { TopicQuestion } from '../api/types'
import DataPage from '../components/DataPage.vue'
import DataState from '../components/DataState.vue'
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import VStat from '../components/VStat.vue'
import VTable from '../components/VTable.vue'
import { reportDataTime } from '../composables/useDataTime'
import { openModal } from '../composables/useModal'
import { useUrlNumber, useUrlState } from '../composables/useUrlState'
import MetaRow from './classification/MetaRow.vue'
import Note from './classification/Note.vue'
import QuestionModal from './classification/QuestionModal.vue'
import Tags from './classification/Tags.vue'
import { openClsGuide } from './classification/guide'
import { finite, num, pct, reviewNames, source, stamp } from './classification/shared'

const label = useUrlState('label', '')
const page = useUrlNumber('page', 1)
const size = useUrlNumber('size', 10)

const cv = useQuery({ queryKey: ['topics', 'catalog'], queryFn: getTopicCatalog })
const dv = useQuery({ queryKey: ['topics', 'distribution'], queryFn: getTopicDistribution })
watch(dv.dataUpdatedAt, reportDataTime, { immediate: true })

const catalogue = computed(() => cv.data.value?.classes || [])
const d = computed(() => dv.data.value)
const counts = computed(() => new Map((d.value?.classes || []).map((c) => [c.label, c])))
const hit = computed(() => (d.value ? (d.value.classes || []).filter((c) => finite(c.count) && c.count > 0).length : null))
// 所选类目不在权威类目里时，回到第一个类目
const current = computed(() => (catalogue.value.some((c) => c.label === label.value) ? label.value : catalogue.value[0]?.label || ''))
const selected = computed(() => catalogue.value.find((c) => c.label === current.value))
const examples = computed(() => (counts.value.get(current.value)?.samples || []).slice(0, 3))
const ratio = (name: string) => {
  const row = counts.value.get(name)
  return finite(row?.count) && finite(d.value?.total) && d.value.total > 0 ? row.count / d.value.total : null
}

const qv = useQuery({
  queryKey: computed(() => ['topics', 'questions', current.value, page.value, size.value]),
  queryFn: () => listTopicQuestions(current.value, page.value, size.value),
  enabled: computed(() => !!current.value),
  placeholderData: keepPreviousData,
})
const q = computed(() => qv.data.value)

function pick(name: string) {
  label.value = name
  page.value = 1
}
function setSize(v: string) {
  size.value = Number(v)
  page.value = 1
}
function turn(step: number) {
  if (q.value) page.value = Math.min(q.value.pages, Math.max(1, q.value.page + step))
}
const showQuestion = (row: TopicQuestion) => openModal({ title: '归类问题 · #' + row.question_id, view: QuestionModal, props: { row }, cls: 'classification-dialog' })
</script>

<template>
  <DataPage page="topics">
    <template #actions>
      <button class="btn soft" @click="openClsGuide">查看查询范围</button>
    </template>

    <div class="stat-strip data-metrics">
      <VStat label="已归类问题" :value="d?.total" unit="条" foot="分布接口的独立问题数" />
      <VStat label="已命中类目" :value="hit" unit="类" foot="问题可同时命中多个类目" />
      <VStat label="权威类目" :value="cv.data.value ? catalogue.length : null" unit="类" foot="名称与边界来自类目定义" />
      <VStat label="最新归类" :value="d?.latest ? d.latest.replace('T', ' ').slice(5, 16) : null" foot="接口返回的归类时间" />
    </div>
    <DataState v-if="!d" :loading="dv.isPending.value" :error="dv.error.value" />
    <template v-else>
      <MetaRow
        :items="[
          ['分布来源', source(d.source)],
          ['占比口径', '类目问题数 / 已归类问题数'],
        ]"
      />
      <Note>一个问题可以属于多个类目，各类占比之和可能超过 100%。0 条表示当前没有命中，不代表未分类问题总数。</Note>
    </template>
    <DataState v-if="!cv.data.value" :loading="cv.isPending.value" :error="cv.error.value" />
    <div v-else class="cls-topics-layout">
      <aside class="panel cls-topic-list">
        <div class="panel-head">
          <h2>咨询类目</h2>
          <span class="small muted">{{ catalogue.length }} 类</span>
        </div>
        <button v-for="c in catalogue" :key="c.label" class="cls-topic-button" :class="{ active: current === c.label }" :aria-pressed="current === c.label" @click="pick(c.label)">
          <span
            >{{ c.label }}<small>{{ ratio(c.label) == null ? '—' : pct(ratio(c.label)) }}</small></span
          ><b>{{ num(counts.get(c.label)?.count) }}</b
          ><span class="cls-topic-track"><i :style="{ width: (ratio(c.label) == null ? 0 : Math.min(100, (ratio(c.label) as number) * 100)) + '%' }"></i></span>
        </button>
      </aside>
      <div>
        <section class="panel">
          <div class="panel-head">
            <h2>{{ current }} · 问题明细</h2>
            <StatusPill color="neutral">服务端分页</StatusPill>
          </div>
          <div class="cls-boundary">
            <span>类目边界</span>
            <p>{{ selected?.boundary || '未提供' }}</p>
            <details v-if="examples.length" class="cls-examples">
              <summary>分布中的代表问法 · {{ examples.length }} 条</summary>
              <ul>
                <li v-for="(text, i) in examples" :key="i">{{ text }}</li>
              </ul>
            </details>
          </div>
          <Note v-if="!current">暂无可查询类目。</Note>
          <DataState v-else-if="!q" :loading="qv.isPending.value" :error="qv.error.value" />
          <template v-else>
            <MetaRow
              :items="[
                ['列表来源', source(q.source)],
                ['类目问题', q.total],
                ['分页范围', '所选类目的全部问题'],
              ]"
            />
            <VTable :heads="['问题 / 原始问法', '完整标签', '来源 / 审核', '归类时间', '操作']" :empty="!q.items?.length">
              <tr v-for="row in q.items ?? []" :key="row.question_id">
                <td class="cls-question">
                  <strong>{{ row.text || row.raw_question || '未标注文本' }}</strong><span class="table-sub">#{{ row.question_id }} · 出现 {{ num(row.occurrence_count) }} 次</span>
                </td>
                <td><Tags :values="row.labels" /></td>
                <td>
                  {{ source(row.source) }}<span class="table-sub">审核：{{ (row.review_status && reviewNames[row.review_status]) || row.review_status || '未提供' }}</span>
                </td>
                <td class="data-time-cell">{{ stamp(row.classified_at) }}</td>
                <td><button class="table-actions" @click="showQuestion(row)">查看 <Icon name="arrow" /></button></td>
              </tr>
            </VTable>
            <div class="data-table-footer cls-pagination">
              <span>共 {{ num(q.total) }} 条 · 第 {{ num(q.page) }} / {{ num(q.pages) }} 页</span>
              <label
                >每页<select id="cls-topic-size" aria-label="每页问题数" :value="size" @change="setSize(($event.target as HTMLSelectElement).value)">
                  <option v-for="s in [10, 20, 50]" :key="s" :value="s">{{ s }} 条</option>
                </select></label
              >
              <div>
                <button class="btn" :disabled="q.page <= 1" @click="turn(-1)">上一页</button><button class="btn" :disabled="q.page >= q.pages" @click="turn(1)">下一页</button>
              </div>
            </div>
          </template>
        </section>
      </div>
    </div>
  </DataPage>
</template>
