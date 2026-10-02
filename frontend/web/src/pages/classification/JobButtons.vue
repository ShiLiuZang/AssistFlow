<!-- 验收卡与报告下方的"重跑 xxx"按钮：核对作业状态后启动，完成后去作业中心 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { actionBusy, jobAction } from '../../composables/useAdminActions'
import { closeModal } from '../../composables/useModal'
import { jobTitles } from './shared'

const props = defineProps<{ jobs?: string[] }>()
const router = useRouter()
const buttons = computed(() => (props.jobs || []).filter((name) => Object.hasOwn(jobTitles, name)))
const run = (name: string) =>
  jobAction(name, false, () => {
    closeModal()
    router.push('/jobs')
  })
</script>

<template>
  <div class="cls-job-actions">
    <button v-for="name in buttons" :key="name" class="btn soft" :disabled="actionBusy" @click="run(name)">重跑 {{ jobTitles[name] }}</button>
  </div>
</template>
