<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getAcceptanceEval } from '../../api/endpoints'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import StatCard from '../../components/StatCard.vue'
import StateBlock from '../../components/StateBlock.vue'
import { dateTime, fixed } from '../../utils/format'

const { data, error, isPending, refetch } = useQuery({ queryKey: ['acceptance', 'eval'], queryFn: getAcceptanceEval })
const ev = computed(() => data.value?.eval)
const scan = computed(() => data.value?.scan)
// 先看没过红线的，再按 F1 从低到高
const classes = computed(() =>
  [...(ev.value?.classes ?? [])].sort((a, b) => Number(a.passed) - Number(b.passed) || a.f1 - b.f1),
)
</script>

<template>
  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />
  <template v-if="data && ev && scan">
    <p v-if="!ev.present" class="notice warn">{{ ev.hint }}</p>
    <template v-else>
      <section class="stat-strip">
        <StatCard label="micro-F1" :value="fixed(ev.micro?.f1)" :foot="`P ${fixed(ev.micro?.p)} · R ${fixed(ev.micro?.r)}`" />
        <StatCard label="macro-F1" :value="fixed(ev.macro?.f1)" :foot="`P ${fixed(ev.macro?.p)} · R ${fixed(ev.macro?.r)}`" />
        <StatCard label="测试集" :value="ev.test_size" unit="条" :foot="`评测于 ${dateTime(ev.ran_at)}`" />
        <StatCard label="误判" :value="(ev.total_fp ?? 0) + (ev.total_fn ?? 0)" unit="笔" :foot="`冤枉 ${ev.total_fp} · 放跑 ${ev.total_fn}（共 ${ev.total_cells} 道是非题）`" />
        <StatCard
          label="容错红线"
          :value="ev.red_line_passed ? '全部达标' : '有类目未达标'"
          foot="严档 F1 ≥ 0.9，中档 ≥ 0.8"
          :tone="ev.red_line_passed ? 'normal' : 'warn'"
        />
      </section>

      <Panel title="各类目表现">
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>类目</th>
                <th>严重度</th>
                <th class="num">精确率</th>
                <th class="num">召回率</th>
                <th class="num">F1</th>
                <th class="num">红线</th>
                <th class="num">样本</th>
                <th class="num">冤枉 FP</th>
                <th class="num">放跑 FN</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in classes" :key="c.name" :class="{ fail: !c.passed }">
                <td>{{ c.name }}</td>
                <td>{{ c.severity }}</td>
                <td class="num">{{ fixed(c.p) }}</td>
                <td class="num">{{ fixed(c.r) }}</td>
                <td class="num">
                  <strong>{{ fixed(c.f1) }}</strong>
                  <Pill v-if="!c.passed" tone="red" class="gap">未过线</Pill>
                </td>
                <td class="num">{{ c.red_line ?? '—' }}</td>
                <td class="num">{{ c.support }}</td>
                <td class="num">{{ c.fp }}</td>
                <td class="num">{{ c.fn }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>
    </template>

    <Panel title="阈值扫描">
      <template #extra>
        <Pill v-if="scan.present" :tone="scan.consistent ? 'green' : 'red'">
          {{ scan.consistent ? `与在用阈值 ${scan.in_use_threshold} 一致` : '与在用阈值不一致' }}
        </Pill>
      </template>
      <p v-if="!scan.present" class="muted">{{ scan.hint }}</p>
      <table v-else class="data">
        <thead>
          <tr>
            <th class="num">阈值</th>
            <th class="num">验证集 micro-F1</th>
            <th class="num">TP</th>
            <th class="num">FP</th>
            <th class="num">FN</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in scan.scan" :key="row.threshold" :class="{ best: row.threshold === scan.best_threshold }">
            <td class="num">
              {{ row.threshold }}<Pill v-if="row.threshold === scan.best_threshold" tone="green" class="gap">当选</Pill>
            </td>
            <td class="num">{{ fixed(row.micro_f1, 4) }}</td>
            <td class="num">{{ row.tp }}</td>
            <td class="num">{{ row.fp }}</td>
            <td class="num">{{ row.fn }}</td>
          </tr>
        </tbody>
      </table>
    </Panel>
  </template>
</template>

<style scoped>
tr.fail td {
  background: #fdf7f8;
}
tr.best td {
  background: var(--brand-soft);
}
.gap {
  margin-left: 6px;
}
</style>
