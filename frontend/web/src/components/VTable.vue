<!-- V2 的 table(heads, rows)：没有行时显示"没有符合条件的记录" -->
<script setup lang="ts">
defineProps<{ heads: string[]; empty?: boolean; cls?: string }>()
</script>

<template>
  <div class="table-wrap">
    <table :class="cls">
      <thead>
        <tr>
          <th v-for="h in heads" :key="h">{{ h }}</th>
        </tr>
      </thead>
      <tbody>
        <slot />
        <tr v-if="empty">
          <td :colspan="heads.length"><div class="empty">没有符合条件的记录</div></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
