<!-- V2 的 data-record-fields：dt/dd 两列字段 -->
<script setup lang="ts">
defineProps<{ fields: [string, unknown][] }>()
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))
</script>

<template>
  <dl class="data-record-fields">
    <div v-for="[label, value] in fields" :key="label">
      <dt>{{ label }}</dt>
      <dd>{{ show(value) }}</dd>
    </div>
  </dl>
</template>
