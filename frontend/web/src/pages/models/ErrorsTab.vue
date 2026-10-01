<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getAcceptanceErrors } from '../../api/endpoints'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import StateBlock from '../../components/StateBlock.vue'
import { useUrlState } from '../../composables/useUrlState'

const { data, error, isPending, refetch } = useQuery({ queryKey: ['acceptance', 'errors'], queryFn: getAcceptanceErrors })
const kind = useUrlState('kind', 'all')
const keyword = ref('')
const errors = computed(() =>
  (data.value?.errors ?? []).filter(
    (e) =>
      (kind.value === 'all' || e.kind === kind.value) &&
      (!keyword.value || [e.text, ...e.gold, ...e.pred].some((s) => s.includes(keyword.value))),
  ),
)
</script>

<template>
  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />
  <template v-if="data">
    <p v-if="!data.eval.present" class="notice warn">{{ data.eval.hint ?? '尚无评测报告。' }}</p>
    <template v-else>
      <div class="grid-2">
        <Panel title="错误类型">
          <dl class="kv">
            <template v-for="(n, k) in data.kinds" :key="k">
              <dt>{{ k }}</dt>
              <dd>
                {{ n }} 条
                <div v-if="data.recipes?.[k]" class="small muted">{{ data.recipes[k] }}</div>
              </dd>
            </template>
          </dl>
        </Panel>
        <Panel title="最常见的混淆（漏掉 → 错抢）">
          <p v-if="!data.pairs.length" class="muted">没有错位类错例。</p>
          <table v-else class="data">
            <thead>
              <tr>
                <th>应打</th>
                <th>被打成</th>
                <th class="num">次数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in data.pairs.slice(0, 10)" :key="`${p.missed}-${p.grabbed}`">
                <td>{{ p.missed }} <span v-if="p.severity" class="small muted">（{{ p.severity }}）</span></td>
                <td>{{ p.grabbed }}</td>
                <td class="num">{{ p.count }}</td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel :title="`错例（${errors.length} / ${data.errors.length}）`">
        <template #extra>
          <select v-model="kind" aria-label="错误类型">
            <option value="all">全部类型</option>
            <option v-for="(_, k) in data.kinds" :key="k" :value="k">{{ k }}</option>
          </select>
          <input v-model="keyword" type="search" aria-label="筛选错例" placeholder="筛选文本或类目…" autocomplete="off" />
        </template>
        <ul class="errors">
          <li v-for="(e, i) in errors" :key="i">
            <div class="text">{{ e.text }}</div>
            <div class="labels">
              <Pill tone="amber">{{ e.kind }}</Pill>
              <span class="small muted">标准：</span>
              <Pill v-for="g in e.gold" :key="`g-${g}`" :tone="e.missed.includes(g) ? 'red' : 'green'">{{ g }}</Pill>
              <span class="small muted">预测：</span>
              <Pill v-for="p in e.pred" :key="`p-${p}`" :tone="e.extra.includes(p) ? 'red' : 'green'">{{ p }}</Pill>
              <span v-if="!e.pred.length" class="small muted">（无）</span>
            </div>
          </li>
        </ul>
        <p class="small muted">红色标签表示漏打或多打。错例条数不等于矩阵笔数：错位一条会记两笔。</p>
      </Panel>
    </template>
  </template>
</template>

<style scoped>
.errors {
  list-style: none;
  margin: 0;
  padding: 0;
}
.errors li {
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}
.labels {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}
</style>
