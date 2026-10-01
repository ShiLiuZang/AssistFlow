<!-- 候选问答：从历史对话挖出的问答，人工核对可信材料后批准入库或驳回 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { approveStaging, getStaging, listStaging, rejectStaging } from '../../api/endpoints'
import type { StagingStatus } from '../../api/types'
import AppDialog from '../../components/AppDialog.vue'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import StateBlock from '../../components/StateBlock.vue'
import { confirm } from '../../composables/useConfirm'
import { useUrlState } from '../../composables/useUrlState'
import { errorText, toast } from '../../composables/useToast'
import { stagingStatus } from '../../utils/labels'
import { dateTime, DASH } from '../../utils/format'

const client = useQueryClient()
const view = useUrlState('stage', 'kept')
const { data, error, isPending, refetch } = useQuery({ queryKey: ['kb', 'staging'], queryFn: () => listStaging(50) })

const rows = computed(() => data.value?.rows[view.value as StagingStatus] ?? [])
const selected = ref<number[]>([])
watch(view, () => (selected.value = []))
const allChecked = computed(() => rows.value.length > 0 && selected.value.length === rows.value.length)
function toggleAll() {
  selected.value = allChecked.value ? [] : rows.value.map((r) => r.id)
}

const afterWrite = () => {
  selected.value = []
  client.invalidateQueries({ queryKey: ['kb'] })
}
const approveMut = useMutation({
  mutationFn: (ids: number[]) => approveStaging(ids),
  onSuccess: (d) => {
    toast(`已批准 ${d.approved} 条并写入知识库`)
    afterWrite()
  },
  onError: (err) => toast(errorText(err), 'error'),
})
const rejectMut = useMutation({
  mutationFn: (ids: number[]) => rejectStaging(ids),
  onSuccess: (d) => {
    toast(`已驳回 ${d.rejected} 条`)
    afterWrite()
  },
  onError: (err) => toast(errorText(err), 'error'),
})
const busy = computed(() => approveMut.isPending.value || rejectMut.isPending.value)

async function approve(ids: number[]) {
  const ok = await confirm({
    title: `批准 ${ids.length} 条候选问答`,
    body: '批准后会校验可信材料，写入知识库并立即向量化。材料校验不通过的批次会整体被拒绝。',
    confirmText: '确认批准',
  })
  if (ok) approveMut.mutate(ids)
}
async function reject(ids: number[]) {
  const ok = await confirm({
    title: `驳回 ${ids.length} 条候选问答`,
    body: '驳回后不会进入知识库。',
    confirmText: '确认驳回',
    danger: true,
  })
  if (ok) rejectMut.mutate(ids)
}

/* 详情 */
const detailId = ref<number | null>(null)
const detailOpen = computed({
  get: () => detailId.value !== null,
  set: (v: boolean) => {
    if (!v) detailId.value = null
  },
})
const detail = useQuery({
  queryKey: computed(() => ['kb', 'staging', detailId.value]),
  queryFn: () => getStaging(detailId.value as number),
  enabled: computed(() => detailId.value !== null),
})
const materialLabel: Record<string, string> = {
  available: '材料可读',
  missing: '材料缺失',
  untrusted: '来源不在白名单',
  read_error: '材料读取失败',
}
</script>

<template>
  <Panel title="候选问答">
    <template #extra>
      <span v-if="data" class="small muted">共 {{ data.stats.total }} 条 · {{ data.stats.batches }} 个批次</span>
    </template>

    <StateBlock :loading="isPending" :error="error" @retry="refetch()" />

    <template v-if="data">
      <div class="toolbar">
        <button
          v-for="(meta, key) in stagingStatus"
          :key="key"
          type="button"
          class="btn small"
          :class="{ primary: view === key }"
          @click="view = key"
        >
          {{ meta[0] }} {{ data.stats.counts[key] ?? 0 }}
        </button>
      </div>

      <div v-if="view === 'kept' && rows.length" class="toolbar">
        <label class="check"><input type="checkbox" :checked="allChecked" @change="toggleAll" /> 全选</label>
        <button class="btn small primary" type="button" :disabled="!selected.length || busy" @click="approve(selected)">
          批准所选 {{ selected.length || '' }}
        </button>
        <button class="btn small danger" type="button" :disabled="!selected.length || busy" @click="reject(selected)">
          驳回所选
        </button>
      </div>

      <StateBlock :empty="rows.length ? '' : '这个状态下没有记录'" />

      <div v-if="rows.length" class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th v-if="view === 'kept'"></th>
              <th>ID</th>
              <th>问题与答案</th>
              <th>来源材料</th>
              <th>批次</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td v-if="view === 'kept'">
                <input v-model="selected" type="checkbox" :value="row.id" :aria-label="`选择 #${row.id}`" />
              </td>
              <td class="mono">#{{ row.id }}</td>
              <td>
                <strong>{{ row.question }}</strong>
                <div class="clamp muted">{{ row.answer }}</div>
              </td>
              <td class="mono">{{ row.source_ref || DASH }}</td>
              <td class="mono small">{{ row.batch_no }}</td>
              <td><button class="btn small ghost" type="button" @click="detailId = row.id">核对</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </Panel>

  <AppDialog v-model="detailOpen" :title="`候选问答 #${detailId ?? ''}`" wide>
    <StateBlock :loading="detail.isPending.value" :error="detail.error.value" @retry="detail.refetch()" />
    <template v-if="detail.data.value">
      <dl class="kv">
        <dt>状态</dt>
        <dd><Pill :tone="stagingStatus[detail.data.value.status][1]">{{ stagingStatus[detail.data.value.status][0] }}</Pill></dd>
        <dt>问题</dt>
        <dd>{{ detail.data.value.question }}</dd>
        <dt>答案</dt>
        <dd class="pre">{{ detail.data.value.answer }}</dd>
        <dt>创建</dt>
        <dd>{{ dateTime(detail.data.value.created_at) }}</dd>
        <dt>材料</dt>
        <dd>
          {{ detail.data.value.material.file || DASH }} ·
          {{ materialLabel[detail.data.value.material.status] }}
          <Pill v-if="detail.data.value.material.valid === true" tone="green">答案可在材料中核对</Pill>
          <Pill v-else-if="detail.data.value.material.valid === false" tone="red">核对不通过</Pill>
          <div v-if="detail.data.value.material.reason" class="small muted">{{ detail.data.value.material.reason }}</div>
        </dd>
      </dl>
      <details v-if="detail.data.value.material.text" class="material">
        <summary>查看可信材料原文</summary>
        <pre class="pre small">{{ detail.data.value.material.text }}</pre>
      </details>
    </template>
    <template v-if="detail.data.value?.status === 'kept'" #footer>
      <button class="btn danger" type="button" :disabled="busy" @click="reject([detailId as number])">驳回</button>
      <button class="btn primary" type="button" :disabled="busy" @click="approve([detailId as number])">批准入库</button>
    </template>
  </AppDialog>
</template>

<style scoped>
.material {
  margin-top: 14px;
}
.material pre {
  max-height: 320px;
  overflow: auto;
  background: var(--canvas);
  padding: 12px;
  border-radius: 8px;
}
</style>
