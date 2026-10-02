<!-- 单句试分类：调用当前分类服务，展示 17 类分数与阈值 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { classifyText } from '../../api/endpoints'
import DataState from '../../components/DataState.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { actionBusy } from '../../composables/useAdminActions'
import MetaRow from '../classification/MetaRow.vue'
import Note from '../classification/Note.vue'
import ScoreChart from '../classification/ScoreChart.vue'
import Tags from '../classification/Tags.vue'
import { trackTime, useClsService } from '../classification/queries'
import { local, serviceDetail } from '../classification/shared'

const router = useRouter()
const v = useClsService()
trackTime(v)
const d = computed(() => v.data.value)
const busy = ref(false)

function edit() {
  local.trialResult = null
  local.trialError = ''
  local.trialEdited = true
}
async function classify() {
  const text = local.trialText.trim()
  if (busy.value || actionBusy.value || !text) return
  busy.value = true
  local.trialResult = null
  local.trialError = ''
  local.trialEdited = false
  try {
    const data = await classifyText(text)
    if (
      !Array.isArray(data.labels) ||
      !Array.isArray(data.scores) ||
      !data.scores.length ||
      data.text !== text ||
      data.scores.some((row) => typeof row.label !== 'string' || !Number.isFinite(row.score) || typeof row.hit !== 'boolean')
    )
      throw new Error('分类结果不完整，请重新核对服务。')
    local.trialResult = data
  } catch (error) {
    local.trialError = (error as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <DataState v-if="!d" :loading="v.isPending.value" :error="v.error.value" />
  <template v-else>
    <VPanel title="推理服务">
      <template #extra>
        <StatusPill v-if="d.online === true">服务在线</StatusPill><StatusPill v-else-if="d.online === false" color="amber">服务离线</StatusPill
        ><StatusPill v-else color="neutral">服务未知</StatusPill>
      </template>
      <div class="panel-pad">
        <MetaRow
          :items="[
            ['服务状态', d.online === true ? '在线' : d.online === false ? '离线' : '未知'],
            ['当前阈值', d.threshold],
            ['ONNX 文件', d.onnx_present === true ? '存在' : d.onnx_present === false ? '缺失' : '未知'],
            ['健康检查', serviceDetail(d.detail)],
          ]"
        />
        <Note>单句试分类调用当前分类服务并展示实际分数；可从验收卡或作业中心核对条件后重跑任务。</Note>
      </div>
    </VPanel>
    <VPanel title="单句试分类">
      <div class="panel-pad">
        <form id="cls-trial-form" @submit.prevent="classify">
          <label class="field"
            >完整问题<textarea
              id="cls-trial-text"
              v-model="local.trialText"
              maxlength="2000"
              required
              :readonly="busy"
              placeholder="输入一句需要核对类目的问题"
              @input="edit"
            ></textarea></label
          ><button class="btn primary" type="submit" :disabled="busy || actionBusy || d.online !== true">{{ busy ? '正在分类…' : '查询真实分类' }}</button
          ><button class="btn soft" type="button" @click="router.push('/jobs')">打开作业中心</button>
          <p class="field-hint section-gap">调用现有本地分类服务，不写入问题池；服务离线时先在作业中心核对 classifier-up。</p>
        </form>
        <div id="cls-trial-output">
          <p v-if="local.trialEdited && !local.trialResult && !local.trialError" class="field-hint section-gap">问题已修改，请重新查询。</p>
          <p v-if="local.trialError" role="alert" class="section-gap">{{ local.trialError }}</p>
          <div v-if="local.trialResult" class="section-gap">
            <Tags :values="local.trialResult.labels" />
            <MetaRow
              :items="[
                ['完整问题', local.trialResult.text],
                ['服务当前阈值', local.trialResult.threshold],
                ['兜底', local.trialResult.fallback ? '是 · 未达阈值，按服务规则返回标签' : '否'],
              ]"
            />
            <ScoreChart :scores="local.trialResult.scores" :threshold="local.trialResult.threshold" />
          </div>
        </div>
      </div>
    </VPanel>
  </template>
</template>
