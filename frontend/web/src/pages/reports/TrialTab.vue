<!-- 单题体验：用当前知识库与模型生成一次有据回答，不改写评估报告 -->
<script setup lang="ts">
import { askKnowledge } from '../../api/endpoints'
import { ApiError } from '../../api/client'
import type { Strategy } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { actionBusy } from '../../composables/useAdminActions'
import { invalidateTrial, strategyNames, trial } from './state'

async function answer() {
  if (trial.busy || actionBusy.value) return
  const query = trial.query.trim()
  const topK = Number(trial.topK)
  if (!query || !Number.isInteger(topK) || topK < 1 || topK > 50) {
    trial.error = '请填写完整问题，Top K 必须是 1–50 的整数。'
    return
  }
  invalidateTrial()
  const version = trial.version
  trial.busy = true
  try {
    const result = await askKnowledge({ query, strategy: trial.strategy as Strategy, top_k: topK, rewrite: trial.rewrite, split: trial.split })
    if (
      typeof result.answer !== 'string' ||
      typeof result.refused !== 'boolean' ||
      !Array.isArray(result.citations) ||
      result.citations.some((hit) => !hit || typeof hit.answer !== 'string')
    )
      throw new Error('回答或引用数据不完整，请核对接口返回。')
    if (version === trial.version) {
      trial.result = result
      trial.time = new Date().toLocaleTimeString('zh-CN')
    }
  } catch (error) {
    if (version === trial.version)
      trial.error =
        error instanceof ApiError && error.status
          ? `单题回答调用失败（HTTP ${error.status}），请核对数据和模型服务后重试。`
          : error instanceof ApiError && error.message.includes('超时')
            ? '等待回答超时，请核对服务后再试；页面没有自动重试。'
            : (error as Error).message || '回答请求失败。'
  } finally {
    trial.busy = false
  }
}
</script>

<template>
  <VPanel title="单题体验">
    <form id="report-trial-form" class="panel-pad" @submit.prevent="answer">
      <label class="field"
        >输入完整问题<textarea
          id="report-trial-query"
          v-model="trial.query"
          required
          maxlength="2000"
          rows="3"
          placeholder="例如：无理由退货有什么条件，寄回去运费谁出？"
          :disabled="trial.busy"
          @input="invalidateTrial"
        ></textarea>
      </label>
      <div class="report-trial-controls">
        <label
          >检索策略<select id="report-trial-strategy" v-model="trial.strategy" :disabled="trial.busy" @change="invalidateTrial">
            <option v-for="(title, key) in strategyNames" :key="key" :value="key">{{ title }}</option>
          </select></label
        >
        <label>Top K<input id="report-trial-k" v-model="trial.topK" type="number" min="1" max="50" required :disabled="trial.busy" @change="invalidateTrial" /></label>
        <label><input id="report-trial-rewrite" v-model="trial.rewrite" type="checkbox" :disabled="trial.busy" @change="invalidateTrial" />问题改写</label>
        <label><input id="report-trial-split" v-model="trial.split" type="checkbox" :disabled="trial.busy" @change="invalidateTrial" />多诉求拆分</label>
        <button class="btn primary" type="submit" :disabled="trial.busy">{{ trial.busy ? '正在检索和生成…' : '生成有据回答' }}</button>
      </div>
      <p class="field-hint section-gap">点击后使用当前知识库及模型配置；可能调用嵌入、重排和聊天服务。单题结果不改写固定题集评估报告。</p>
      <p class="field-hint">可到“固定题集”点击“试问”，载入问题后再生成。</p>
    </form>
    <div id="report-trial-result" class="panel-pad report-trial-output" aria-live="polite">
      <div v-if="trial.busy" class="empty" role="status">正在检索和生成，等待真实返回结果…</div>
      <div v-else-if="trial.error" class="notice data-alert" role="alert">{{ trial.error }}</div>
      <div v-else-if="!trial.result" class="empty">等待提问 · 答案与引用会显示在这里</div>
      <template v-else>
        <div class="between report-answer-heading">
          <h3>{{ trial.result.refused ? '证据不足 · 拒答' : '生成回答' }}</h3>
          <StatusPill :color="trial.result.refused ? 'amber' : ''">{{ trial.result.refused ? '已拒答' : '实时单题结果' }}</StatusPill>
        </div>
        <p class="report-trial-answer">{{ trial.result.answer }}</p>
        <div class="report-citations">
          <details v-for="hit in trial.result.citations" :key="hit.n">
            <summary>[{{ hit.n }}] {{ hit.section_path || hit.question || '引用资料' }}</summary>
            <div class="preview-text">{{ hit.answer }}</div>
          </details>
          <p v-if="!trial.result.citations.length" class="field-hint">本次未返回引用。请结合拒答状态判断，回答文本本身不代表证据充分。</p>
        </div>
      </template>
    </div>
  </VPanel>
</template>
