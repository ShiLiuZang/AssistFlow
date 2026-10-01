<!-- 录入与切块：粘贴或选择 Markdown/TXT → 预览切块与查重 → 确认后入库；下方是建库材料清单 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { ingestText, previewFile, previewText } from '../../api/endpoints'
import type { IngestResult, KbOverview, PreviewResult } from '../../api/types'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import { confirm } from '../../composables/useConfirm'
import { errorText, toast } from '../../composables/useToast'
import { contentTypeNames } from '../../utils/labels'
import { dateTime, num } from '../../utils/format'

const props = defineProps<{ overview?: KbOverview }>()
const client = useQueryClient()

const MAX_CHARS = 40000
const text = ref('')
const contentType = ref('faq')
const vectorize = ref(true)
const fileNote = ref('')
const preview = ref<PreviewResult | null>(null)
const previewSource = ref<'text' | 'file'>('text')
const result = ref<IngestResult | null>(null)

const typeOptions = computed(() =>
  (props.overview?.content_types ?? ['faq', 'policy', 'manual', 'spec'].map((key) => ({ key, desc: '' }))).map((t) => ({
    key: t.key,
    label: contentTypeNames[t.key] ?? t.key,
    desc: t.desc,
  })),
)

// 正文或类型变了，旧的预览就作废，必须重新预览才能入库
watch([text, contentType], () => {
  if (previewSource.value === 'text') preview.value = null
  result.value = null
})

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!/\.(md|markdown|txt)$/i.test(file.name)) {
    fileNote.value = `只支持 UTF-8 编码的 Markdown 或 TXT，${file.name} 未载入。`
    return
  }
  try {
    const content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
    if (content.length > MAX_CHARS) {
      fileNote.value = `${file.name} 共 ${content.length} 字，超过单次上限 ${MAX_CHARS} 字，请拆开录入。`
      return
    }
    text.value = content
    previewSource.value = 'text'
    fileNote.value = `已载入 ${file.name}，可在下方编辑，入库以编辑器内容为准。`
  } catch {
    fileNote.value = `${file.name} 不是有效的 UTF-8 文本，未载入。`
  }
}

const previewMut = useMutation({
  mutationFn: () => previewText(text.value, contentType.value),
  onSuccess: (data) => {
    preview.value = data
    previewSource.value = 'text'
  },
  onError: (err) => toast(errorText(err), 'error'),
})

const filePreviewMut = useMutation({
  mutationFn: (file: string) => previewFile(file),
  onSuccess: (data) => {
    preview.value = data
    previewSource.value = 'file'
    result.value = null
  },
  onError: (err) => toast(errorText(err), 'error'),
})

const ingestMut = useMutation({
  mutationFn: () => ingestText(text.value, contentType.value, vectorize.value),
  onSuccess: (data) => {
    result.value = data
    toast(`已入库 ${data.inserted} 块，跳过重复 ${data.skipped} 块`)
    client.invalidateQueries({ queryKey: ['kb'] })
  },
  onError: (err) => toast(errorText(err), 'error'),
})

const canIngest = computed(
  () => preview.value && previewSource.value === 'text' && preview.value.total > 0 && !ingestMut.isPending.value,
)

async function doIngest() {
  if (!preview.value) return
  const p = preview.value
  const ok = await confirm({
    title: '确认入库',
    body: `将切出 ${p.total} 块，其中疑似重复 ${p.duplicates} 块（入库时自动跳过）、关键条款 ${p.key_clause} 块。\n${
      vectorize.value ? '入库后立即向量化（会调用嵌入服务）。' : '只写入 MySQL，向量化稍后在"索引状态"补齐。'
    }`,
    confirmText: '确认入库',
  })
  if (ok) ingestMut.mutate()
}
</script>

