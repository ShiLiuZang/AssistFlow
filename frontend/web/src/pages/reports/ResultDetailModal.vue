<!-- 逐题评估依据（对应 V2 showResult） -->
<script setup lang="ts">
import type { EvalCase, EvalDetail } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import EvidenceGroups from './EvidenceGroups.vue'
import ModalFoot from './ModalFoot.vue'
import ReportMeta from './ReportMeta.vue'
import { decimal, finite, judge, name, percent, type Outcome } from './state'

defineProps<{ row: EvalDetail; item?: EvalCase; generation?: boolean | null; outcome: Outcome }>()
</script>

<template>
  <div class="modal-body">
    <div class="data-detail-meta">
      <StatusPill color="neutral">{{ name(row.strategy) }}</StatusPill><StatusPill :color="outcome[2]">{{ outcome[1] }}</StatusPill
      ><StatusPill color="neutral">已保存报告</StatusPill>
    </div>
    <h3>{{ row.query }}</h3>
    <ReportMeta
      :items="[
        ['题目 ID', row.id],
        ['标准判断', judge(row.should_refuse)],
        ['召回率', row.error ? '调用失败' : percent(row.recall)],
        ['RR', row.error ? '调用失败' : decimal(row.rr)],
      ]"
    />
    <div v-if="row.error" class="notice report-note amber" role="alert">本次调用失败：{{ row.error }}。报告中的默认零分保留，但这里单独标明调用失败。</div>
    <div class="report-detail-grid">
      <section>
        <h3>标准证据组</h3>
        <EvidenceGroups :item="item" />
        <p class="field-hint section-gap">预期关键词：{{ item?.expected_terms?.join('、') || '未提供' }}</p>
        <h3 class="section-gap">本次召回内容</h3>
        <template v-if="Array.isArray(row.hits)">
          <article v-for="(hit, i) in row.hits" :key="i" class="report-hit">
            <div class="between">
              <strong>{{ i + 1 }}. {{ hit.section_path || '未标注章节' }}</strong><span class="mono muted">{{ finite(hit.score) ? decimal(hit.score) : '—' }}</span>
            </div>
            <p>{{ hit.question || hit.questions || '' }}</p>
            <div class="preview-text">{{ hit.answer || hit.text || '未提供正文' }}</div>
            <p v-if="hit.rerank_score != null" class="field-hint">重排分数 {{ decimal(hit.rerank_score) }}</p>
          </article>
          <p v-if="!row.hits.length" class="field-hint">检索执行完成，没有召回内容。</p>
        </template>
        <p v-else class="field-hint">报告没有保存召回内容，不能视为检索无命中。</p>
      </section>
      <section>
        <h3>生成回答</h3>
        <div class="preview-text section-gap">
          {{ row.answer ?? (generation === false ? '本报告仅评估检索，未生成回答。' : row.error ? '调用失败，未取得生成结果。' : '报告未提供生成回答。') }}
        </div>
        <div class="detail-row"><span>实际拒答</span><span>{{ row.refused === true ? '是' : row.refused === false ? '否' : '未提供' }}</span></div>
        <div class="detail-row">
          <span>拒答判断正确</span><span>{{ row.error ? '调用失败' : row.refusal_correct === true ? '是' : row.refusal_correct === false ? '否' : '未评估' }}</span>
        </div>
        <div class="detail-row"><span>关键词覆盖</span><span>{{ row.error ? '调用失败' : percent(row.coverage, '未评估') }}</span></div>
        <p class="field-hint section-gap">生成结果与标准判断分开显示。当前只读报告，未创建人工确认或解决记录。</p>
      </section>
    </div>
  </div>
  <ModalFoot />
</template>
