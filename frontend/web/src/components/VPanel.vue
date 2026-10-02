<!-- V2 的 panel：<section class="panel"><div class="panel-head"><h2>…</h2>[extra]</div>…</section> -->
<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>{{ title }}</h2>
      <slot name="extra" />
    </div>
    <slot />
  </section>
</template>
