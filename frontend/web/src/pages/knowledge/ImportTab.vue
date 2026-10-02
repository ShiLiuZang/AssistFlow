<!-- 录入与切块（对应 V2 importPage）：填写原文 → 预览与查重 → 核对后入库（只存原文，不向量化） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQueryClient, type UseQueryReturnType } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { request } from '../../api/client'
import type { KbOverview, PreviewResult } from '../../api/types'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { actionBusy } from '../../composables/useAdminActions'
import { openModal } from '../../composables/useModal'
import { useUrlState } from '../../composables/useUrlState'
import ChunkDetailModal from './ChunkDetailModal.vue'
import IngestConfirmModal from './IngestConfirmModal.vue'
import MaterialsPanel from './MaterialsPanel.vue'
import PreviewChunkHead from './PreviewChunkHead.vue'
import { exampleText, invalidatePreview, kb, typeName } from './state'

const props = defineProps<{ overview: UseQueryReturnType<KbOverview, Error> }>()
const emit = defineEmits<{ materials: [] }>()
const router = useRouter()
const client = useQueryClient()
const tab = useUrlState('tab', 'content')
const data = computed(() => props.overview.data.value)
const busy = computed(() => kb.ingestBusy || kb.vectorChecking || kb.vectorStarting || actionBusy.value)

function onText(value: string) {
  if (busy.value) return
  kb.text = value
  invalidatePreview()
  if (kb.fileName) kb.fileNotice = '已修改正文，入库以编辑器内容为准。'
}
function onType(value: string) {
  kb.importType = value
  invalidatePreview()
}
function fillExample() {
  if (busy.value) return
  kb.text = exampleText
  kb.importType = 'policy'
  invalidatePreview()
}

/* 选择文件：只载入编辑器，不自动预览或入库 */
async function loadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || busy.value) return
  const token = ++kb.fileVersion
  kb.fileReading = false
  if (!/\.(md|markdown|txt)$/i.test(file.name)) {
    kb.fileNotice = '请选择 Markdown 或 TXT 文件；原正文已保留。'
    return
  }
  if (file.size > 1024 * 1024) {
    kb.fileNotice = '文件过大，请选择不超过 1 MB 且正文不超过 40,000 字符的材料；原正文已保留。'
    return
  }
  kb.fileReading = true
  kb.fileNotice = `正在读取 ${file.name}，读取完成后可编辑并手动预览。`
  try {
    const buffer = await file.arrayBuffer()
    if (token !== kb.fileVersion) return
    const text = new TextDecoder('utf-8', { fatal: true }).decode(buffer).replace(/^﻿/, '').replace(/\r\n?/g, '\n')
    if (!text.trim()) throw new Error('文件没有正文')
    if (text.length > 40000) throw new Error('正文超过 40,000 字符')
    if (text.includes('\u0000')) throw new Error('文件包含非文本内容')
    kb.text = text
    invalidatePreview()
    kb.fileName = file.name
    kb.fileNotice = `已载入 ${text.length.toLocaleString('zh-CN')} 字符，可修改正文后预览；尚未入库。`
  } catch (error: any) {
    if (token !== kb.fileVersion) return
    kb.fileNotice = `${error.name === 'TypeError' ? '文件不是有效的 UTF-8 文本，请转换编码后重试' : error.message || '文件读取失败'}；原正文已保留。`
  } finally {
    if (token === kb.fileVersion) kb.fileReading = false
  }
}

/* 预览切块 */
async function preview() {
  if (kb.previewBusy || kb.fileReading || busy.value) return
  const text = kb.text
  const contentType = kb.importType
  const version = ++kb.previewVersion
  kb.previewBusy = true
  kb.preview = null
  kb.previewError = ''
  try {
    const result = await request<PreviewResult>('/api/kb/preview', { method: 'POST', body: { text, content_type: contentType } })
    if (
      !Array.isArray(result.chunks) ||
      !Number.isInteger(result.total) ||
      result.total !== result.chunks.length ||
      !Number.isInteger(result.duplicates) ||
      result.duplicates < 0 ||
      result.duplicates > result.total
    )
      throw new Error('切块结果不完整，请重新预览。')
    if (version === kb.previewVersion) {
      kb.preview = result
      kb.ingestResult = null
      if (result.dedup_known) kb.ingestError = null
    }
  } catch (error: any) {
    if (version === kb.previewVersion) kb.previewError = error.message
  } finally {
    if (version === kb.previewVersion) kb.previewBusy = false
  }
}

