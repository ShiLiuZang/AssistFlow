<!-- 商品与订单（对应 V2 service-panels.js 的 productsPage） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { toast } from '../../composables/useToast'
import { showOrder, showProduct } from '../../demo/actions'
import { activeTickets, demo, log, match, orderColor, orderState, view } from '../../demo/store'
import ServiceHeading from './ServiceHeading.vue'

const router = useRouter()
const aftersales = computed(() => demo.conversations.filter((c) => activeTickets(c).length).length)
const orders = computed(() =>
  demo.conversations.filter(
    (c) =>
      match(`${c.order} ${c.name} ${c.product}`, view.orderQuery) &&
      (view.orderFilter === 'all' || (view.orderFilter === 'exception' && c.id === 2) || (view.orderFilter === 'aftersales' && activeTickets(c).length)),
  ),
)
const products = computed(() => demo.conversations.filter((c) => match(c.product, view.productQuery)))
function sync() {
  view.sync = 'running'
  setTimeout(() => {
    view.sync = 'done'
    log('同步演示', '沿用现有商品与订单样例')
    toast('同步演示完成，没有连接外部平台')
  }, 900)
}
function viewCustomer(id: number) {
  view.customer = id
  view.customerQuery = ''
  view.customerFilter = 'all'
  view.customerTab = 'summary'
  router.push('/customers')
}
function resetOrders() {
  view.orderQuery = ''
  view.orderFilter = 'all'
}
</script>

<template>
  <div class="page admin-page service-page">
    <ServiceHeading eyebrow="COMMERCE CONTEXT" title="商品与订单" desc="查询交易上下文，衔接每一步售后。">
      <button class="btn" :disabled="view.sync === 'running'" @click="sync"><Icon name="clock" />{{ view.sync === 'running' ? '演示同步中…' : '演示同步' }}</button>
    </ServiceHeading>
    <nav class="section-tabs" aria-label="商品与订单子页面">
      <button
        v-for="[id, label] in [
          ['orders', '订单列表'],
          ['catalog', '商品目录'],
        ]"
        :key="id"
        :class="{ active: view.productTab === id }"
        :aria-pressed="view.productTab === id"
        @click="view.productTab = id"
      >
        {{ label }}
      </button>
    </nav>
    <div v-if="view.sync === 'done'" class="notice">已完成前端同步演示，沿用当前样例；没有获取真实平台数据。</div>
    <template v-if="view.productTab === 'orders'">
      <div class="compact-metrics">
        <span>演示订单 <b>{{ demo.conversations.length }}</b></span><span>需核查物流 <b>1</b></span><span>售后跟进中 <b>{{ aftersales }}</b></span>
      </div>
      <section class="panel">
        <div class="panel-toolbar">
          <div class="filter-row">
            <button
              v-for="[id, label] in [
                ['all', '全部订单'],
                ['exception', '物流异常'],
                ['aftersales', '售后跟进'],
              ]"
              :key="id"
              class="filter-chip"
              :class="{ active: view.orderFilter === id }"
              :aria-pressed="view.orderFilter === id"
              @click="view.orderFilter = id"
            >
              {{ label }}
            </button>
          </div>
          <label class="search"><Icon name="search" /><input id="order-search" v-model="view.orderQuery" aria-label="搜索订单" placeholder="订单号、客户或商品" /></label>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>订单编号</th>
                <th>商品</th>
                <th>客户</th>
                <th>实付金额</th>
                <th>物流状态</th>
                <th>售后</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="order-rows">
              <tr v-for="c in orders" :key="c.id">
                <td><button class="table-actions table-title mono" @click="showOrder(c.id)">{{ c.order }}</button><span class="table-sub">Web · 演示订单</span></td>
                <td><strong class="table-title">{{ c.product }}</strong><span class="table-sub">数量 1 · 商品快照</span></td>
                <td><button class="table-actions" @click="viewCustomer(c.id)">{{ c.name }}</button></td>
                <td class="mono">¥ {{ c.amount }}</td>
                <td><StatusPill :color="orderColor(c)">{{ orderState(c) }}</StatusPill></td>
                <td>
                  <StatusPill v-if="activeTickets(c).length" color="amber">{{ activeTickets(c).length }} 笔待跟进</StatusPill><span v-else class="muted">—</span>
                </td>
                <td><button class="table-actions" @click="showOrder(c.id)">详情 <Icon name="chevron" /></button></td>
              </tr>
              <tr v-if="!orders.length">
                <td colspan="7">
                  <div class="empty">
                    <p>没有匹配的订单</p>
                    <button class="btn" @click="resetOrders">清除筛选</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="panel-footer">当前展示 6 笔样例订单，金额与物流均非真实业务数据。</div>
      </section>
    </template>
    <template v-else>
      <div class="catalog-toolbar">
        <p class="muted">商品信息用于查看咨询上下文，库存与价格以正式业务系统为准。</p>
        <label class="search"><Icon name="search" /><input id="product-search" v-model="view.productQuery" aria-label="搜索商品" placeholder="搜索商品名称" /></label>
      </div>
      <div id="product-grid" class="catalog-grid">
        <article v-for="c in products" :key="c.id" class="catalog-card">
          <div class="catalog-image">
            <div class="image-placeholder">商品图片待补</div>
            <span class="muted small">演示商品</span>
          </div>
          <div class="catalog-body">
            <div class="between">
              <span class="mono small muted">SKU-{{ String(c.id).padStart(4, '0') }}</span><StatusPill color="neutral">样例</StatusPill>
            </div>
            <h3>{{ c.product }}</h3>
            <div class="catalog-price">¥ {{ c.amount }}<span>订单价格快照</span></div>
            <div class="catalog-bottom">
              <span class="small muted">实时库存待接入</span><button class="text-button" @click="showProduct(c.id)">商品资料 <Icon name="arrow" /></button>
            </div>
          </div>
        </article>
        <div v-if="!products.length" class="empty">
          <p>没有匹配的商品</p>
          <button class="btn" @click="view.productQuery = ''">清除筛选</button>
        </div>
      </div>
    </template>
  </div>
</template>
