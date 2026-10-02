<!-- 消息列表（对应 V2 messages(c, client)）：客户页隐藏内部备注，显示反馈按钮 -->
<script setup lang="ts">
import Icon from '../components/Icon.vue'
import { toast } from '../composables/useToast'
import { showDoc } from './actions'
import Avatar from './Avatar.vue'
import { demo, type Conversation, type Message } from './store'

const props = defineProps<{ conv: Conversation; client?: boolean }>()
const shown = (m: Message) => !props.client || m.role !== 'note'
const outgoing = (m: Message) => (props.client ? m.role === 'customer' : m.role === 'staff' || m.role === 'note')
const nameOf = (m: Message) =>
  m.role === 'customer' ? (props.client ? '我' : props.conv.name) : m.role === 'bot' ? 'Minihelp 助手' : m.role === 'note' ? '周小雨 · 内部备注' : '周小雨'
const docTitle = (id: number) => demo.docs.find((d) => d.id === id)?.title
// 客户反馈：只记录在演示数据里，不写入后台的知识缺口
function feedback(m: Message, rating: 'up' | 'down') {
  if (m.feedback) return
  m.feedback = rating
  toast(rating === 'down' ? '已记录"未解决"反馈（演示数据，不写入后台）' : '感谢反馈（演示）')
}
</script>

<template>
  <div class="day-divider">今天 · {{ client ? '您的专属服务' : '会话记录' }}</div>
  <template v-for="(m, i) in conv.messages" :key="i">
    <template v-if="shown(m)">
      <div v-if="m.role === 'system'" class="system-message"><span>{{ m.text }}</span></div>
      <article v-else class="message" :class="{ outgoing: outgoing(m), bot: m.role === 'bot' }">
        <span v-if="m.role === 'bot'" class="avatar small green"><Icon name="spark" /></span>
        <Avatar v-else :name="m.role === 'customer' ? conv.name : '周'" :color="m.role === 'customer' ? conv.color : 'green'" small />
        <div class="message-body">
          <div class="message-label"><b>{{ nameOf(m) }}</b><time>{{ m.time }}</time></div>
          <div class="bubble" :style="m.role === 'note' ? 'background:var(--amber-soft)' : undefined" style="white-space: pre-line">{{ m.text }}<button v-if="m.source" class="citation-link" @click="showDoc(m.source)"><Icon name="book" />{{ docTitle(m.source) }} <Icon name="chevron" /></button></div>
          <div v-if="m.role === 'note'" class="message-note">仅团队可见</div>
          <div v-else-if="m.role === 'bot' && !client" class="message-note">AI 回复 · 引用已发布知识</div>
          <div v-if="client && m.role === 'bot'" class="client-feedback">
            <button :class="{ chosen: m.feedback === 'up' }" :disabled="!!m.feedback" @click="feedback(m, 'up')">{{ m.feedback === 'up' ? '已反馈有帮助' : '有帮助' }}</button
            ><button :class="{ chosen: m.feedback === 'down' }" :disabled="!!m.feedback" @click="feedback(m, 'down')">{{ m.feedback === 'down' ? '已反馈未解决' : '未解决' }}</button>
          </div>
        </div>
      </article>
    </template>
  </template>
</template>
