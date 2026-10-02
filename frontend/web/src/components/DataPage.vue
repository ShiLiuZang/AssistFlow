<!-- 管理数据页骨架：标题与操作、业务内容、可展开的数据来源说明。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useIsFetching, useQueryClient } from '@tanstack/vue-query'
import Icon from './Icon.vue'
import { dataTime } from '../composables/useDataTime'
import { actionBusy, actionNotice } from '../composables/useAdminActions'

const props = defineProps<{ page: string; busy?: boolean }>()
const route = useRoute()
const client = useQueryClient()
const fetching = useIsFetching()

const desc: Record<string, string> = {
  knowledge: '维护回复依据，核对原文、审核与向量状态。',
  overview: '查看知识、质量与模型的当前状态，找到下一件需要处理的事。',
  review: '飞轮待审 · 从未解决的问题出发，核对依据，再确认可复用的答案。',
  jobs: '查看执行条件、运行状态与日志，回到业务页核对结果。',
  quality: '看策略、看逐题证据，分清检索结果与生成判断。',
  observability: '核对调用消耗、可比较评测与证据阈值。',
  topics: '看清问题分布，按权威类目核对完整问法与归类依据。',
  models: '核对数据、评测与产物，分别判断验收结果和服务状态。',
}
const sourceText = computed(() =>
  props.page === 'knowledge'
    ? '库存来自真实接口；原文录入、候选审核与向量补齐均需确认。'
    : '读取当前项目后端，库存、报告和服务状态分别查询。',
)

// 与 V2 一致：刷新读数会清空本页所有缓存并重新读取
function refresh() {
  if (props.busy || actionBusy.value) return
  client.invalidateQueries()
}
</script>

<template>
  <div class="page admin-page data-page" :data-page="page">
    <div class="page-title between">
      <div>
        <h1>{{ route.meta.title }}</h1>
        <p>{{ desc[page] }}</p>
      </div>
      <div class="page-actions">
        <button class="btn" :disabled="busy || actionBusy || fetching > 0" @click="refresh"><Icon name="clock" />刷新读数</button>
        <slot name="actions" />
      </div>
    </div>
    <div v-if="actionNotice" class="notice data-alert" role="status">{{ actionNotice }}</div>
    <slot />
    <details class="source-line data-source-details">
      <summary>数据来源与范围 · {{ dataTime ? `本次读取 ${dataTime}` : '等待读取' }}</summary>
      <p>{{ sourceText }}<template v-if="page === 'knowledge'">文档版本与发布生命周期尚无对应数据。</template></p>
    </details>
  </div>
</template>
