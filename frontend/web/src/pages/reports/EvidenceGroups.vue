<script setup lang="ts">
import type { EvalCase } from '../../api/types'
defineProps<{ item?: EvalCase | null }>()
</script>

<template>
  <p v-if="!item" class="field-hint">报告未保存该题的标准证据与预期关键词。</p>
  <template v-else-if="item.groups?.length">
    <ol class="report-groups">
      <li v-for="(group, i) in item.groups" :key="i">
        <template v-for="(path, j) in group" :key="j"><br v-if="j" />{{ path }}</template>
      </li>
    </ol>
    <p class="field-hint">组内任一路径命中即可覆盖该组；不同组分别计算。</p>
  </template>
  <p v-else class="field-hint">没有标准证据组，该题不进入召回率与 MRR 的分母。</p>
</template>
