<!-- 检索自测：换个说法提问，看召回的是不是该召回的知识块 -->
<script setup lang="ts">
import { ref } from 'vue'
import { useMutation } from '@tanstack/vue-query'
import { searchKb } from '../../api/endpoints'
import type { Strategy } from '../../api/types'
import Panel from '../../components/Panel.vue'
import { errorText } from '../../composables/useToast'
import { contentTypeNames, strategyNames } from '../../utils/labels'
import { fixed, DASH } from '../../utils/format'

const q = ref('')
const strategy = ref<Strategy>('hybrid_rerank')
const topK = ref(5)
const searched = ref('')

const mut = useMutation({
  mutationFn: () => searchKb(q.value.trim(), strategy.value, topK.value),
  onSuccess: () => (searched.value = q.value.trim()),
})
</script>

<template>
  <Panel title="检索自测">
    <form class="toolbar" @submit.prevent="q.trim() && mut.mutate()">
      <input v-model="q" class="grow" type="search" aria-label="提问" placeholder="换一种说法提问，例如：退货寄回去谁出钱…" maxlength="500" autocomplete="off" required />
      <select v-model="strategy" aria-label="检索策略">
        <option v-for="(name, key) in strategyNames" :key="key" :value="key">{{ name }}</option>
      </select>
      <select v-model.number="topK" aria-label="返回条数">
        <option v-for="k in [3, 5, 10]" :key="k" :value="k">Top {{ k }}</option>
      </select>
      <button class="btn primary" type="submit" :disabled="mut.isPending.value || !q.trim()">
        {{ mut.isPending.value ? '检索中…' : '检索' }}
      </button>
    </form>
    <p class="small muted">只调用检索（嵌入、Milvus、可选重排），不调用大模型生成回答。</p>

    <p v-if="mut.error.value" class="notice error">{{ errorText(mut.error.value) }}</p>
    <p v-if="q.trim() && searched && q.trim() !== searched" class="notice warn">问法已修改，结果对应的是"{{ searched }}"，请重新检索。</p>

    <template v-if="mut.data.value">
      <p v-if="!mut.data.value.hits.length" class="muted">没有命中知识块。</p>
      <ol class="hits">
        <li v-for="(h, i) in mut.data.value.hits" :key="h.id ?? i">
          <div class="hit-head">
            <span class="rank">{{ i + 1 }}</span>
            <strong>{{ h.question || DASH }}</strong>
            <span class="score mono">分数 {{ fixed(h.score) }}<template v-if="h.rerank_score !== null"> · 重排 {{ fixed(h.rerank_score) }}</template></span>
          </div>
          <div class="small muted">
            #{{ h.id ?? DASH }} · {{ contentTypeNames[h.content_type ?? ''] ?? h.content_type ?? DASH }} · {{ h.section_path || DASH }}
          </div>
          <p class="clamp">{{ h.answer }}</p>
        </li>
      </ol>
    </template>
  </Panel>
</template>

<style scoped>
.hits {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.hits li {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.hit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.rank {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand-deep);
  font-size: 12px;
}
.score {
  margin-left: auto;
  color: var(--muted);
}
.hits p {
  margin: 6px 0 0;
  font-size: 13px;
}
</style>
