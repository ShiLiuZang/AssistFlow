<!-- V2 modal() 的默认页脚 -->
<script setup lang="ts">
import { closeModal } from '../../composables/useModal'
</script>

<template>
  <div class="modal-foot"><button class="btn" @click="closeModal">知道了</button></div>
</template>
