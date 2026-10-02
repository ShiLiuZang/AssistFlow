<!-- 知识块详情（对应 V2 chunkDetailView） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getChunk } from '../../api/endpoints'
import RecordFields from '../../components/RecordFields.vue'
import StatusPill from '../../components/StatusPill.vue'
import { closeModal } from '../../composables/useModal'
import { stamp, typeName } from './state'

const props = defineProps<{ id: number }>()
const { data: row, error, isPending, refetch } = useQuery({ queryKey: ['kb', 'chunk', props.id], queryFn: () => getChunk(props.id) })
const vector = (s: string) => (s === 'done' ? ['已向量化', ''] : s === 'pending' ? ['待向量化', 'amber'] : [s || '未知', 'neutral'])
const fields = computed<[string, unknown][]>(() => {
  const r = row.value
  if (!r) return []
  return [
    ['章节', r.section_path || '未标注'],
    ['分类', r.category || '未标注'],
    ['录入时间', stamp(r.created_at)],
    ['向量记录', r.vector_id || '未返回'],
    ['关联审核', r.review_id ? `#${r.review_id}` : '未关联'],
    ['相邻知识块', [r.prev_chunk_id ? `前 #${r.prev_chunk_id}` : '', r.next_chunk_id ? `后 #${r.next_chunk_id}` : ''].filter(Boolean).join(' · ') || '未关联'],
  ]
})
</script>

<template>
  <div class="modal-body">
    <div v-if="isPending" class="empty" role="status">正在读取完整内容…</div>
    <div v-else-if="error" class="data-empty-state compact">
      <h2>详情暂时无法读取</h2>
      <p>{{ error.message }}</p>
      <button class="btn" @click="refetch()">重新读取</button>
    </div>
    <template v-else-if="row">
      <div class="data-detail-meta">
        <StatusPill color="neutral">#{{ row.id }}</StatusPill>
        <StatusPill color="neutral">{{ typeName(row.content_type) }}</StatusPill>
        <StatusPill :color="vector(row.status)[1]">{{ vector(row.status)[0] }}</StatusPill>
        <span v-if="row.is_key_clause" class="key-clause-label">关键条款</span>
      </div>
      <h3>{{ row.questions || '未标注问法' }}</h3>
      <RecordFields :fields="fields" />
      <section class="data-full-answer">
        <div class="between">
          <h3>完整正文</h3>
          <span class="small muted">{{ row.answer.length }} 字</span>
        </div>
        <div class="data-detail-text">{{ row.answer }}</div>
      </section>
      <p class="field-hint section-gap">正文来自知识块详情接口。文档版本与发布生命周期尚无对应字段。</p>
    </template>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">知道了</button></div>
</template>
