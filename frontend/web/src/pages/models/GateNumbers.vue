<!-- 验收卡上的关键读数（对应 V2 gateNumbers） -->
<script setup lang="ts">
import { computed } from 'vue'
import type { AcceptanceData, AcceptanceErrors, AcceptanceEval, AcceptanceOverview, FileStat } from '../../api/types'
import { dec, formatted } from '../classification/shared'

const props = defineProps<{ gate: string; data?: AcceptanceData; evaluation?: AcceptanceEval; errors?: AcceptanceErrors; overview?: AcceptanceOverview }>()
const values = computed<[string, unknown][] | undefined>(() => {
  const { data, evaluation, errors, overview } = props
  const e = evaluation?.eval,
    s = evaluation?.scan,
    splits = data?.dataset?.splits || {}
  const countFile = (file?: FileStat) => (file?.present === true ? formatted(file.lines) : '—')
  const splitSize = (key: string) => (splits[key]?.file?.present === true ? formatted(splits[key].size) : '—')
  const validEval = e?.present === true,
    validScan = s?.present === true
  const report = data?.onnx?.report
  return (
    {
      data: [
        ['标注语料', countFile(data?.lineage?.find((f) => f.file === 'corpus_labeled.jsonl'))],
        ['训练集', splitSize('train')],
        ['验证 / 测试', splitSize('val') + ' / ' + splitSize('test')],
      ],
      train: [
        ['模型三件套', data?.model?.trio_ok === true ? '齐全' : data?.model?.trio_ok === false ? '未齐全' : '—'],
        ['文件阈值', data?.model?.threshold ?? '—'],
      ],
      export: [
        ['对齐预测', report?.present === true ? formatted(report.checked) : '—'],
        ['不一致', report?.present === true ? formatted(report.mismatch) : '—'],
        ['服务', overview?.classifier?.online === true ? '在线' : overview?.classifier?.online === false ? '离线' : '—'],
      ],
      eval: [
        ['micro-F1', validEval ? dec(e.micro?.f1) : '—'],
        ['macro-F1', validEval ? dec(e.macro?.f1) : '—'],
      ],
      threshold: [
        ['扫描推荐', validScan ? (s.best_threshold ?? '—') : '—'],
        ['文件在用', evaluation?.threshold_in_use ?? '—'],
      ],
      matrix: [
        ['多打 FP', validEval ? formatted(e.total_fp) : '—'],
        ['漏打 FN', validEval ? formatted(e.total_fn) : '—'],
      ],
      errors: [
        ['错例', errors?.eval?.present === true ? formatted(errors.errors?.length) : '—'],
        ['错误笔数', errors?.eval?.present === true ? formatted(errors.matrix_entries) : '—'],
      ],
    } as Record<string, [string, unknown][]>
  )[props.gate]
})
</script>

<template>
  <div v-if="values" class="cls-gate-numbers" :class="{ 'has-three': values.length === 3 }">
    <div v-for="[title, value] in values" :key="title">
      <span>{{ title }}</span><b>{{ value }}</b>
    </div>
  </div>
</template>
