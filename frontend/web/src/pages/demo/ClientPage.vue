<!-- 客户咨询页（对应 V2 prototype.js 的 client） -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import Icon from '../../components/Icon.vue'
import { toast } from '../../composables/useToast'
import { newTicket, showClientTickets, showDoc, showNote, showOrder } from '../../demo/actions'
import ChatMessages from '../../demo/ChatMessages.vue'
import { demo, now, view } from '../../demo/store'

const catUrl = `${import.meta.env.BASE_URL}assets/minihelp-cat.svg`
const c = computed(() => demo.conversations[0])
const status = computed(() => (c.value.status === 'human' ? '周小雨正在为您服务' : c.value.status === 'queued' ? '已转人工，等待客服接待' : 'Minihelp 助手在线'))
const list = ref<HTMLElement | null>(null)
const box = ref<HTMLTextAreaElement | null>(null)
const scroll = () => nextTick(() => list.value && (list.value.scrollTop = list.value.scrollHeight))
watch(() => c.value.messages.length, scroll)

function send(preset?: string) {
  const text = preset ?? view.clientDraft.trim()
  if (!text) {
    toast('先输入咨询内容')
    return
  }
  c.value.messages.push({ role: 'customer', text, time: now() })
  c.value.time = now()
  if (!preset) view.clientDraft = ''
  if (c.value.status === 'auto') {
    const source = /退|包装|售后/.test(text) ? 1 : /快递|发货|物流/.test(text) ? 2 : null
    c.value.messages.push({
      role: 'bot',
      text:
        source === 1
          ? '可以先提交退货申请。未使用、配件齐全的商品通常可申请；拆封包装的具体状态需要客服确认。'
          : source === 2
            ? '常规现货商品付款后 48 小时内发出。物流长时间未更新时，我们可以转人工协助核查。'
            : '收到您的咨询。请补充商品型号或订单信息，也可以选择转人工进一步沟通。',
      time: now(),
      source,
    })
  }
  box.value?.focus()
  if (c.value.status !== 'auto') toast(c.value.status === 'queued' ? '消息已加入待接待会话' : '消息已同步到客服工作台')
}
function handoff() {
  if (c.value.status === 'human') return toast('周小雨已接管，可在客服工作台继续回复')
  if (c.value.status === 'queued') return toast('您已在待接待队列中，可切换工作台接管')
  c.value.status = 'queued'
  c.value.messages.push({ role: 'system', text: '客户申请人工服务 · 等待客服接待', time: now() })
  toast('已转入客服工作台的待接待队列')
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}
const serviceInfo = () =>
  showNote(
    '服务说明',
    '<p>AI 助手可协助解答常见问题。需要进一步核查订单、确认售后条件或人工帮助时，可以选择转人工。</p><div class="notice" style="margin-top:18px">本页面使用演示客户与预设回复。所有操作只在当前预览中生效。</div>',
  )
</script>

<template>
  <main class="client-shell">
    <header class="store-header">
      <div class="store-brand"><img :src="catUrl" alt="" />喵喵优选</div>
      <nav class="store-nav" aria-label="店铺服务">
        <button class="active" @click="box?.focus()">在线咨询</button><button @click="showOrder(1)">我的订单</button><button @click="showClientTickets">服务记录</button>
      </nav>
    </header>
    <div class="client-grid">
      <section class="client-intro">
        <div class="eyebrow">HERE TO HELP YOU</div>
        <h1>关于小家伙的一切，<br />我们都认真对待。</h1>
        <p>从选购建议到订单售后，<br />有问题，就来聊一聊。</p>
        <div class="help-links">
          <button class="help-link" @click="showOrder(1)"><Icon name="box" />查询我的订单</button
          ><button class="help-link" @click="showDoc(1)"><Icon name="back" />了解退换货</button
          ><button class="help-link" @click="send('我想了解商品的使用方法')"><Icon name="book" />商品使用帮助</button
          ><button class="help-link" @click="handoff"><Icon name="headset" />联系人工客服</button>
        </div>
        <div class="client-note"><Icon name="shield" />当前为演示会话，不涉及真实订单</div>
      </section>
      <section class="client-window" aria-label="客户咨询窗口">
        <header class="chat-header">
          <span class="avatar green"><Icon :name="c.status === 'human' ? 'headset' : 'spark'" /></span>
          <div>
            <h2>喵喵优选 · 在线客服</h2>
            <div class="chat-meta"><span class="dot" :class="{ amber: c.status === 'queued' }"></span>{{ status }}</div>
          </div>
          <button class="icon-btn" aria-label="服务说明" @click="serviceInfo"><Icon name="info" /></button>
        </header>
        <div id="client-messages" ref="list" class="chat-messages"><ChatMessages :conv="c" client /></div>
        <div class="client-quick">
          <button @click="showOrder(1)">查询订单</button><button @click="newTicket(1, true)">申请退货</button><button @click="handoff">转人工</button>
        </div>
        <div class="composer">
          <div class="composer-box">
            <textarea id="client-draft" ref="box" v-model="view.clientDraft" aria-label="咨询内容" placeholder="说说你遇到的问题…" maxlength="2000" @keydown="onKey"></textarea>
            <div class="composer-foot">
              <span class="small muted" style="padding-left: 4px">演示聊天 · 刷新后重置</span><span class="spacer"></span
              ><button class="btn primary" @click="send()">发送 <Icon name="send" /></button>
            </div>
          </div>
        </div>
        <div class="powered">服务支持 <b>Minihelp</b> · 温暖，也高效</div>
      </section>
    </div>
  </main>
</template>
