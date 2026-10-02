<!-- 数据与产物：语料血缘、三份数据集、模型文件与 ONNX 对齐 -->
<script setup lang="ts">
import { computed } from 'vue'
import DataState from '../../components/DataState.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import VTable from '../../components/VTable.vue'
import JobButtons from '../classification/JobButtons.vue'
import MetaRow from '../classification/MetaRow.vue'
import Note from '../classification/Note.vue'
import NumberBar from '../classification/NumberBar.vue'
import { trackTime, useClsData } from '../classification/queries'
import { filename, finite, formatted, missingText, origin, splitNames } from '../classification/shared'
import FileTable from './FileTable.vue'

const v = useClsData()
trackTime(v)
const d = computed(() => v.data.value)
const keys = ['train', 'val', 'test'] as const
const splits = computed(() => d.value?.dataset?.splits || {})
const complete = computed(() => keys.every((k) => splits.value[k]?.file?.present === true))
const leaks = computed(() => d.value?.dataset?.leaks || {})
const labeled = computed(() => (d.value?.lineage || []).find((f) => f.file === 'corpus_labeled.jsonl'))
const present = (key: string) => splits.value[key]?.file?.present === true
const allFiles = computed(() => [...(d.value?.model?.files || []), ...(d.value?.onnx?.files || []), ...(d.value?.sample_review ? [d.value.sample_review] : [])])
const datasetFiles = computed(() => keys.filter((k) => splits.value[k]?.file).map((k) => ({ ...splits.value[k].file, stage: splitNames[k] })))
const report = computed(() => d.value?.onnx?.report)
const reportMissing = computed(() => missingText(report.value))
const originText = (o?: Record<string, number>, sep = ' · ') =>
  Object.entries(o || {})
    .map(([k, n]) => origin(k) + ' ' + formatted(n) + ' 条')
    .join(sep)
const maxima = computed(() => Object.fromEntries(keys.map((k) => [k, Math.max(0, ...Object.values(splits.value[k]?.counts || {}).filter(finite))])))
const labels = computed(() => d.value?.topic_names || [...new Set(keys.flatMap((k) => Object.keys(splits.value[k]?.counts || {})))])
const leakRows = [
  ['train_val', '训练 ∩ 验证'],
  ['train_test', '训练 ∩ 测试'],
  ['val_test', '验证 ∩ 测试'],
] as const
const leakPill = (key: string): [string, string] => {
  const n = leaks.value[key]
  if (!complete.value) return ['尚不能核对', 'neutral']
  return [n === 0 ? '未发现重叠' : finite(n) ? '存在重叠' : '读数未知', n > 0 ? 'red' : n === 0 ? '' : 'neutral']
}
const cleanPill = computed(() => (!complete.value ? '文件未齐全' : d.value?.dataset?.clean === true ? '未发现相同文本' : d.value?.dataset?.clean === false ? '发现重叠' : '未知'))
</script>

