<script setup lang="ts">
import { computed, ref } from 'vue'
import { closeModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { demo, log } from '../../demo/store'
const props = defineProps<{ id: number }>()
const m = computed(() => demo.members.find((x) => x.id === props.id)!)
const role = ref(m.value.role)
const status = ref(m.value.status)
function save() {
  m.value.role = role.value
  m.value.status = status.value
  log('成员设置', `${m.value.name} · ${m.value.role} · ${m.value.status === 'active' ? '启用' : '停用'}`)
  closeModal()
  toast('演示角色已更新，不改变实际权限')
}
</script>

<template>
  <div class="modal-body">
    <form id="member-edit-form" @submit.prevent="save">
      <label class="field"
        >角色<select v-model="role" name="role">
          <option v-for="r in ['管理员', '主管', '客服', '知识运营']" :key="r">{{ r }}</option>
        </select></label
      >
      <label class="field"
        >成员状态<select v-model="status" name="status">
          <option value="active">启用</option>
          <option value="disabled">停用</option>
        </select></label
      >
      <div class="notice">这里只演示设置流程，不修改任何真实账号和访问权限。</div>
    </form>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">取消</button><button class="btn primary" type="submit" form="member-edit-form">保存演示设置</button></div>
</template>
