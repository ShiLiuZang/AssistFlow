<!-- 索引状态：MySQL 与 Milvus 双写对账 + 知识库相关作业（预览、建库、向量化） -->
<script setup lang="ts">
import type { KbOverview } from '../../api/types'
import BarList from '../../components/BarList.vue'
import JobCard from '../../components/JobCard.vue'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import { contentTypeNames } from '../../utils/labels'
import { num } from '../../utils/format'

defineProps<{ overview?: KbOverview }>()
</script>

<template>
  <div class="grid-2">
    <Panel title="双写对账">
      <p v-if="!overview" class="muted">等待知识库概览…</p>
      <template v-else>
        <dl class="kv">
          <dt>MySQL 已向量化</dt>
          <dd>{{ num(overview.chunks.done) }} 块</dd>
          <dt>MySQL 待向量化</dt>
          <dd>{{ num(overview.chunks.pending) }} 块</dd>
          <dt>Milvus</dt>
          <dd>
            <template v-if="overview.milvus.online">{{ num(overview.milvus.count) }} 条 · 集合 {{ overview.milvus.collection }}</template>
            <template v-else>
              <Pill tone="red">离线</Pill>
              <div class="small muted">{{ overview.milvus.detail }}</div>
            </template>
          </dd>
          <dt>结论</dt>
          <dd>
            <Pill v-if="overview.consistent === true" tone="green">一致</Pill>
            <Pill v-else-if="overview.consistent === false" tone="amber">对不上</Pill>
            <Pill v-else>无法判断</Pill>
          </dd>
        </dl>
        <p class="notice section">
          数量一致只说明两边记录对得上，检索质量请在"检索自测"或"RAG 质量"页核对。有待向量化的块时，运行下方"向量化"作业补齐，不需要重新录入。
        </p>
      </template>
    </Panel>

    <Panel title="按类型分布">
      <BarList
        v-if="overview"
        :items="Object.entries(overview.chunks.by_content_type).map(([k, v]) => ({ label: contentTypeNames[k] ?? k, value: v }))"
      />
    </Panel>
  </div>

  <Panel title="知识库作业">
    <JobCard name="kb-preview" />
    <JobCard name="kb-build" />
    <JobCard name="kb-vectorize" />
  </Panel>
</template>

<style scoped>
.section {
  margin-top: 16px;
}
</style>
