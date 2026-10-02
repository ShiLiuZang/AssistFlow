<!-- 检索自测（对应 V2 searchPage） -->
<script setup lang="ts">
import { request } from '../../api/client'
import type { SearchHit, Strategy } from '../../api/types'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { kb, num, typeName } from './state'

const strategies: [Strategy, string][] = [
  ['vector', '向量检索'],
  ['bm25', '关键词检索'],
  ['hybrid', '混合检索'],
  ['hybrid_rerank', '混合 + 重排'],
]
function changed() {
  kb.hits = null
  kb.searchError = ''
}
async function search() {
  if (kb.searchBusy) return
  const query = kb.searchQuery
  const strategy = kb.strategy
  kb.searchBusy = true
  kb.hits = null
  kb.searchError = ''
  try {
    const data = await request<{ hits: SearchHit[] }>('/api/kb/search', { method: 'POST', body: { q: query, strategy, top_k: 5 }, timeoutMs: 30000 })
    if (query === kb.searchQuery && strategy === kb.strategy) kb.hits = data.hits
  } catch (error: any) {
    if (query === kb.searchQuery && strategy === kb.strategy) kb.searchError = error.message
  } finally {
    kb.searchBusy = false
  }
}
</script>

<template>
  <VPanel title="检索自测">
    <form id="data-search-form" class="panel-pad" @submit.prevent="search">
      <div class="query-grid">
        <label class="field">换一种说法提问<input id="data-search-query" v-model="kb.searchQuery" required maxlength="500" autocomplete="off" @input="changed" /></label>
        <label class="field"
          >检索策略<select id="data-search-strategy" v-model="kb.strategy" @change="changed">
            <option v-for="[key, label] in strategies" :key="key" :value="key">{{ label }}</option>
          </select></label
        >
        <button class="btn primary" type="submit" :disabled="kb.searchBusy"><Icon name="search" />{{ kb.searchBusy ? '正在检索…' : '检索' }}</button>
      </div>
      <p class="field-hint">点击后调用检索服务，可能使用嵌入或重排模型。检索分数不等于答案正确率。</p>
    </form>
    <div v-if="kb.searchError" class="panel-pad notice" role="alert">{{ kb.searchError }}</div>
    <div id="data-search-result" class="panel-pad">
      <div v-if="kb.hits == null" class="data-empty-state compact">
        <Icon name="search" />
        <h2>看看知识能否被找到</h2>
        <p>输入另一种问法，核对召回的内容与依据。</p>
      </div>
      <template v-else-if="kb.hits.length">
        <article v-for="(hit, index) in kb.hits" :key="hit.id ?? index" class="data-search-hit">
          <div class="between">
            <h3>{{ index + 1 }}. {{ hit.question || hit.section_path || '未标注问法' }}</h3>
            <StatusPill color="neutral">{{ typeName(hit.content_type) }}</StatusPill>
          </div>
          <p>{{ hit.answer }}</p>
          <div class="small muted">{{ hit.section_path || '未标注章节' }} · 检索分数 {{ num(hit.score) }} · 重排分数 {{ num(hit.rerank_score) }}</div>
        </article>
      </template>
      <div v-else class="empty">检索已完成，没有命中知识块。</div>
    </div>
  </VPanel>
</template>
