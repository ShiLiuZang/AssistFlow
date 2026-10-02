<script setup lang="ts">
import { computed } from 'vue'
import Icon from '../components/Icon.vue'
import { closeModal } from '../composables/useModal'
import { showDoc } from './actions'
import { demo, docLabel, findConv } from './store'
const props = defineProps<{ id: number }>()
const c = computed(() => findConv(props.id)!)
const related = computed(() => demo.docs.filter((d) => d.scope === '全部商品' || c.value.product.includes(d.scope)))
</script>

<template>
  <div class="modal-body">
    <div class="linked-order">
      <div class="image-placeholder">商品图待补</div>
      <div>
        <h3>{{ c.product }}</h3>
        <small class="mono">SKU-{{ String(c.id).padStart(4, '0') }}</small><span>订单快照 ¥ {{ c.amount }}</span>
      </div>
    </div>
    <dl class="property-grid">
      <div><dt>实时库存</dt><dd>待接入</dd></div>
      <div><dt>当前售价</dt><dd>待接入</dd></div>
    </dl>
    <div class="section-heading"><h3>相关知识</h3><span>含草稿与待审内容</span></div>
    <button v-for="d in related" :key="d.id" class="relation-row" @click="showDoc(d.id)">
      <span class="relation-icon"><Icon name="book" /></span
      ><span
        ><strong>{{ d.title }}</strong><small>{{ d.version }} · {{ docLabel(d) }}</small></span
      ><Icon name="chevron" />
    </button>
    <div class="quiet-note">商品图片和实时字段待提供；示例资料不用于判断实际库存或售后资格。</div>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">知道了</button></div>
</template>
