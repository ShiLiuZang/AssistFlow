<!-- 可比较运行的折线图：范围 0–1，缺失指标不补零也不连线 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { EvalRun } from '../../api/types'
import { decimal, finite } from './state'

const props = defineProps<{ runs: EvalRun[]; metric: string; label: string }>()
const left = 48, right = 612, top = 20, bottom = 145
const rows = computed(() => [...props.runs].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at))))
const x = (i: number) => (rows.value.length === 1 ? (left + right) / 2 : left + ((right - left) * i) / (rows.value.length - 1))
const y = (v: number) => bottom - Math.max(0, Math.min(1, v)) * (bottom - top)
const segments = computed(() => {
  const out: string[] = []
  let seg: string[] = []
  rows.value.forEach((row, i) => {
    const v = row.metrics?.[props.metric]
    if (finite(v)) seg.push(`${x(i)},${y(v)}`)
    else {
      if (seg.length > 1) out.push(seg.join(' '))
      seg = []
    }
  })
  if (seg.length > 1) out.push(seg.join(' '))
  return out
})
const points = computed(() =>
  rows.value.flatMap((row, i) => {
    const v = row.metrics?.[props.metric]
    return finite(v) ? [{ id: row.id, cx: x(i), cy: y(v), v }] : []
  }),
)
</script>

<template>
  <div class="report-trend-chart">
    <svg viewBox="0 0 660 183" role="img" :aria-label="`${label} 可比较运行记录，范围零到一`">
      <template v-for="v in [0, 0.5, 1]" :key="v">
        <line :x1="left" :x2="right" :y1="y(v)" :y2="y(v)" />
        <text x="34" :y="y(v) + 4" text-anchor="end">{{ v.toFixed(1) }}</text>
      </template>
      <polyline v-for="(pts, i) in segments" :key="'s' + i" :points="pts" />
      <template v-for="p in points" :key="'p' + p.id">
        <circle :cx="p.cx" :cy="p.cy" r="4"><title>{{ `RUN-${p.id}：${decimal(p.v)}` }}</title></circle>
        <text class="report-point-label" :x="p.cx" :y="p.cy - 10" text-anchor="middle">{{ decimal(p.v) }}</text>
      </template>
      <text v-for="(row, i) in rows" :key="'l' + row.id" :x="x(i)" y="171" text-anchor="middle">RUN-{{ row.id }}</text>
    </svg>
    <p class="field-hint">
      {{ rows.length === 1 ? '只有一次可比较运行，仅展示单点读数。' : `当前 ${rows.length} 次可比较运行，按记录时间排列。缺失指标不补零，也不连接缺口。` }}
    </p>
  </div>
</template>
