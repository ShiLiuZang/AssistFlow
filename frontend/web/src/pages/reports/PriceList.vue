<script setup lang="ts">
import type { CostRow } from '../../api/types'
defineProps<{ row: CostRow }>()
</script>

<template>
  <div v-if="Object.keys(row.priced_subtotals ?? {}).length" class="report-prices">
    <span v-for="(amount, currency) in row.priced_subtotals" :key="currency" class="mono">{{ currency }} {{ amount }}</span>
  </div>
  <span v-else class="muted">无已定价小计</span>
</template>