<template>
  <DataState v-if="!d" :loading="v.isPending.value" :error="v.error.value" />
  <template v-else>
    <div class="stat-strip data-metrics">
      <VStat label="标注语料" :value="formatted(labeled?.present ? labeled.lines : null)" unit="条" foot="形成数据集的输入" />
      <VStat
        v-for="key in keys"
        :key="key"
        :label="splitNames[key]"
        :value="formatted(present(key) ? splits[key].size : null)"
        unit="条"
        :foot="`多标签 ${formatted(present(key) ? splits[key].multi_label : null)} 条`"
      />
    </div>
    <VPanel title="语料血缘 · 从问题到数据集">
      <div class="panel-pad">
        <div class="cls-lineage">
          <article v-for="(f, i) in d.lineage || []" :key="i">
            <span>{{ f.stage || '未标注阶段' }}</span><strong>{{ f.present === true ? formatted(f.lines) : '—' }}</strong>
            <p>{{ f.desc || '未提供说明' }}</p>
            <small class="mono">{{ f.file || filename(f.path) }}</small>
          </article>
          <article>
            <span>训练 / 验证 / 测试</span><strong class="cls-split-total">{{ keys.map((k) => (present(k) ? formatted(splits[k].size) : '—')).join(' / ') }}</strong>
            <p>只增强训练集，验证与测试用于留出核对。</p>
            <small class="mono">dataset/*.jsonl</small>
          </article>
        </div>
        <MetaRow :items="[['标注语料来源', originText(d.corpus_origins, '；') || '未提供']]" />
        <JobButtons :jobs="['finetune-corpus', 'finetune-dataset']" />
      </div>
      <FileTable :heads="['产物 / 阶段', '文件状态', '大小', '记录行数', '更新时间', '操作']" :files="d.lineage || []" />
    </VPanel>
    <VPanel title="三份数据集 · 泄漏自检与标签分布">
      <template #extra><StatusPill :color="d.dataset?.clean === false ? 'red' : 'neutral'">{{ cleanPill }}</StatusPill></template>
      <div class="panel-pad">
        <div class="cls-leakage">
          <article v-for="[key, title] in leakRows" :key="key" :class="{ 'is-error': complete && finite(leaks[key]) && leaks[key] > 0 }">
            <span>{{ title }}</span><strong>{{ formatted(complete ? leaks[key] : null) }} <small>条</small></strong><StatusPill :color="leakPill(key)[1]">{{ leakPill(key)[0] }}</StatusPill>
          </article>
        </div>
        <div class="cls-split-origins">
          <article v-for="(split, key) in splits" :key="key">
            <strong>{{ splitNames[key] || key }}</strong>
            <p>多标签 {{ formatted(split.file?.present === true ? split.multi_label : null) }} 条</p>
            <small>{{ originText(split.origins) || '来源未提供' }}</small>
          </article>
        </div>
        <p class="field-hint section-gap">重叠只核对完全相同文本。多标签样本可计入多个类目；柱长分别按各列最多类目缩放，数字为实际样本数。</p>
      </div>
      <div class="cls-distribution-table">
        <VTable :heads="['类目', ...keys.map((k) => ({ train: '训练', val: '验证', test: '测试' })[k] + ' · ' + (present(k) ? formatted(splits[k]?.size) : '—'))]" :empty="!labels.length">
          <tr v-for="label in labels" :key="label">
            <td>{{ label }}</td>
            <td v-for="k in keys" :key="k"><NumberBar :value="present(k) ? splits[k]?.counts?.[label] : null" :max="maxima[k]" :precision="false" /></td>
          </tr>
        </VTable>
      </div>
      <FileTable :heads="['数据集文件', '文件状态', '大小', '记录行数', '更新时间', '操作']" :files="datasetFiles" />
      <div class="panel-pad"><JobButtons :jobs="['finetune-dataset']" /></div>
    </VPanel>
    <VPanel title="模型、推理与复核文件">
      <div class="panel-pad">
        <MetaRow
          :items="[
            ['模型三件套', d.model?.trio_ok === true ? '齐全' : d.model?.trio_ok === false ? '未齐全' : '未知'],
            ['文件在用阈值', d.model?.threshold],
          ]"
        />
        <JobButtons :jobs="['finetune-train', 'finetune-export', 'classifier-up']" />
      </div>
      <FileTable :heads="['产物', '文件状态', '大小', '文本行数', '更新时间', '操作']" :files="allFiles" />
    </VPanel>
    <VPanel title="ONNX 导出对齐报告">
      <div class="panel-pad">
        <Note v-if="reportMissing" alert>{{ reportMissing }}</Note>
        <MetaRow
          v-else-if="report"
          :items="[
            ['报告时间', report.ran_at],
            ['核对预测', report.checked],
            ['不一致', report.mismatch],
            ['对齐结论', report.passed === true ? '通过' : report.passed === false ? '未通过' : '未知'],
            ['产物路径', report.onnx_path],
            ['Opset', report.opset],
          ]"
        />
        <p class="field-hint">文件存在、对齐报告、服务在线和质量达标分别核对。</p>
        <JobButtons :jobs="['finetune-export']" />
      </div>
    </VPanel>
  </template>
</template>
