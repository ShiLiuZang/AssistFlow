<!-- 产物文件表（对应 V2 fileRows） -->
<script setup lang="ts">
import type { FileStat } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VTable from '../../components/VTable.vue'
import { openModal } from '../../composables/useModal'
import { bytes, fileContext, filename, num, stamp } from '../classification/shared'
import FileModal from './FileModal.vue'
defineProps<{ heads: string[]; files: FileStat[] }>()
const show = (file: FileStat) => openModal({ title: '产物元信息', view: FileModal, props: { file }, cls: 'classification-dialog' })
</script>

<template>
  <VTable :heads="heads" :empty="!files.length">
    <tr v-for="(f, i) in files" :key="i">
      <td class="mono cls-path">{{ f.file || filename(f.path) }}<span class="table-sub">{{ fileContext(f) }}</span></td>
      <td>
        <StatusPill v-if="f.present === true">文件存在</StatusPill><StatusPill v-else-if="f.present === false" color="amber">文件缺失</StatusPill
        ><StatusPill v-else color="neutral">未知</StatusPill>
      </td>
      <td>{{ f.present === true ? bytes(f.bytes) : '—' }}</td>
      <td>{{ f.present === true ? num(f.lines) : '—' }}</td>
      <td>{{ f.present === true ? stamp(f.mtime) : '—' }}</td>
      <td><button class="table-actions" @click="show(f)">详情</button></td>
    </tr>
  </VTable>
</template>
