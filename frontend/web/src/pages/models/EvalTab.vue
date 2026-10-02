<!-- 评测与阈值：总分、各类红线、阈值扫描、每类二元混淆矩阵 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { ClassMetric } from '../../api/types'
import DataState from '../../components/DataState.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import VTable from '../../components/VTable.vue'
import JobButtons from '../classification/JobButtons.vue'
import MetaRow from '../classification/MetaRow.vue'
import Note from '../classification/Note.vue'
import NumberBar from '../classification/NumberBar.vue'
import { trackTime, useClsEval } from '../classification/queries'
import { dec, finite, formatted, missingText, num, origin } from '../classification/shared'

defineEmits<{ tab: [key: string] }>()
const v = useClsEval()
trackTime(v)
const d = computed(() => v.data.value)
const e = computed(() => d.value?.eval)
const s = computed(() => d.value?.scan)
const missing = computed(() => missingText(e.value))
const scanMissing = computed(() => missingText(s.value))
const scorePairs = [
  ['micro', '所有标签判断汇总'],
  ['macro', '17 类分别计算，再平均'],
] as const
const scoreKeys = [
  ['p', '精确率 P'],
  ['r', '召回率 R'],
  ['f1', 'F1'],
] as const
const cells = [
  ['tn', 'TN · 正确排除'],
  ['fp', 'FP · 多打'],
  ['fn', 'FN · 漏打'],
  ['tp', 'TP · 命中'],
] as const
const hasErrors = (c: ClassMetric) => (finite(c.fp) && c.fp > 0) || (finite(c.fn) && c.fn > 0)
const cellClass = (c: ClassMetric, key: string) =>
  key === 'tp' ? 'is-correct' : (key === 'fp' || key === 'fn') && finite(c[key]) && (c[key] as number) > 0 ? 'is-error' : ''
const redLine = (c: ClassMetric) => dec(c.red_line) + (c.passed === true ? ' · 达标' : c.passed === false ? ' · 未达标' : ' · 待核对')
const originText = computed(() =>
  Object.entries(e.value?.origin_counts || {})
    .map(([k, n]) => origin(k) + ' ' + n + ' 条')
    .join('；'),
)
const current = computed(() => d.value?.threshold_in_use)
</script>

