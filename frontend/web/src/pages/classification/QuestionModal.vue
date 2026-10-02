<script setup lang="ts">
import type { TopicQuestion } from '../../api/types'
import ModalFoot from '../reports/ModalFoot.vue'
import MetaRow from './MetaRow.vue'
import Tags from './Tags.vue'
import { source } from './shared'
defineProps<{ row: TopicQuestion }>()
</script>

<template>
  <div class="modal-body">
    <Tags :values="row.labels" />
    <MetaRow
      :items="[
        ['来源', source(row.source)],
        ['出现次数', row.occurrence_count],
        ['提问时间', row.asked_at],
        ['归类时间', row.classified_at],
        ['规范化', row.normalized === true ? '是' : row.normalized === false ? '否' : '未提供'],
        ['审核状态', row.review_status || '未提供'],
      ]"
    />
    <h3>原始问法</h3>
    <div class="preview-text section-gap">{{ row.raw_question || '未提供' }}</div>
    <h3 class="section-gap">归类文本</h3>
    <div class="preview-text section-gap">{{ row.text || '未提供' }}</div>
  </div>
  <ModalFoot />
</template>
