<!-- 作业卡片：状态、执行条件、启动/停止、日志。运行中自动轮询 -->
<script setup lang="ts">
import { ref } from 'vue'
import { useJob } from '../composables/useJob'
import { jobStatus } from '../utils/labels'
import { dateTime } from '../utils/format'
import Pill from './Pill.vue'

const props = defineProps<{ name: string; compact?: boolean }>()
const { query, start, stop, confirmStart, confirmStop } = useJob(() => props.name)
const showLog = ref(false)
</script>

<template>
  <div class="job">
    <div v-if="query.isPending.value" class="muted">读取作业状态…</div>
    <div v-else-if="query.error.value" class="muted">作业状态读取失败：{{ query.error.value.message }}</div>
    <template v-else-if="query.data.value">
      <div class="top">
        <div>
          <strong>{{ query.data.value.title }}</strong>
          <Pill :tone="jobStatus[query.data.value.status][1]">{{ jobStatus[query.data.value.status][0] }}</Pill>
          <Pill v-if="query.data.value.heavy" tone="amber">耗时</Pill>
        </div>
        <div class="buttons">
          <button
            v-if="query.data.value.status === 'running'"
            class="btn small danger"
            type="button"
            :disabled="stop.isPending.value"
            @click="confirmStop"
          >
            停止
          </button>
          <button
            v-else
            class="btn small"
            type="button"
            :disabled="start.isPending.value"
            @click="confirmStart"
          >
            {{ start.isPending.value ? '启动中…' : '启动' }}
          </button>
          <button class="btn small ghost" type="button" @click="showLog = !showLog">
            {{ showLog ? '收起日志' : '查看日志' }}
          </button>
        </div>
      </div>
      <p v-if="!compact" class="meta">
        执行条件：{{ query.data.value.needs }} · 开始 {{ dateTime(query.data.value.started_at) }} · 结束
        {{ dateTime(query.data.value.finished_at) }}
        <template v-if="query.data.value.returncode !== null"> · 退出码 {{ query.data.value.returncode }}</template>
      </p>
      <pre v-if="showLog" class="log">{{ query.data.value.log || '暂无日志' }}</pre>
    </template>
  </div>
</template>

<style scoped>
.job {
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
.job:last-child {
  border-bottom: 0;
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.top strong {
  margin-right: 8px;
}
.top .pill {
  margin-right: 4px;
}
.buttons {
  display: flex;
  gap: 6px;
}
.meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.log {
  margin: 10px 0 0;
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  background: var(--rail);
  color: var(--rail-text);
  border-radius: 8px;
  font: 12px/1.6 Consolas, SFMono-Regular, monospace;
  white-space: pre-wrap;
  word-break: break-all;
}
.muted {
  color: var(--muted);
  font-size: 13px;
}
</style>
