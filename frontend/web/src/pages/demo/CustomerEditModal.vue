<script setup lang="ts">
import { computed, ref } from 'vue'
import { closeModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { demo, findConv } from '../../demo/store'
const props = defineProps<{ id: number }>()
const c = computed(() => findConv(props.id)!)
const tags = ref(c.value.tags.join('，'))
const preference = ref(demo.preferences[props.id] || '优先站内回复')
const error = ref('')
function save() {
  const list = [...new Set(tags.value.split(/[,，]/).map((t) => t.trim()).filter(Boolean))]
  if (list.length > 5 || list.some((t) => t.length > 12)) {
    error.value = '最多填写 5 个标签，每个不超过 12 字。'
    return
  }
  c.value.tags = list
  demo.preferences[props.id] = preference.value
  closeModal()
  toast('演示客户资料已更新')
}
</script>

<template>
  <div class="modal-body">
    <form id="customer-edit-form" @submit.prevent="save">
      <label class="field"
        >客户标签<input v-model="tags" name="tags" maxlength="100" /><span class="field-hint">最多 5 个标签，用逗号分隔，每个标签不超过 12 字。</span></label
      >
      <label class="field"
        >联系偏好<select v-model="preference" name="preference">
          <option v-for="v in ['优先站内回复', '工作时间联系', '等待客户主动联系']" :key="v">{{ v }}</option>
        </select></label
      >
      <p class="quiet-note">仅修改演示资料；标签会同步出现在客服工作台。</p>
      <p id="customer-edit-error" class="form-error" role="alert">{{ error }}</p>
    </form>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">取消</button><button class="btn primary" type="submit" form="customer-edit-form">保存资料</button></div>
</template>
