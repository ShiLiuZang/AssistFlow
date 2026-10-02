<!-- 核对本次录入（对应 V2 confirmIngest / ingest）：只保存原文，vectorize=false -->
<script setup lang="ts">
import { ref } from 'vue'
import StatusPill from '../../components/StatusPill.vue'
import { closeModal } from '../../composables/useModal'
import { queryClient } from '../../queryClient'
import { kb, typeName } from './state'

const props = defineProps<{ text: string; contentType: string; version: number }>()
const checked = ref(false)
const preview = kb.preview!

async function ingest() {
  if (!checked.value || props.version !== kb.previewVersion || props.text !== kb.text || props.contentType !== kb.importType) return
  kb.ingestBusy = true
  kb.ingestError = null
  kb.ingestResult = null
  closeModal()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30000)
  try {
    const response = await fetch('/api/kb/ingest', {
      method: 'POST',
      signal: controller.signal,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: props.text, content_type: props.contentType, vectorize: false }),
    })
    if (!response.ok) {
      let detail
      try {
        detail = (await response.json()).detail
      } catch {}
      throw Object.assign(
        new Error(
          response.status >= 500
            ? `服务未返回完整录入结果（HTTP ${response.status}）。`
            : typeof detail === 'string'
              ? detail
              : `录入请求未通过（HTTP ${response.status}），请检查内容。`,
        ),
        { uncertain: response.status >= 500 },
      )
    }
    const d = await response.json()
    if (
      !Number.isInteger(d.chunks) ||
      !Number.isInteger(d.inserted) ||
      !Number.isInteger(d.skipped) ||
      d.inserted < 0 ||
      d.skipped < 0 ||
      d.inserted + d.skipped !== d.chunks ||
      !Array.isArray(d.ids) ||
      d.ids.length !== d.inserted ||
      new Set(d.ids).size !== d.ids.length ||
      d.ids.some((id: unknown) => !Number.isInteger(id) || (id as number) < 1) ||
      d.vectorized !== null
    )
      throw new Error('服务返回的录入结果不完整，暂不能确认新增数量。')
    kb.ingestResult = d
  } catch (error: any) {
    kb.ingestError = {
      uncertain: error.uncertain !== false,
      message:
        error.name === 'AbortError' ? '录入请求超时，尚未确认保存结果。' : error instanceof TypeError ? '连接中断，尚未收到录入结果。' : error.message,
    }
  } finally {
    clearTimeout(timer)
    kb.ingestBusy = false
    queryClient.invalidateQueries()
  }
}
</script>

<template>
  <div class="modal-body">
    <form id="data-ingest-form" @submit.prevent="ingest">
      <div class="data-detail-meta">
        <StatusPill color="neutral">{{ typeName(contentType) }}</StatusPill>
        <StatusPill color="amber">仅保存原文，待向量化</StatusPill>
      </div>
      <p>预览 {{ preview.total }} 块，重复 {{ preview.duplicates }} 块，预计新增 {{ preview.total - preview.duplicates }} 块。实际结果以提交时再次查重为准。</p>
      <details class="data-source-excerpt" open>
        <summary>本次提交的完整原文 · {{ text.length }} 字</summary>
        <div class="data-detail-text data-ingest-original">{{ text }}</div>
      </details>
      <label class="data-ingest-check"><input v-model="checked" type="checkbox" required name="checked" />我已核对内容与适用范围，确认将原文存入当前知识库。</label>
    </form>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">继续检查</button>
    <button class="btn primary" type="submit" form="data-ingest-form">确认入库原文</button>
  </div>
</template>
