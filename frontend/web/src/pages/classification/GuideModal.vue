<script setup lang="ts">
import { useRouter } from 'vue-router'
import { closeModal } from '../../composables/useModal'
const router = useRouter()
function go(path: string) {
  closeModal()
  router.push(path)
}
</script>

<template>
  <div class="modal-body">
    <p>主题页读取类目定义、分布与所选类目的服务端分页。分类器页读取既有验收、文件、评测、错例及服务健康结果。</p>
    <p class="section-gap">已有报告可查询；生成语料、训练、导出、评测和批量归类从作业中心核对后启动。单句试分类不写问题池。阈值配置不由页面自动应用。</p>
    <div class="section-gap"><button class="btn" @click="go('/jobs')">查看登记作业</button><button class="btn" @click="go('/topics')">查看咨询主题</button></div>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">知道了</button></div>
</template>
