<script setup lang="ts">
import { computed } from 'vue'
import StatusPill from '../../components/StatusPill.vue'
import { dec, finite } from './shared'
const props = defineProps<{ scores?: { label: string; score: number; hit: boolean }[]; threshold?: number | null }>()
const rows = computed(() => [...(props.scores || [])].sort((a, b) => b.score - a.score))
const showLine = computed(() => finite(props.threshold) && props.threshold >= 0 && props.threshold <= 1)
</script>

<template>
  <div class="cls-probabilities">
    <div v-for="row in rows" :key="row.label" class="cls-probability-row" :class="{ hit: row.hit }">
      <strong>{{ row.label }}</strong>
      <div class="cls-probability-track" aria-hidden="true">
        <i :style="{ width: (finite(row.score) ? Math.max(0, Math.min(100, row.score * 100)) : 0) + '%' }"></i
        ><span v-if="showLine" class="cls-threshold-line" :style="{ left: (threshold as number) * 100 + '%' }"></span>
      </div>
      <b>{{ dec(row.score) }}</b><span><StatusPill v-if="row.hit">命中</StatusPill></span>
    </div>
    <p class="field-hint section-gap">分数范围 0–1{{ finite(threshold) ? `，竖线为判定阈值 ${threshold}` : '，阈值未提供' }}；命中标签以服务返回为准，兜底不等于过线。</p>
  </div>
</template>
