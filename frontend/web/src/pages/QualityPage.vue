<!-- RAG 质量：四种检索策略的评测报告、逐题明细、重新评测，以及单题试问 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { askKnowledge, getEvalState, getRagReport, listEvalCases, runEvaluation } from '../api/endpoints'
import type { Strategy } from '../api/types'
import BarList from '../components/BarList.vue'
import PageHeader from '../components/PageHeader.vue'
import Panel from '../components/Panel.vue'
import Pill from '../components/Pill.vue'
import StateBlock from '../components/StateBlock.vue'
import TabBar from '../components/TabBar.vue'
import { confirm } from '../composables/useConfirm'
import { useUrlState } from '../composables/useUrlState'
import { errorText, toast } from '../composables/useToast'
import { refusalReasons, strategyNames } from '../utils/labels'
import { dateTime, fixed, pct, DASH } from '../utils/format'

const client = useQueryClient()
const tab = useUrlState('tab', 'report')
const tabs: [string, string][] = [
  ['report', '评测报告'],
  ['details', '逐题明细'],
  ['trial', '单题试问'],
]

const report = useQuery({ queryKey: ['rag', 'report'], queryFn: getRagReport })
const evalState = useQuery({
  queryKey: ['rag', 'state'],
  queryFn: getEvalState,
  refetchInterval: (q) => (q.state.data?.running ? 5000 : false),
})

const summary = computed(() => Object.entries(report.data.value?.summary ?? {}))
const bestMrr = computed(() => Math.max(...summary.value.map(([, s]) => s.mrr), 0))

/* 重新评测 */
const evalTopK = ref(5)
const evalGenerate = ref(false)
const evalMut = useMutation({
  mutationFn: () => runEvaluation(evalTopK.value, evalGenerate.value),
  onSuccess: () => {
    toast('评测完成，报告已更新')
    client.invalidateQueries({ queryKey: ['rag'] })
  },
  onError: (err) => {
    toast(errorText(err), 'error')
    client.invalidateQueries({ queryKey: ['rag', 'state'] })
  },
})
const running = computed(() => evalMut.isPending.value || !!evalState.data.value?.running)
async function startEval() {
  const ok = await confirm({
    title: '重新运行 RAG 评测',
    body: `用固定题集对四种策略逐题检索，Top ${evalTopK.value}。${
      evalGenerate.value ? '同时生成回答，会调用付费聊天模型，耗时更长。' : '只评检索，不生成回答。'
    }\n最长约 10 分钟，完成后覆盖旧报告；超时不会覆盖。`,
    confirmText: '开始评测',
  })
  if (ok) {
    evalMut.mutate()
    setTimeout(() => client.invalidateQueries({ queryKey: ['rag', 'state'] }), 800)
  }
}

/* 逐题明细 */
const detailStrategy = useUrlState('strategy', 'hybrid_rerank')
const onlyFailed = ref(false)
const details = computed(() =>
  (report.data.value?.details ?? []).filter(
    (d) => d.strategy === detailStrategy.value && (!onlyFailed.value || d.error || d.rr < 1 || !d.refusal_correct),
  ),
)

/* 单题试问 */
const cases = useQuery({ queryKey: ['rag', 'cases'], queryFn: listEvalCases, enabled: computed(() => tab.value === 'trial') })
const trial = ref({ query: '', strategy: 'hybrid_rerank' as Strategy, top_k: 5, rewrite: false, split: false })
const asked = ref('')
const askMut = useMutation({
  mutationFn: () => askKnowledge({ ...trial.value, query: trial.value.query.trim() }),
  onSuccess: () => (asked.value = trial.value.query.trim()),
})
function loadCase(event: Event) {
  const select = event.target as HTMLSelectElement
  if (select.value) trial.value.query = select.value
  select.value = ''
}
async function ask() {
  const ok = await confirm({
    title: '单题试问',
    body: '会执行一次检索并调用聊天模型生成回答（付费）。',
    confirmText: '提问',
  })
  if (ok) askMut.mutate()
}
</script>

