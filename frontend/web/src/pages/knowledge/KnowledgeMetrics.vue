<!-- 知识库存统计条（对应 V2 knowledgeMetrics） -->
<script setup lang="ts">
import { computed } from 'vue'
import type { KbOverview } from '../../api/types'
import VStat from '../../components/VStat.vue'

const props = defineProps<{ data: Partial<KbOverview> }>()
const s = computed(() => props.data.chunks ?? ({} as Partial<KbOverview['chunks']>))
const v = computed(() => props.data.milvus ?? ({} as Partial<KbOverview['milvus']>))
const c = computed(() => props.data.consistent)
const verdict = computed(() => (c.value === true ? '一致' : c.value === false ? '对不上' : '未知'))
const note = computed(() =>
  c.value === true
    ? '数量一致不代表检索合格'
    : c.value === false
      ? '有待补块或两端数量不同'
      : props.data.db_error
        ? '原文统计不可读，暂不下结论'
        : v.value.online === false
          ? '向量库离线，暂不下结论'
          : '数量读数未知，暂不下结论',
)
const consistency = computed(() => (c.value === true ? 'consistent' : c.value === false ? 'mismatch' : 'unknown'))
</script>

<template>
  <div class="stat-strip data-metrics data-knowledge-metrics" role="group" aria-label="知识库存统计" :data-consistency="consistency">
    <VStat label="知识块总数" :value="s.total" unit="块" foot="数据库原文记录（MySQL）" />
    <VStat label="已向量化" :value="s.done" unit="块" foot="MySQL 中标记已向量化" />
    <VStat label="待向量化" :value="s.pending" unit="块" foot="保留原文，等待补齐" />
    <VStat label="关键条款" :value="s.key_clause" unit="块" foot="需完整保留的约束" />
    <VStat
      label="Milvus 条数"
      :value="v.online === true ? v.count : v.online === false ? '离线' : null"
      :unit="v.online === true && v.count != null ? '条' : ''"
      :foot="v.online === true ? '向量库实际记录数' : v.online === false ? '向量库连接不可用' : '向量库状态未知'"
    />
    <VStat label="双写核对" :value="verdict" :foot="note" />
  </div>
</template>