<template>
  <div class="grid-2">
    <Panel title="录入正文">
      <div class="toolbar">
        <select v-model="contentType" aria-label="内容类型">
          <option v-for="t in typeOptions" :key="t.key" :value="t.key">{{ t.label }}</option>
        </select>
        <label class="btn small file">
          选择文件
          <input type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" @change="onFile" />
        </label>
        <label class="check"><input v-model="vectorize" type="checkbox" /> 入库后立即向量化</label>
      </div>
      <p v-if="fileNote" class="notice warn">{{ fileNote }}</p>
      <textarea
        v-model="text"
        rows="14"
        aria-label="Markdown 正文"
        placeholder="粘贴 Markdown，例如：## 退货运费…"
        :maxlength="MAX_CHARS"
        spellcheck="false"
      />
      <div class="foot">
        <span class="small muted">{{ num(text.length) }} / {{ num(MAX_CHARS) }} 字</span>
        <div class="buttons">
          <button class="btn" type="button" :disabled="!text.trim() || previewMut.isPending.value" @click="previewMut.mutate()">
            {{ previewMut.isPending.value ? '预览中…' : '预览切块' }}
          </button>
          <button class="btn primary" type="button" :disabled="!canIngest" @click="doIngest">
            {{ ingestMut.isPending.value ? '入库中…' : '确认入库' }}
          </button>
        </div>
      </div>
      <p v-if="!preview && text.trim()" class="small muted">入库前必须先预览，核对切块和查重结果。</p>

      <div v-if="result" class="notice">
        切出 {{ result.chunks }} 块，新增 {{ result.inserted }} 块，跳过重复 {{ result.skipped }} 块。
        <template v-if="result.vectorized !== null">向量化 {{ result.vectorized }} 块。</template>
        <template v-else>尚未向量化，可在"索引状态"补齐。</template>
      </div>
    </Panel>

    <Panel :title="preview ? `切块预览 · ${preview.source}` : '切块预览'">
      <p v-if="!preview" class="muted">点击"预览切块"后在这里核对每一块的内容。</p>
      <template v-else>
        <p class="summary">
          共 {{ preview.total }} 块 · 关键条款 {{ preview.key_clause }} ·
          <template v-if="preview.dedup_known">疑似重复 {{ preview.duplicates }}</template>
          <template v-else>数据库不可用，未能查重</template>
          <span v-if="previewSource === 'file'"> · 材料文件只读预览，正式建库请运行"离线建库"作业</span>
        </p>
        <ol class="chunks">
          <li v-for="c in preview.chunks" :key="c.seq" :class="{ dup: c.duplicate }">
            <div class="chunk-head">
              <span class="mono">#{{ c.seq }}</span>
              <strong>{{ c.questions }}</strong>
              <Pill v-if="c.is_key_clause" tone="amber">关键条款</Pill>
              <Pill v-if="c.is_table" tone="blue">表格</Pill>
              <Pill v-if="c.duplicate" tone="red">重复</Pill>
            </div>
            <div class="small muted">{{ c.section_path }} · {{ c.chars }} 字</div>
            <p class="clamp">{{ c.answer }}</p>
          </li>
        </ol>
      </template>
    </Panel>
  </div>

  <Panel title="建库材料">
    <p v-if="!overview" class="muted">读取知识库概览后显示材料清单。</p>
    <div v-else class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>文件</th>
            <th>类型</th>
            <th class="num">字数</th>
            <th class="num">切块</th>
            <th class="num">关键条款</th>
            <th>修改时间</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in overview.sources" :key="s.file">
            <td class="mono">{{ s.path }}</td>
            <td>{{ contentTypeNames[s.content_type] ?? s.content_type }}</td>
            <td class="num">{{ num(s.chars) }}</td>
            <td class="num">{{ num(s.chunks) }}</td>
            <td class="num">{{ num(s.key_clause) }}</td>
            <td class="small">{{ s.present ? dateTime(s.mtime) : '文件不存在' }}</td>
            <td>
              <button
                class="btn small ghost"
                type="button"
                :disabled="!s.present || filePreviewMut.isPending.value"
                @click="filePreviewMut.mutate(s.file)"
              >
                预览切块
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </Panel>
</template>

<style scoped>
textarea {
  width: 100%;
}
.file {
  position: relative;
  overflow: hidden;
}
.file input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}
.buttons {
  display: flex;
  gap: 8px;
}
.summary {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--muted);
}
.chunks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
  max-height: 560px;
  overflow: auto;
}
.chunks li {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.chunks li.dup {
  background: var(--red-soft);
}
.chunk-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.chunks p {
  margin: 6px 0 0;
  font-size: 13px;
}
</style>
