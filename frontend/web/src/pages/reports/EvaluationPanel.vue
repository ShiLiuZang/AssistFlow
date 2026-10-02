<!-- 运行固定题集评估：读取运行状态，运行中每 3 秒轮询；结束后刷新报告 -->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { getEvalState } from '../../api/endpoints'
import { actionBusy, evaluationAction } from '../../composables/useAdminActions'
import { closeModal } from '../../composables/useModal'

const router = useRouter()
const client = useQueryClient()
const state = useQuery({
  queryKey: ['rag', 'evaluation-state'],
  queryFn: getEvalState,
  refetchInterval: (q) => (q.state.data?.running === true ? 3000 : false),
})
watch(
  () => state.data.value?.running,
  (now, before) => {
    if (before === true && now === false) {
      client.invalidateQueries({ queryKey: ['rag', 'report'] })
      client.invalidateQueries({ queryKey: ['admin'] })
    }
  },
)
const topK = ref(5)
const generate = ref(false)
const submit = () =>
  evaluationAction(Number(topK.value), generate.value, () => {
    closeModal()
    router.push('/quality')
  })
</script>

<template>
  <details class="compact-guide evaluation-settings" :open="state.data.value?.running || !!state.error.value">
    <summary><strong>运行固定题集评估</strong>{{ state.data.value?.running ? '正在运行 · 查看状态' : state.error.value ? '状态读取失败' : state.data.value ? '当前空闲 · 展开运行设置' : '正在读取状态…' }}</summary>
    <div class="panel-pad">
      <p class="small muted">
        {{
          state.data.value ? (state.data.value.running ? '评估正在运行；等待真实报告，不推测进度。' : '当前没有评估运行。') : state.error.value ? '评估状态暂不可读取；恢复查询后再启动。' : '正在读取评估状态…'
        }}旧报告与本次执行分别核对。
      </p>
      <form id="report-evaluate-form" class="data-table-tools section-gap" @submit.prevent="submit">
        <label>top_k <input v-model="topK" name="top_k" type="number" min="1" max="50" required aria-label="评估 top_k" /></label>
        <label><input v-model="generate" name="generate" type="checkbox" />同时生成回答（调用聊天模型）</label>
        <button class="btn primary" type="submit" :disabled="!state.data.value || state.data.value.running || actionBusy">核对并运行评估</button>
      </form>
    </div>
  </details>
</template>
