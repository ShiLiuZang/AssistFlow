<!-- 建库材料（对应 V2 materialsPage） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import type { KbOverview } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { actionBusy, jobAction } from '../../composables/useAdminActions'
import { openModal } from '../../composables/useModal'
import MaterialPreviewModal from './MaterialPreviewModal.vue'
import SourceFeatures from './SourceFeatures.vue'
import { kb, num, typeName } from './state'

const props = defineProps<{ data?: KbOverview }>()
const router = useRouter()
const client = useQueryClient()
const sources = computed(() => props.data?.sources ?? [])
const summary = computed(() => {
  const readable = sources.value.filter((r) => r.present)
  const known = sources.value.every((r) => r.present && Number.isInteger(r.chunks))
  return `${sources.value.length} 份材料 · 共切 ${known ? readable.reduce((sum, r) => sum + (r.chunks ?? 0), 0) : '—'} 块`
})
const busy = computed(() => kb.ingestBusy || kb.vectorChecking || kb.vectorStarting || actionBusy.value)
const preview = (file: string) => openModal({ title: `建库材料 · ${file}`, view: MaterialPreviewModal, props: { file }, cls: 'knowledge-dialog' })
</script>

<template>
  <VPanel title="建库材料">
    <template #extra><StatusPill color="neutral">{{ summary }}</StatusPill></template>
    <div class="panel-pad data-material-description">
      <p><span class="mono">data/kb/</span> 下的源文件是离线建库的输入。点击“看切块”核对章节、正文与关键条款。</p>
      <p class="muted">这里展示当前文件的切块预估，不代表已入库。预览不写库、不执行向量化。</p>
    </div>
    <div class="data-source-table">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-for="h in ['材料文件', '类型 / 状态', '字符', '行', '切出块数', '关键条款', '特性', '操作']" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sources" :key="row.file">
              <td class="data-source-file">
                <strong>{{ row.file }}</strong><span class="table-sub mono">{{ row.path }}</span>
              </td>
              <td>
                {{ typeName(row.content_type) }}<span class="table-sub"><StatusPill v-if="row.present">可读</StatusPill><StatusPill v-else color="amber">文件缺失</StatusPill></span>
              </td>
              <td>{{ num(row.chars) }}</td>
              <td>{{ num(row.lines) }}</td>
              <td>{{ num(row.chunks) }}</td>
              <td>{{ num(row.key_clause) }}</td>
              <td><SourceFeatures :features="row.features" /></td>
              <td><button class="btn soft" :disabled="!row.present || kb.previewBusy || busy" @click="preview(row.file)">看切块</button></td>
            </tr>
            <tr v-if="!sources.length">
              <td colspan="8"><div class="empty">没有符合条件的记录</div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="data-table-footer">
      <span>源文件已修改时，请刷新读数后重新预览。</span>
      <div class="form-actions">
        <button class="btn" :disabled="busy" @click="client.invalidateQueries()">重新读取材料</button>
        <button class="btn soft" :disabled="busy" @click="jobAction('kb-preview', false)">重跑材料与切块预览</button>
        <button class="btn primary" :disabled="busy" @click="jobAction('kb-build', false)">离线建库</button>
        <button class="text-button" @click="router.push('/jobs?name=kb-')">作业状态与日志 →</button>
      </div>
    </div>
  </VPanel>
</template>
