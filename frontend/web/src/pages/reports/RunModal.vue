<script setup lang="ts">
import type { EvalRun } from '../../api/types'
import VTable from '../../components/VTable.vue'
import ModalFoot from './ModalFoot.vue'
import ReportMeta from './ReportMeta.vue'
import { decimal, percent } from './state'
defineProps<{ run: EvalRun }>()
</script>

<template>
  <div class="modal-body">
    <h3 class="mono">RUN-{{ run.id }}</h3>
    <ReportMeta
      :items="[
        ['记录时间', run.created_at?.replace('T', ' ')],
        ['数据集', run.dataset_version],
        ['配置版本', run.config_version],
        ['知识修订', run.kb_revision],
        ['触发来源', run.triggered_by],
      ]"
    />
    <p class="field-hint">题目 ID：{{ run.case_ids?.join('、') || '未提供' }}</p>
    <div class="section-gap">
      <VTable :heads="['问题', '标准', '召回率', 'RR', '生成结果', '错误']" :empty="!run.details?.length">
        <tr v-for="(item, i) in run.details ?? []" :key="i">
          <td class="data-content-cell">{{ item.query || item.id }}</td>
          <td>{{ item.should_refuse ? '应拒答' : '可回答' }}</td>
          <td>{{ item.error ? '调用失败' : percent(item.recall) }}</td>
          <td>{{ item.error ? '调用失败' : decimal(item.rr) }}</td>
          <td class="report-answer-cell">{{ item.answer ?? '未提供' }}</td>
          <td>{{ item.error || '—' }}</td>
        </tr>
      </VTable>
    </div>
    <p class="field-hint section-gap">缺失的忠实度指标未评估；关键词覆盖率不能替代忠实度。</p>
  </div>
  <ModalFoot />
</template>