<template>
  <DataState v-if="!d" :loading="v.isPending.value" :error="v.error.value" />
  <template v-else>
    <div v-if="!missing && e" class="stat-strip data-metrics">
      <VStat label="测试集" :value="formatted(e.test_size)" unit="条" :foot="`真实提问 ${formatted(e.real_subset?.size)} 条`" />
      <VStat label="评测阈值" :value="e.threshold" :foot="`文件在用 ${d.threshold_in_use ?? '—'}`" />
      <VStat label="micro-F1" :value="dec(e.micro?.f1)" foot="汇总全部标签判断" />
      <VStat label="macro-F1" :value="dec(e.macro?.f1)" foot="各类指标平均" />
    </div>
    <VPanel title="总分 · micro 与 macro 一起看">
      <div class="panel-pad">
        <Note v-if="missing" alert>{{ missing }}</Note>
        <div v-else class="cls-score-pair">
          <article v-for="[key, desc] in scorePairs" :key="key">
            <div class="between">
              <h3>{{ key }}</h3>
              <small>{{ desc }}</small>
            </div>
            <div class="cls-score-numbers">
              <div v-for="[k, title] in scoreKeys" :key="k">
                <strong>{{ dec(e?.[key]?.[k]) }}</strong><span>{{ title }}</span>
              </div>
            </div>
          </article>
        </div>
        <p class="field-hint section-gap">micro 汇总全部标签判断；macro 对各类指标分别平均。整体成绩不能代替单类红线。</p>
        <JobButtons :jobs="['finetune-eval']" />
      </div>
    </VPanel>
    <VPanel title="各类指标与容错红线">
      <div v-if="missing" class="panel-pad"><Note alert>{{ missing }}</Note></div>
      <template v-else-if="e">
        <div class="panel-pad">
          <Note :alert="e.red_line_passed === false">{{
            e.red_line_passed === true ? '报告中的类目红线全部达标。' : e.red_line_passed === false ? '有类目跌破红线，请先核对红色行及错例。' : '未返回红线结论。'
          }}</Note>
          <MetaRow
            :items="[
              ['评测时间', e.ran_at],
              ['真实子集 micro-F1', dec(e.real_subset?.micro_f1)],
              ['来源', originText || '未提供'],
            ]"
          />
        </div>
        <div class="cls-eval-table">
          <VTable :heads="['类目 / 档位', '精确率 P', '召回率 R', 'F1', '正例 support', 'F1 红线']" :empty="!e.classes?.length">
            <tr v-for="c in e.classes ?? []" :key="c.name" :class="{ 'cls-failed': c.passed === false }">
              <td>
                <strong>{{ c.name }}</strong
                ><span class="table-sub"><StatusPill :color="c.severity === '严' ? '' : 'neutral'">{{ (c.severity || d.severity?.[c.name] || '未标注') + '档' }}</StatusPill></span>
              </td>
              <td><NumberBar :value="c.p" /></td>
              <td><NumberBar :value="c.r" /></td>
              <td><NumberBar :value="c.f1" :alert="c.passed === false" /></td>
              <td>{{ formatted(c.support) }}</td>
              <td>
                <StatusPill v-if="c.red_line == null" color="neutral">无单类红线</StatusPill>
                <StatusPill v-else :color="c.passed === false ? 'red' : c.passed === true ? '' : 'neutral'">{{ redLine(c) }}</StatusPill>
              </td>
            </tr>
          </VTable>
        </div>
      </template>
    </VPanel>
    <VPanel title="判定阈值 · 验证集候选线扫描">
      <template v-if="!scanMissing && s" #extra>
        <StatusPill :color="s.consistent === false ? 'amber' : 'neutral'">{{
          s.consistent === true ? '扫描报告与当时在用一致' : s.consistent === false ? '扫描报告存在差异' : '一致性未提供'
        }}</StatusPill>
      </template>
      <div class="panel-pad">
        <Note v-if="scanMissing" alert>{{ scanMissing }}</Note>
        <template v-else-if="s">
          <MetaRow
            :items="[
              ['扫描时间', s.ran_at],
              ['验证集', s.val_size],
              ['扫描推荐', s.best_threshold],
              ['文件在用', d.threshold_in_use],
            ]"
          />
          <div class="cls-scan-bars">
            <div v-for="row in s.scan ?? []" :key="row.threshold" class="cls-scan-row" :class="{ recommended: row.threshold === s.best_threshold }">
              <strong>{{ finite(row.threshold) ? row.threshold.toFixed(2) : '—' }}</strong><NumberBar :value="row.micro_f1" /><span class="cls-scan-markers"
                ><StatusPill v-if="row.threshold === s.best_threshold">扫描推荐</StatusPill><StatusPill v-if="finite(current) && row.threshold === current" color="neutral">文件在用</StatusPill></span
              >
            </div>
            <div v-if="!s.scan?.length" class="empty">没有候选线记录</div>
          </div>
          <p class="field-hint section-gap">柱长为验证集 micro-F1（0–1）。推荐值与当前文件分别标记；本页不自动应用阈值。</p>
          <details class="cls-scan-detail">
            <summary>查看各候选线 TP / FP / FN</summary>
            <VTable :heads="['阈值', 'micro-F1', 'TP', 'FP', 'FN']" :empty="!s.scan?.length">
              <tr v-for="r in s.scan ?? []" :key="r.threshold">
                <td>{{ num(r.threshold) }}</td>
                <td>{{ dec(r.micro_f1) }}</td>
                <td>{{ formatted(r.tp) }}</td>
                <td>{{ formatted(r.fp) }}</td>
                <td>{{ formatted(r.fn) }}</td>
              </tr>
            </VTable>
          </details>
        </template>
        <JobButtons :jobs="['finetune-threshold-scan']" />
      </div>
    </VPanel>
    <VPanel v-if="!missing && e" title="每类二元混淆矩阵">
      <div class="panel-pad">
        <MetaRow
          :items="[
            ['标签判断', formatted(e.total_cells)],
            ['多打 FP', formatted(e.total_fp)],
            ['漏打 FN', formatted(e.total_fn)],
          ]"
        />
        <p class="field-hint">每类独立统计四格；错位可同时计入一次 FP 与一次 FN，不是 17 × 17 单标签混淆矩阵。</p>
        <div class="cls-matrices">
          <article v-for="c in e.classes ?? []" :key="c.name" class="cls-matrix">
            <header :class="{ 'has-errors': hasErrors(c) }">
              <strong>{{ c.name }}</strong><StatusPill :color="c.severity === '严' ? '' : 'neutral'">{{ c.severity || '档位未标注' }}</StatusPill>
            </header>
            <div>
              <section v-for="[key, title] in cells" :key="key" :class="cellClass(c, key)">
                <b>{{ formatted(c[key]) }}</b><span>{{ title }}</span>
              </section>
            </div>
          </article>
        </div>
        <div class="form-actions section-gap"><button class="btn soft" @click="$emit('tab', 'errors')">查看完整错例</button></div>
        <JobButtons :jobs="['finetune-eval']" />
      </div>
    </VPanel>
  </template>
</template>
