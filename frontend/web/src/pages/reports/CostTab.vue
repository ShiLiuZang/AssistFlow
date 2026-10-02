<!-- 意图消耗：已知 Token 分布与调用消耗明细 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { CostBlock, CostRow } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import VTable from '../../components/VTable.vue'
import { openModal } from '../../composables/useModal'
import CostModal from './CostModal.vue'
import PriceList from './PriceList.vue'
import { count, finite, percent, reportTime } from './state'

const props = defineProps<{ data: CostBlock }>()
const summary = computed(() => props.data.summary ?? {})
const meta = computed(() => props.data.meta ?? {})
const items = computed(() => props.data.rows ?? [])
const total = computed(() =>
  finite(summary.value.known_input_tokens) && finite(summary.value.known_output_tokens) ? summary.value.known_input_tokens + summary.value.known_output_tokens : null,
)
const tokens = (row: CostRow) => (finite(row.input_tokens) && finite(row.output_tokens) ? row.input_tokens + row.output_tokens : null)
const share = (row: CostRow) => {
  const known = tokens(row)
  return finite(total.value) && total.value > 0 && finite(known) ? known / total.value : null
}
const width = (row: CostRow) => {
  const s = share(row)
  return `${s == null ? 0 : Math.max(0, Math.min(100, 100 * s))}%`
}
const showRow = (row: CostRow) => openModal({ title: '调用与估算口径', view: CostModal, props: { row } })
</script>

<template>
  <div class="report-cost-view">
    <div class="stat-strip data-metrics report-cost-metrics">
      <VStat label="请求数" :value="count(summary.requests)" unit="次" foot="按 trace 去重" />
      <VStat label="模型生成" :value="count(summary.generations)" unit="次" foot="同一请求可多次调用" />
      <VStat label="已知 Token" :value="count(total)" :foot="`输入 ${count(summary.known_input_tokens)} · 输出 ${count(summary.known_output_tokens)}`" />
      <VStat label="未定价调用" :value="count(summary.unpriced)" unit="次" :foot="`用量未知 ${count(summary.unknown_usage)} 次`" />
    </div>
    <VPanel title="按意图的已知 Token 分布">
      <template #extra>
        <StatusPill :color="summary.usage_complete === false ? 'amber' : 'neutral'">{{ summary.usage_complete === false ? '部分用量未知' : '已知用量分布' }}</StatusPill>
      </template>
      <div class="panel-pad">
        <div v-for="row in items" :key="row.intent" class="report-intent-bar">
          <div class="between">
            <span
              ><strong>{{ row.intent }}</strong><small>{{ count(row.requests) }} 次请求 · {{ count(row.generations) }} 次生成</small></span
            ><b>{{ share(row) == null ? '—' : percent(share(row)) }} · {{ count(tokens(row)) }} Token</b>
          </div>
          <div class="report-token-track" aria-hidden="true"><i :style="{ width: width(row) }"></i></div>
        </div>
        <div v-if="!items.length" class="empty">尚无意图用量记录</div>
      </div>
    </VPanel>
    <VPanel title="调用消耗明细">
      <template #extra>
        <StatusPill v-if="summary.estimate_complete === true">估算完整</StatusPill>
        <StatusPill v-else-if="summary.estimate_complete === false" color="amber">估算不完整</StatusPill>
        <StatusPill v-else color="neutral">完整性未知</StatusPill>
      </template>
      <div class="report-cost-table">
        <VTable :heads="['意图', '请求', '生成', '输入 Token', '输出 Token', '未知 / 未定价', '费用估算', '生成 P95', '操作']" :empty="!items.length">
          <tr v-for="row in items" :key="row.intent">
            <td><strong>{{ row.intent }}</strong></td>
            <td>{{ count(row.requests) }}</td>
            <td>{{ count(row.generations) }}</td>
            <td>{{ count(row.input_tokens) }}</td>
            <td>{{ count(row.output_tokens) }}</td>
            <td>{{ count(row.unknown_usage) }} / {{ count(row.unpriced) }}</td>
            <td><PriceList :row="row" /><StatusPill v-if="row.estimate_complete === false" color="amber">估算不完整</StatusPill></td>
            <td>{{ finite(row.p95_generation_ms) ? count(Math.round(row.p95_generation_ms)) + ' ms' : '—' }}</td>
            <td><button class="btn" @click="showRow(row)">口径</button></td>
          </tr>
        </VTable>
      </div>
      <details class="report-cost-notes">
        <summary>数据来源与估算口径 · {{ meta.source || '未标注' }} · {{ reportTime(meta.generated_at) }}</summary>
        <p>范围为报表输入中的已保存生成记录。柱条表示各意图已知输入与输出 Token 之和占已知总量的比例，不含未知用量。</p>
        <p>费用按币种分别展示，不跨币种相加；只按已知用量与配置价格估算，不代表实际账单或缓存计费。</p>
        <p>{{ data.hint || '生成 P95 仅表示有耗时记录的模型生成时间，不是整轮响应时间。' }}缺失读数显示 —。</p>
      </details>
    </VPanel>
  </div>
</template>
