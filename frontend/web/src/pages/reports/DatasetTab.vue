<!-- 当前固定题集 -->
<script setup lang="ts">
import type { UseQueryReturnType } from '@tanstack/vue-query'
import type { EvalCase } from '../../api/types'
import DataState from '../../components/DataState.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VTable from '../../components/VTable.vue'
import { openModal } from '../../composables/useModal'
import CaseModal from './CaseModal.vue'
import ReportEmpty from './ReportEmpty.vue'
import { invalidateTrial, trial } from './state'

defineProps<{ query: UseQueryReturnType<{ cases: EvalCase[] }, Error> }>()
const emit = defineEmits<{ try: [] }>()
function tryCase(item: EvalCase) {
  if (trial.busy) return
  trial.query = item.query
  invalidateTrial()
  emit('try')
}
const showCase = (item: EvalCase) => openModal({ title: '固定题目标准', view: CaseModal, props: { item } })
</script>

<template>
  <DataState v-if="!query.data.value" :loading="query.isPending.value" :error="query.error.value" />
  <ReportEmpty v-else-if="!Array.isArray(query.data.value.cases)" title="固定题集不可读取" description="接口未返回题目列表，请检查数据文件后重新读取。" />
  <template v-else>
    <div class="notice report-note">这里是当前固定题集，可能与旧报告不同。逐题结果中的标准依据仅使用报告保存的题集快照；未保存时显示“未提供”。</div>
    <VPanel title="当前固定题集">
      <template #extra><StatusPill color="neutral">{{ query.data.value.cases.length }} 题</StatusPill></template>
      <VTable :heads="['题目', '应答标准', '证据组', '预期关键词', '操作']" :empty="!query.data.value.cases.length">
        <tr v-for="row in query.data.value.cases" :key="row.id">
          <td class="data-content-cell"><strong>{{ row.query || '未标注问题' }}</strong><span class="table-sub mono">{{ row.id }}</span></td>
          <td>
            <StatusPill v-if="row.should_refuse === true" color="amber">应拒答</StatusPill><StatusPill v-else-if="row.should_refuse === false">可回答</StatusPill
            ><StatusPill v-else color="neutral">未标注</StatusPill>
          </td>
          <td>{{ Array.isArray(row.groups) ? row.groups.length : '—' }} 组</td>
          <td>{{ (row.expected_terms || []).join('、') || '无预期关键词' }}</td>
          <td>
            <div class="form-actions">
              <button class="btn soft" @click="tryCase(row)">试问</button><button class="btn" @click="showCase(row)">查看标准</button>
            </div>
          </td>
        </tr>
      </VTable>
    </VPanel>
  </template>
</template>