const canIngest = computed(
  () =>
    !kb.previewBusy &&
    !kb.fileReading &&
    !busy.value &&
    !kb.ingestResult &&
    !kb.ingestError &&
    !!kb.preview?.dedup_known &&
    kb.preview.total > kb.preview.duplicates,
)
const previewNote = computed(() => {
  const p = kb.preview
  if (!p) return ''
  return kb.ingestBusy
    ? '正在保存原文，请等待返回结果。'
    : kb.ingestResult
      ? '本次录入已返回结果；再次录入前请重新预览。'
      : !p.total
        ? '没有切出正文，请补充内容。'
        : !p.dedup_known
          ? '查重未完成，请恢复数据服务后重新预览。'
          : p.total === p.duplicates
            ? '内容全部重复，本次无需新增。'
            : '预览尚未写入；提交时后端会再次查重，实际新增数量以返回结果为准。'
})
function confirmIngest() {
  if (!canIngest.value || !kb.preview) return
  openModal({
    title: '核对本次录入',
    view: IngestConfirmModal,
    props: { text: kb.text, contentType: kb.importType, version: kb.previewVersion },
    cls: 'knowledge-dialog',
  })
}

/* 录入结果的后续操作 */
function toInventory() {
  router.replace({ query: { tab: 'content' } })
  client.invalidateQueries()
}
function ingestNext() {
  if (busy.value) return
  kb.text = ''
  kb.ingestResult = null
  kb.ingestError = null
  invalidatePreview()
}
const showChunk = (id: number) => openModal({ title: '知识块详情', view: ChunkDetailModal, props: { id }, cls: 'knowledge-dialog' })
</script>

