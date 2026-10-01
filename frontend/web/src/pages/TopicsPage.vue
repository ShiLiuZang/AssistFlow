<!-- 咨询主题：17 类问题分布，点开某一类看完整问法与归类依据 -->
<script setup lang="ts">
import { computed } from 'vue'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { getTopicCatalog, getTopicDistribution, listTopicQuestions } from '../api/endpoints'
import PageHeader from '../components/PageHeader.vue'
import Pager from '../components/Pager.vue'
import Panel from '../components/Panel.vue'
import Pill from '../components/Pill.vue'
import StatCard from '../components/StatCard.vue'
import StateBlock from '../components/StateBlock.vue'
import { useUrlNumber, useUrlState } from '../composables/useUrlState'
import { dateTime, DASH } from '../utils/format'

const dist = useQuery({ queryKey: ['topics', 'distribution'], queryFn: getTopicDistribution })
const catalog = useQuery({ queryKey: ['topics', 'catalog'], queryFn: getTopicCatalog })

const label = useUrlState('label', '')
const page = useUrlNumber('page', 1)

const classes = computed(() => [...(dist.data.value?.classes ?? [])].sort((a, b) => b.count - a.count))
const max = computed(() => Math.max(1, ...classes.value.map((c) => c.count)))
const hit = computed(() => classes.value.filter((c) => c.count > 0).length)
const boundary = computed(() => catalog.data.value?.classes.find((c) => c.label === label.value)?.boundary)
const sourceName = computed(() =>
  dist.data.value?.source === 'conversation_history' ? '历史会话（隔离归类）' : '低置信度问题池',
)

function pick(name: string) {
  label.value = name
  page.value = 1
}

const questions = useQuery({
  queryKey: computed(() => ['topics', 'questions', label.value, page.value]),
  queryFn: () => listTopicQuestions(label.value, page.value, 20),
  enabled: computed(() => !!label.value),
  placeholderData: keepPreviousData,
})

const sampleText = (s: string | { text?: string }) => (typeof s === 'string' ? s : (s.text ?? ''))
</script>

<template>
  <PageHeader eyebrow="CONSULTATION TOPICS" title="咨询主题" desc="看清问题分布，按权威类目核对完整问法与归类依据。">
    <button class="btn" type="button" @click="dist.refetch()">刷新读数</button>
  </PageHeader>

  <StateBlock :loading="dist.isPending.value" :error="dist.error.value" @retry="dist.refetch()" />

  <template v-if="dist.data.value">
    <section class="stat-strip">
      <StatCard label="已归类问题" :value="dist.data.value.total" unit="条" :foot="`来源：${sourceName}`" />
      <StatCard label="命中类目" :value="`${hit} / ${classes.length}`" foot="至少有一条问题的类目" />
      <StatCard label="最近归类" :value="dateTime(dist.data.value.latest)" />
    </section>

    <div class="layout">
      <Panel title="类目分布">
        <p v-if="!dist.data.value.total" class="muted">还没有归类结果。可在"分类器管理"或"作业中心"运行批量归类。</p>
        <ul class="topic-list">
          <li v-for="c in classes" :key="c.label">
            <button type="button" :class="{ active: label === c.label }" @click="pick(c.label)">
              <span class="name">{{ c.label }}</span>
              <span class="track"><span v-if="c.count" class="fill" :style="{ width: `${(c.count / max) * 100}%` }" /></span>
              <span class="count">{{ c.count }}</span>
            </button>
          </li>
        </ul>
      </Panel>

      <Panel :title="label ? `「${label}」的问题` : '选择一个类目'">
        <p v-if="!label" class="muted">点击左侧类目，查看这一类的完整问法。</p>
        <template v-else>
          <p v-if="boundary" class="notice">归类边界：{{ boundary }}</p>
          <StateBlock
            :loading="questions.isPending.value"
            :error="questions.error.value"
            :empty="questions.data.value && !questions.data.value.items.length ? '这一类还没有问题' : ''"
            @retry="questions.refetch()"
          />
          <ul v-if="questions.data.value?.items.length" class="questions">
            <li v-for="item in questions.data.value.items" :key="item.question_id">
              <div>{{ item.text }}</div>
              <div class="small muted">
                <span v-if="item.text !== item.raw_question">原话：{{ item.raw_question }} · </span>
                出现 {{ item.occurrence_count }} 次 · {{ dateTime(item.asked_at) }}
              </div>
              <div class="labels">
                <Pill v-for="l in item.labels" :key="l" :tone="l === label ? 'green' : 'neutral'">{{ l }}</Pill>
                <Pill v-if="item.review_status" tone="amber">{{ item.review_status }}</Pill>
              </div>
            </li>
          </ul>
          <Pager
            v-if="questions.data.value?.items.length"
            :page="questions.data.value.page"
            :pages="questions.data.value.pages"
            :total="questions.data.value.total"
            @go="page = $event"
          />
          <details v-if="classes.find((c) => c.label === label)?.samples.length" class="samples">
            <summary>分布样例</summary>
            <ul>
              <li v-for="(s, i) in classes.find((c) => c.label === label)?.samples ?? []" :key="i">{{ sampleText(s) || DASH }}</li>
            </ul>
          </details>
        </template>
      </Panel>
    </div>
  </template>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(280px, 380px) minmax(0, 1fr);
  gap: 20px;
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
.topic-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.topic-list button {
  display: grid;
  grid-template-columns: 96px 1fr 36px;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 7px 8px;
  border: 0;
  border-radius: 6px;
  background: none;
  text-align: left;
  font-size: 13px;
}
.topic-list button:hover {
  background: var(--canvas);
}
.topic-list button.active {
  background: var(--brand-soft);
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track {
  height: 8px;
  background: var(--sand);
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  background: var(--brand);
}
.count {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.questions {
  list-style: none;
  margin: 0;
  padding: 0;
}
.questions li {
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}
.labels {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.samples {
  margin-top: 14px;
  font-size: 13px;
}
</style>
