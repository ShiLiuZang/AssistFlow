<!-- 转交会话给其他坐席 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { closeModal } from '../../composables/useModal'
import { ROLE_NAMES, type Role } from '../../auth/session'
import { listStaff } from '../../api/agent'

const props = defineProps<{ current: string | null; onConfirm: (to: string) => Promise<void> }>()
const staff = useQuery({ queryKey: ['agent', 'staff'], queryFn: listStaff })
const choices = computed(() => (staff.data.value ?? []).filter((s) => s.username !== props.current))
const target = ref('')
const busy = ref(false)
async function confirm() {
  if (!target.value) return
  busy.value = true
  try {
    await props.onConfirm(target.value)
    closeModal()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="modal-body">
    <p v-if="staff.isLoading.value" class="muted">正在读取坐席列表…</p>
    <p v-else-if="staff.error.value" class="notice amber">{{ staff.error.value.message }}</p>
    <p v-else-if="!choices.length" class="muted">没有其他可转交的坐席账号。</p>
    <label v-else class="field">转交给<select v-model="target"><option value="" disabled>选择坐席</option><option v-for="s in choices" :key="s.username" :value="s.username">{{ s.username }}（{{ ROLE_NAMES[s.role as Role] ?? s.role }}）</option></select></label>
    <p class="field-hint">转交记录会以内部备注保存，顾客看不到。</p>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">取消</button><button class="btn primary" :disabled="!target || busy" @click="confirm">确认转交</button></div>
</template>