<template>
  <div v-if="kb.ingestBusy" class="notice data-ingest-status" role="status">正在保存原文，请勿重复提交。录入结果返回后会重新读取库存。</div>
  <div v-else-if="kb.ingestError" class="data-ingest-result">
    <VPanel :title="kb.ingestError.uncertain ? '录入结果待核对' : '录入未完成'">
      <div class="panel-pad">
        <div class="notice data-alert" :class="kb.ingestError.uncertain ? 'amber' : 'data-ingest-error'" role="alert">{{ kb.ingestError.message }}</div>
        <p class="field-hint">
          {{ kb.ingestError.uncertain ? '请求可能已写入原文，请先查看库存，再重新预览查重；不要直接重复提交。' : '原文仍保留在表单中，请检查内容后重新预览。' }}
        </p>
        <div class="form-actions"><button class="btn soft" @click="toInventory">查看知识库存</button></div>
      </div>
    </VPanel>
  </div>
  <div v-else-if="kb.ingestResult" class="data-ingest-result">
    <VPanel :title="kb.ingestResult.inserted ? '原文已入库' : '内容已存在，本次未新增'">
      <template #extra><StatusPill>真实录入结果</StatusPill></template>
      <div class="panel-pad">
        <div class="data-ingest-counts">
          <span>实际新增 <b>{{ kb.ingestResult.inserted }}</b> 块</span>
          <span>跳过重复 <b>{{ kb.ingestResult.skipped }}</b> 块</span>
          <span><StatusPill color="amber">本次未执行向量化</StatusPill></span>
        </div>
        <div v-if="kb.ingestResult.ids.length" class="data-ingest-ids">
          <span class="muted">入库记录</span>
          <button v-for="id in kb.ingestResult.ids" :key="id" class="btn soft" @click="showChunk(id)">#{{ id }}</button>
        </div>
        <p class="field-hint">
          {{ kb.ingestResult.inserted ? '原文已保存，录入时为待向量化。点击记录核对完整正文和当前状态。' : '提交时再次查重，全部内容已存在。' }}
        </p>
        <div class="form-actions">
          <button class="btn soft" @click="toInventory">查看知识库存</button>
          <button v-if="kb.ingestResult.inserted" class="btn primary" @click="tab = 'index'">查看索引并补齐</button>
          <button class="btn" @click="ingestNext">录入下一份</button>
        </div>
      </div>
    </VPanel>
  </div>

  <div class="data-import-steps" aria-label="录入流程">
    <span>01 填写原文</span><Icon name="arrow" /><span>02 预览与查重</span><Icon name="arrow" /><span>03 核对后入库</span>
  </div>
  <div class="data-material-entry">
    <span>已有源文件？在下方建库材料中查看清单与切块。</span>
    <button class="btn soft" @click="emit('materials')">查看建库材料</button>
  </div>
  <div class="split-panels data-import-panels">
    <VPanel title="录入内容">
      <form id="data-preview-form" class="panel-pad" @submit.prevent="preview">
        <label class="field"
          >内容类型<select id="data-import-type" :value="kb.importType" :disabled="busy" @change="onType(($event.target as HTMLSelectElement).value)">
            <option v-for="row in data?.content_types ?? []" :key="row.key" :value="row.key">{{ typeName(row.key) }}</option>
          </select></label
        >
        <div class="data-file-picker">
          <div class="form-actions">
            <label class="btn soft" :class="{ disabled: busy }">
              {{ kb.fileReading ? '正在读取文件…' : '选择文件' }}
              <input id="data-import-file" type="file" accept=".md,.markdown,.txt,text/plain,text/markdown" hidden :disabled="busy" @change="loadFile" />
            </label>
            <span id="data-file-name">{{ kb.fileName || 'Markdown / TXT · UTF-8' }}</span>
          </div>
          <p id="data-file-notice" class="field-hint" aria-live="polite">
            {{ kb.fileNotice || '文件载入下方编辑器，最多 40,000 字符；不会自动保存源文件或入库。PDF / Word 暂不支持。' }}
          </p>
        </div>
        <label class="field"
          >Markdown / TXT 正文<textarea
            id="data-import-text"
            class="large-textarea"
            required
            maxlength="40000"
            placeholder="粘贴需要入库的完整材料，保留标题、适用范围和限制条件…"
            :value="kb.text"
            :disabled="busy"
            @input="onText(($event.target as HTMLTextAreaElement).value)"
          ></textarea
        ></label>
        <div class="form-actions">
          <button class="btn primary" type="submit" :disabled="kb.previewBusy || kb.fileReading || busy"><Icon name="file" />{{ kb.previewBusy ? '正在预览…' : '预览切块' }}</button>
          <button class="btn" type="button" :disabled="busy" @click="fillExample">填入示例材料</button>
        </div>
        <p id="data-preview-hint" class="field-hint">预览不会写入。确认入库后保存原文，状态为待向量化；此步骤不启动向量化。</p>
      </form>
    </VPanel>
    <VPanel title="切块预览">
      <div id="data-preview-result" class="panel-pad" aria-live="polite">
        <div v-if="kb.previewBusy" class="data-empty-state compact" role="status">
          <h2>正在切块与查重</h2>
          <p>预览不写入知识库。</p>
        </div>
        <div v-else-if="kb.previewError" class="notice data-alert" role="alert">{{ kb.previewError }}</div>
        <div v-else-if="!kb.preview" class="data-empty-state compact">
          <Icon name="file" />
          <h2>先预览，再核对</h2>
          <p>切块结果会保留章节、关键条款和查重状态。</p>
        </div>
        <template v-else>
          <div class="data-preview-summary">
            <span>切块 <b>{{ kb.preview.total }}</b></span>
            <span>关键条款 <b>{{ kb.preview.key_clause }}</b></span>
            <span v-if="kb.preview.dedup_known">重复 <b>{{ kb.preview.duplicates }}</b></span>
            <span v-else>查重状态：未知</span>
          </div>
          <div class="data-preview-list">
            <article v-for="row in kb.preview.chunks" :key="row.seq" class="data-preview-chunk" :class="{ 'is-key-clause': row.is_key_clause }">
              <PreviewChunkHead :row="row" />
              <p>{{ row.answer }}</p>
              <div class="small muted">{{ row.chars }} 字</div>
            </article>
          </div>
          <div class="data-import-next">
            <p class="field-hint">{{ previewNote }}</p>
            <button class="btn primary" :disabled="!canIngest" @click="confirmIngest">{{ kb.ingestBusy ? '正在入库…' : '核对并入库' }}</button>
          </div>
        </template>
      </div>
    </VPanel>
  </div>
  <div id="data-source-materials" class="section-gap">
    <MaterialsPanel :data="data" />
  </div>
</template>
