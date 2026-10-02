<!-- 写操作确认弹窗的内容（结构对应 V2 admin-actions.js 的各阶段） -->
<script setup lang="ts">
import { ref } from 'vue'
import RecordFields from './RecordFields.vue'
import { actionState, cancelOrReopen, execute } from '../composables/useAdminActions'
import { closeModal } from '../composables/useModal'

const checked = ref(false)
function submit() {
  if (checked.value) execute()
}
</script>

<template>
  <div class="modal-body">
    <div v-if="actionState.phase === 'loading'" class="empty" role="status">正在读取最新状态…</div>
    <template v-else-if="actionState.phase === 'error'">
      <p role="alert">{{ actionState.message }}</p>
      <p class="field-hint section-gap">尚未发送写入请求。</p>
    </template>
    <form v-else-if="actionState.phase === 'confirm' && actionState.spec" id="admin-confirm-form" @submit.prevent="submit">
      <p v-if="actionState.spec.intro">{{ actionState.spec.intro }}</p>
      <RecordFields v-if="actionState.spec.fields" :fields="actionState.spec.fields" />
      <template v-for="[title, text] in actionState.spec.fulls ?? []" :key="title">
        <h3 class="section-gap">{{ title }}</h3>
        <div class="data-detail-text section-gap">{{ text }}</div>
      </template>
      <p v-if="actionState.spec.notice" class="notice section-gap">{{ actionState.spec.notice }}</p>
      <label class="data-ingest-check section-gap">
        <input id="admin-confirm-check" v-model="checked" type="checkbox" required />我已核对对象、范围和执行条件，确认执行本次操作。
      </label>
      <p class="field-hint section-gap">提交后查询真实结果。超时不自动重试，已完成的步骤不会由页面撤回。</p>
    </form>
    <template v-else-if="actionState.phase === 'running'">
      <div class="empty" role="status">正在执行，请等待真实返回结果…</div>
      <p class="field-hint section-gap">关闭仅收起弹窗，后台操作继续；结果会显示在页面上。</p>
    </template>
    <p v-else-if="actionState.phase === 'result'" role="status">{{ actionState.message }}</p>
  </div>
  <div class="modal-foot">
    <template v-if="actionState.phase === 'confirm'">
      <button class="btn" @click="cancelOrReopen">返回核对</button>
      <button class="btn primary" form="admin-confirm-form" type="submit">{{ actionState.spec?.button ?? '确认执行' }}</button>
    </template>
    <template v-else-if="actionState.phase === 'result'">
      <button class="btn" @click="closeModal">关闭</button>
      <button class="btn primary" @click="cancelOrReopen">查询当前结果</button>
    </template>
    <button v-else class="btn" @click="closeModal">关闭</button>
  </div>
</template>
