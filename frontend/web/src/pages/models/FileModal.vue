<script setup lang="ts">
import type { FileStat } from '../../api/types'
import ModalFoot from '../reports/ModalFoot.vue'
import MetaRow from '../classification/MetaRow.vue'
import { bytes } from '../classification/shared'
defineProps<{ file: FileStat }>()
</script>

<template>
  <div class="modal-body">
    <MetaRow
      :items="[
        ['文件路径', file.path],
        ['是否存在', file.present === true ? '存在' : file.present === false ? '缺失' : '未知'],
        ['大小', file.present === true ? bytes(file.bytes) : null],
        ['记录行数', file.present === true ? file.lines : null],
        ['更新时间', file.present === true ? file.mtime : null],
        ['用途', file.desc || file.stage || '未提供'],
      ]"
    />
    <p class="small muted">当前查询仅提供文件元信息，不读取文件正文。</p>
  </div>
  <ModalFoot />
</template>
