<script setup lang="ts">
import { ref } from 'vue'
import { useMutation } from '@tanstack/vue-query'
import { classifyText } from '../../api/endpoints'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import { errorText } from '../../composables/useToast'
import { fixed } from '../../utils/format'

const text = ref('')
const asked = ref('')
const mut = useMutation({
  mutationFn: () => classifyText(text.value.trim()),
  onSuccess: () => (asked.value = text.value.trim()),
})
</script>

<template>
  <Panel title="单句试分类">
    <form class="toolbar" @submit.prevent="text.trim() && mut.mutate()">
      <input v-model="text" class="grow" type="text" aria-label="一句顾客提问" placeholder="输入一句顾客提问，例如：猫砂盆尺寸不合适想换个大的…" maxlength="500" autocomplete="off" />
      <button class="btn primary" type="submit" :disabled="mut.isPending.value || !text.trim()">
        {{ mut.isPending.value ? '分类中…' : '分类' }}
      </button>
    </form>
    <p class="small muted">调用本地 ONNX 分类服务（:8110），不调用大模型。</p>

    <p v-if="mut.error.value" class="notice error">{{ errorText(mut.error.value) }}</p>
    <p v-if="asked && text.trim() !== asked" class="notice warn">文本已修改，结果对应的是"{{ asked }}"。</p>

    <template v-if="mut.data.value">
      <div class="result">
        <span class="small muted">命中类目</span>
        <Pill v-for="l in mut.data.value.labels" :key="l" tone="green">{{ l }}</Pill>
        <span v-if="!mut.data.value.labels.length" class="muted">没有类目超过阈值</span>
        <Pill v-if="mut.data.value.fallback" tone="amber">最高分低于阈值，走兜底</Pill>
      </div>
      <ul class="scores">
        <li v-for="s in mut.data.value.scores.slice(0, 8)" :key="s.label" :class="{ hit: s.hit }">
          <span class="name">{{ s.label }}</span>
          <span class="track">
            <span class="fill" :style="{ width: `${Math.min(100, s.score * 100)}%` }" />
            <span
              v-if="mut.data.value.threshold !== null"
              class="line"
              :style="{ left: `${mut.data.value.threshold * 100}%` }"
              :title="`阈值 ${mut.data.value.threshold}`"
            />
          </span>
          <span class="value mono">{{ fixed(s.score) }}</span>
        </li>
      </ul>
      <p class="small muted">竖线为阈值 {{ mut.data.value.threshold ?? '—' }}，只显示得分最高的 8 类。</p>
    </template>
  </Panel>
</template>

<style scoped>
.result {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 8px 0 14px;
}
.scores {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.scores li {
  display: grid;
  grid-template-columns: 110px 1fr 60px;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.track {
  position: relative;
  height: 10px;
  background: var(--sand);
  border-radius: 999px;
}
.fill {
  display: block;
  height: 100%;
  background: var(--line-strong);
  border-radius: 999px;
}
.hit .fill {
  background: var(--brand);
}
.line {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 2px;
  background: var(--amber);
}
.value {
  text-align: right;
}
</style>
