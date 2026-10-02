<!-- 索引状态（对应 V2 indexPage）：原文与向量对账 + 向量补齐作业 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { UseQueryReturnType } from '@tanstack/vue-query'
import type { KbOverview } from '../../api/types'
import DataState from '../../components/DataState.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import VectorJobPanel from './VectorJobPanel.vue'
import { num, typeName } from './state'

const props = defineProps<{ overview: UseQueryReturnType<KbOverview, Error> }>()
const router = useRouter()
const data = computed(() => props.overview.data.value)
const label = computed(() =>
  data.value?.consistent === true ? '两端数量一致' : data.value?.consistent === false ? '仍有待补向量或数量不一致' : '暂无法核对',
)
const toPending = () => router.replace({ query: { tab: 'content', status: 'pending' } })
</script>

<template>
  <DataState :loading="overview.isPending.value" :error="overview.error.value" />
  <template v-if="data">
    <div class="stat-strip data-metrics">
      <VStat label="数据库知识块" :value="data.chunks.total" unit="块" foot="保存原文和元数据" />
      <VStat label="已向量化" :value="data.chunks.done" unit="块" foot="已完成向量化" />
      <VStat label="待向量化" :value="data.chunks.pending" unit="块" foot="可补齐，无需重录" />
      <VStat label="向量库记录" :value="data.milvus.online ? data.milvus.count : null" unit="条" :foot="data.milvus.online ? 'Milvus 返回的数量' : '向量库当前不可用'" />
    </div>
    <div class="data-status-grid">
      <VPanel title="原文与向量">
        <div class="panel-pad">
          <div class="data-status-title">
            <StatusPill :color="data.db_error ? 'red' : ''">{{ data.db_error ? '原文读取失败' : '原文数据库可读' }}</StatusPill>
            <StatusPill :color="data.milvus.online ? '' : 'amber'">{{ data.milvus.online ? '向量库在线' : '向量库离线' }}</StatusPill>
          </div>
          <h3>{{ label }}</h3>
          <p class="muted section-gap">数量一致是库存检查，检索质量需要单独自测。</p>
          <div class="form-actions">
            <button class="btn soft" @click="router.replace({ query: { tab: 'search' } })">检索自测</button>
            <button class="btn" @click="toPending">查看待向量化原文</button>
          </div>
        </div>
      </VPanel>
      <VPanel title="按内容类型">
        <div class="panel-pad data-type-breakdown">
          <div v-for="(count, key) in data.chunks.by_content_type" :key="key" class="between">
            <span>{{ typeName(String(key)) }}</span><strong>{{ num(count) }} <small class="muted">块</small></strong>
          </div>
          <p v-if="!Object.keys(data.chunks.by_content_type ?? {}).length" class="muted">暂无可读取的类型统计</p>
        </div>
      </VPanel>
    </div>
    <div class="section-gap"><VectorJobPanel :data="data" /></div>
  </template>
</template>