<template>
  <PageHeader eyebrow="RAG QUALITY" title="RAG 质量" desc="看策略、看逐题证据，分清检索结果与生成判断。">
    <button class="btn" type="button" @click="report.refetch()">刷新报告</button>
  </PageHeader>

  <TabBar v-model="tab" :tabs="tabs" />

  <template v-if="tab === 'report'">
    <StateBlock :loading="report.isPending.value" :error="report.error.value" @retry="report.refetch()" />
    <template v-if="report.data.value">
      <p v-if="report.data.value.status !== 'evaluated'" class="notice warn">尚未生成评测报告，可在下方运行一次评测。</p>
      <template v-else>
        <p class="muted small">
          报告时间 {{ dateTime(report.data.value.created_at) }} · Top {{ report.data.value.k }} ·
          {{ report.data.value.generation ? '含回答生成' : '仅检索' }}
        </p>
        <div class="grid-2">
          <Panel title="策略对比">
            <div class="table-wrap">
              <table class="data">
                <thead>
                  <tr>
                    <th>策略</th>
                    <th class="num">召回@K</th>
                    <th class="num">MRR</th>
                    <th class="num">拒答准确率</th>
                    <th class="num">关键词覆盖</th>
                    <th class="num">失败</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="[name, s] in summary" :key="name">
                    <td>
                      {{ strategyNames[name] ?? name }}
                      <Pill v-if="s.mrr === bestMrr" tone="green">最佳</Pill>
                    </td>
                    <td class="num">{{ pct(s.recall_at_k) }}</td>
                    <td class="num">{{ fixed(s.mrr) }}</td>
                    <td class="num">{{ pct(s.refusal_accuracy) }}</td>
                    <td class="num">{{ pct(s.keyword_coverage) }}</td>
                    <td class="num">{{ s.failures }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="small muted">题数 {{ summary[0]?.[1].cases ?? DASH }}，其中应回答 {{ summary[0]?.[1].answerable_cases ?? DASH }} 题。</p>
          </Panel>
          <Panel title="MRR（越高越好）">
            <BarList :items="summary.map(([name, s]) => ({ label: strategyNames[name] ?? name, value: Number(s.mrr.toFixed(3)) }))" />
          </Panel>
        </div>
      </template>
    </template>

    <Panel title="重新评测">
      <div class="toolbar">
        <label class="check">Top K <input v-model.number="evalTopK" type="number" min="1" max="50" class="k" /></label>
        <label class="check"><input v-model="evalGenerate" type="checkbox" /> 同时生成回答（付费）</label>
        <button class="btn primary" type="button" :disabled="running" @click="startEval">
          {{ running ? '评测运行中…' : '开始评测' }}
        </button>
      </div>
      <p class="small muted">同一时间只能运行一次评测；运行中刷新页面不会中断。</p>
    </Panel>
  </template>

  <template v-else-if="tab === 'details'">
    <Panel title="逐题明细">
      <template #extra>
        <select v-model="detailStrategy" aria-label="策略">
          <option v-for="(name, key) in strategyNames" :key="key" :value="key">{{ name }}</option>
        </select>
        <label class="check"><input v-model="onlyFailed" type="checkbox" /> 只看未满分</label>
      </template>
      <StateBlock :loading="report.isPending.value" :error="report.error.value" :empty="report.data.value && !details.length ? '没有符合条件的题目' : ''" @retry="report.refetch()" />
      <div v-if="details.length" class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>题目</th>
              <th>应拒答</th>
              <th class="num">召回</th>
              <th class="num">RR</th>
              <th>拒答判断</th>
              <th>首条命中</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in details" :key="d.id">
              <td>
                <strong>{{ d.query }}</strong>
                <div class="small muted mono">{{ d.id }}</div>
                <div v-if="d.error" class="small" style="color: var(--red)">{{ d.error }}</div>
              </td>
              <td>{{ d.should_refuse ? '是' : '否' }}</td>
              <td class="num">{{ pct(d.recall, 0) }}</td>
              <td class="num">{{ fixed(d.rr, 2) }}</td>
              <td><Pill :tone="d.refusal_correct ? 'green' : 'red'">{{ d.refusal_correct ? '正确' : '错误' }}</Pill></td>
              <td class="small"><span class="clamp">{{ d.hits[0]?.question ?? DASH }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>
  </template>

  <template v-else>
    <Panel title="单题试问">
      <form class="trial" @submit.prevent="trial.query.trim() && ask()">
        <div class="toolbar">
          <input v-model="trial.query" class="grow" type="text" aria-label="问题" placeholder="输入一个顾客会问的问题…" autocomplete="off" required />
          <select
            aria-label="从题集载入"
            value=""
            @change="loadCase"
          >
            <option value="">从题集载入…</option>
            <option v-for="c in cases.data.value?.cases ?? []" :key="c.id" :value="c.query">{{ c.query }}</option>
          </select>
        </div>
        <div class="toolbar">
          <select v-model="trial.strategy" aria-label="策略">
            <option v-for="(name, key) in strategyNames" :key="key" :value="key">{{ name }}</option>
          </select>
          <label class="check">Top K <input v-model.number="trial.top_k" type="number" min="1" max="20" class="k" /></label>
          <label class="check"><input v-model="trial.rewrite" type="checkbox" /> 问题改写</label>
          <label class="check"><input v-model="trial.split" type="checkbox" /> 多诉求拆分</label>
          <button class="btn primary" type="submit" :disabled="askMut.isPending.value || !trial.query.trim()">
            {{ askMut.isPending.value ? '生成中…' : '提问' }}
          </button>
        </div>
      </form>

      <p v-if="askMut.error.value" class="notice error">{{ errorText(askMut.error.value) }}</p>
      <p v-if="asked && trial.query.trim() !== asked" class="notice warn">问题已修改，下方结果对应的是"{{ asked }}"。</p>

      <template v-if="askMut.data.value">
        <div class="answer" :class="{ refused: askMut.data.value.refused }">
          <Pill :tone="askMut.data.value.refused ? 'amber' : 'green'">
            {{ askMut.data.value.refused ? `拒答：${refusalReasons[askMut.data.value.reason ?? ''] ?? askMut.data.value.reason}` : '有据回答' }}
          </Pill>
          <p class="pre">{{ askMut.data.value.answer }}</p>
        </div>
        <h3 v-if="askMut.data.value.citations.length" class="sub">引用证据</h3>
        <ol class="cites">
          <li v-for="c in askMut.data.value.citations" :key="c.n">
            <strong>[{{ c.n }}] {{ c.question }}</strong>
            <div class="small muted">{{ c.section_path }} · 分数 {{ fixed(c.score) }}</div>
            <p class="clamp small">{{ c.answer }}</p>
          </li>
        </ol>
      </template>
    </Panel>
  </template>
</template>

<style scoped>
.k {
  width: 72px;
}
.answer {
  padding: 14px;
  border-radius: 8px;
  background: var(--brand-soft);
  margin-top: 8px;
}
.answer.refused {
  background: var(--amber-soft);
}
.answer p {
  margin: 8px 0 0;
}
.sub {
  font-size: 14px;
  margin: 16px 0 8px;
}
.cites {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 8px;
}
.cites li {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.cites p {
  margin: 4px 0 0;
}
</style>
