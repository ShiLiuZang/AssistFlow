<!-- 错例复核：标准与预测标签、权威类目边界 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { AcceptanceErrors, ClassifierError, TopicCatalog } from '../../api/types'
import ModalFoot from '../reports/ModalFoot.vue'
import MetaRow from '../classification/MetaRow.vue'
import Note from '../classification/Note.vue'
import Tags from '../classification/Tags.vue'
const props = defineProps<{ row: ClassifierError; report: AcceptanceErrors['eval']; catalog?: TopicCatalog | null }>()
const groups = computed(() => [
  ['标准标签', props.row.gold],
  ['预测标签', props.row.pred],
  ['漏打', props.row.missed],
  ['多打', props.row.extra],
] as const)
const labels = computed(() => [...new Set([...(props.row.gold || []), ...(props.row.pred || [])])])
</script>

<template>
  <div class="modal-body">
    <div class="preview-text">{{ row.text }}</div>
    <MetaRow
      :items="[
        ['错误笔数', row.matrix_entries],
        ['报告时间', report.ran_at],
        ['评测阈值', report.threshold],
      ]"
    />
    <div class="report-detail-grid">
      <section v-for="[t, l] in groups" :key="t">
        <h3>{{ t }}</h3>
        <div class="section-gap"><Tags :values="l" /></div>
      </section>
    </div>
    <h3 class="section-gap">权威类目边界</h3>
    <template v-if="catalog">
      <p v-for="lb in labels" :key="lb" class="cls-recipe">
        <strong>{{ lb }}</strong>{{ catalog.classes?.find((x) => x.label === lb)?.boundary || '未提供' }}
      </p>
    </template>
    <Note v-else>类目定义暂不可读取，不推造边界。</Note>
    <p class="field-hint section-gap">只核对保存报告，没有提交补数或复训。</p>
  </div>
  <ModalFoot />
</template>
