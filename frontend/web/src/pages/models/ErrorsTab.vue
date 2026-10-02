<!-- 错例复核：错误类型、边界摩擦与逐条对照 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { ClassifierError } from '../../api/types'
import DataState from '../../components/DataState.vue'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import VTable from '../../components/VTable.vue'
import { openModal } from '../../composables/useModal'
import CompareTags from '../classification/CompareTags.vue'
import JobButtons from '../classification/JobButtons.vue'
import MetaRow from '../classification/MetaRow.vue'
import Note from '../classification/Note.vue'
import { trackTime, useCatalog, useClsErrors } from '../classification/queries'
import { formatted, local, missingText } from '../classification/shared'
import ErrorModal from './ErrorModal.vue'

const v = useClsErrors()
const catalog = useCatalog()
trackTime(v)
const d = computed(() => v.data.value)
const missing = computed(() => (d.value ? missingText(d.value.eval) : null))
const kinds = ['漏打', '多打', '错位']
const rows = computed(() =>
  (d.value?.errors || []).filter(
    (r) => (local.kind === 'all' || local.kind === r.kind) && `${r.text} ${(r.gold || []).join(' ')} ${(r.pred || []).join(' ')}`.includes(local.errorQuery),
  ),
)
const setKind = (k: string) => (local.kind = k)
const show = (row: ClassifierError) =>
  openModal({ title: '错例复核 · ' + row.kind, view: ErrorModal, props: { row, report: d.value!.eval, catalog: catalog.data.value }, cls: 'classification-dialog' })
</script>

<template>
  <DataState v-if="!d" :loading="v.isPending.value" :error="v.error.value" />
  <Note v-else-if="missing" alert>{{ missing }}</Note>
  <template v-else>
    <div class="stat-strip data-metrics">
      <VStat label="错例" :value="formatted(d.errors?.length)" unit="条" foot="同一句只算一条错例" />
      <VStat label="矩阵错误" :value="formatted(d.matrix_entries)" unit="笔" foot="错位可产生多笔标签错误" />
      <VStat label="多打 FP" :value="formatted(d.total_fp)" unit="笔" foot="错误命中的标签" />
      <VStat label="漏打 FN" :value="formatted(d.total_fn)" unit="笔" foot="未命中的标准标签" />
    </div>
    <VPanel title="错误类型 · 错例数与矩阵笔数分开看">
      <div class="panel-pad">
        <div class="cls-error-kinds">
          <article v-for="kind in kinds" :key="kind">
            <div class="between">
              <h3>{{ kind }}</h3>
              <strong>{{ formatted(d.kinds?.[kind]) }} <small>条</small></strong>
            </div>
            <p>{{ d.recipes?.[kind] || '未提供修正建议' }}</p>
          </article>
        </div>
        <MetaRow
          :items="[
            ['报告时间', d.eval.ran_at],
            ['测试样本', d.eval.test_size],
            ['评测阈值', d.eval.threshold],
          ]"
        />
        <JobButtons :jobs="['finetune-eval']" />
      </div>
    </VPanel>
    <VPanel title="边界摩擦 · 哪两类出现错位">
      <VTable :heads="['漏打类目', '多打类目', '同时出现', '漏打类档位']" :empty="!d.pairs?.length">
        <tr v-for="(p, i) in d.pairs ?? []" :key="i">
          <td><span class="cls-compare-tag missed">{{ p.missed }}</span></td>
          <td><span class="cls-compare-tag extra">{{ p.grabbed }}</span></td>
          <td>{{ formatted(p.count) }} 次</td>
          <td>{{ p.severity || '未标注' }}</td>
        </tr>
      </VTable>
      <p class="panel-pad field-hint">配对仅表示报告中的漏打与多打共现，为人工核对提供线索。</p>
    </VPanel>
    <VPanel title="逐条对照 · 标准标签与模型预测">
      <div class="panel-toolbar data-toolbar">
        <div class="data-filters">
          <button v-for="k in ['all', ...kinds]" :key="k" class="filter-chip" :class="{ active: local.kind === k }" :aria-pressed="local.kind === k" @click="setKind(k)">
            {{ k === 'all' ? '全部' : k }}{{ k !== 'all' ? ' ' + formatted(d.kinds?.[k]) : '' }}
          </button>
        </div>
        <label class="search"><Icon name="search" /><input id="cls-error-query" v-model="local.errorQuery" aria-label="筛选报告错例" placeholder="筛选当前报告" /></label>
      </div>
      <div class="cls-tag-legend"><span class="cls-compare-tag correct">正确命中</span><span class="cls-compare-tag missed">漏打</span><span class="cls-compare-tag extra">多打</span></div>
      <div id="cls-error-rows" class="cls-error-list">
        <article v-for="(r, i) in rows" :key="i" class="cls-error-card">
          <div class="between">
            <div>
              <StatusPill :color="r.kind === '错位' ? 'red' : 'amber'">{{ r.kind }}</StatusPill><span class="small muted">记 {{ formatted(r.matrix_entries) }} 笔矩阵错误</span>
            </div>
            <button class="btn" @click="show(r)">核对类目边界</button>
          </div>
          <h3>{{ r.text }}</h3>
          <div class="cls-error-labels">
            <div><span>标准标签</span><CompareTags :values="r.gold" :other="r.pred" missing /></div>
            <div><span>模型预测</span><CompareTags :values="r.pred" :other="r.gold" /></div>
          </div>
          <p class="field-hint">{{ r.missed?.length ? '漏打：' + r.missed.join('、') + '　' : '' }}{{ r.extra?.length ? '多打：' + r.extra.join('、') : '' }}</p>
          <p v-if="d.recipes?.[r.kind]" class="cls-error-recipe">建议：{{ d.recipes[r.kind] }}</p>
        </article>
        <div v-if="!rows.length" class="empty">当前报告没有匹配错例</div>
      </div>
      <div class="panel-pad"><JobButtons :jobs="['finetune-eval']" /></div>
    </VPanel>
  </template>
</template>
