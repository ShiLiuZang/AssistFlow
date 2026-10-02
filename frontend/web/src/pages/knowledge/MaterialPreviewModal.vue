<!-- 建库材料切块预览（对应 V2 previewMaterial）：只预览与查重，不写库 -->
<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { request } from '../../api/client'
import type { PreviewResult } from '../../api/types'
import VStat from '../../components/VStat.vue'
import { closeModal } from '../../composables/useModal'
import PreviewChunkHead from './PreviewChunkHead.vue'
import SourceFeatures from './SourceFeatures.vue'
import { num, typeName } from './state'

const props = defineProps<{ file: string }>()
const { data, error, isPending, refetch } = useQuery({
  queryKey: ['kb', 'material-preview', props.file],
  queryFn: async () => {
    const d = await request<PreviewResult>('/api/kb/preview', { method: 'POST', body: { file: props.file } })
    if (!Array.isArray(d.chunks) || !Number.isInteger(d.total) || d.total !== d.chunks.length) throw new Error('切块结果不完整，请重新预览。')
    return d
  },
  gcTime: 0,
})
</script>

<template>
  <div class="modal-body">
    <div v-if="isPending" class="empty" role="status">正在读取文件并预览切块…</div>
    <div v-else-if="error" class="data-empty-state compact">
      <h2>材料预览暂时不可用</h2>
      <p>{{ error.message }}</p>
      <button class="btn" @click="refetch()">重新预览</button>
    </div>
    <template v-else-if="data">
      <p class="mono muted">{{ data.source }} · {{ typeName(data.content_type) }}</p>
      <p class="field-hint">本次仅预览与查重，不写入知识库、不执行向量化。</p>
      <div class="stat-strip data-metrics">
        <VStat label="原文字符" :value="data.chars" unit="字" foot="当前文件内容" />
        <VStat label="切出块数" :value="data.total" unit="块" foot="预览尚未写入" />
        <VStat label="关键条款" :value="data.key_clause" unit="块" foot="完整保留的约束" />
        <VStat label="重复块" :value="data.dedup_known === true ? data.duplicates : '未知'" :unit="data.dedup_known === true ? '块' : ''" foot="与现有库存核对" />
      </div>
      <SourceFeatures :features="data.features" />
      <article v-for="row in data.chunks" :key="row.seq" class="data-preview-chunk" :class="{ 'is-key-clause': row.is_key_clause }">
        <PreviewChunkHead :row="row" />
        <p v-if="row.questions"><strong>问法</strong> {{ row.questions }}</p>
        <p>{{ row.answer }}</p>
        <div class="small muted">{{ num(row.chars) }} 字<template v-if="row.category"> · {{ row.category }}</template><template v-if="row.is_table"> · 表格</template></div>
      </article>
      <div v-if="!data.chunks.length" class="empty">材料中没有可切块的正文。</div>
    </template>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">关闭</button></div>
</template>
