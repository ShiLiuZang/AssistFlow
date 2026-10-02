<!-- 坐席看到的会话记录：顾客、AI、坐席回复、内部备注、系统提示 -->
<script setup lang="ts">
import Icon from '../../components/Icon.vue'
import Avatar from '../../demo/Avatar.vue'
import { shortTime, type AgentMessage } from '../../api/agent'

defineProps<{ messages: AgentMessage[]; customer: string }>()
const name = (m: AgentMessage, customer: string) =>
  m.role === 'customer' ? customer : m.role === 'bot' ? 'Minihelp 助手' : m.role === 'note' ? `${m.author ?? '坐席'} · 内部备注` : (m.author ?? '坐席')
</script>

<template>
  <div class="day-divider">会话记录</div>
  <template v-for="m in messages" :key="m.id">
    <div v-if="m.role === 'system'" class="system-message"><span>{{ m.content }} · {{ shortTime(m.created_at) }}</span></div>
    <article v-else class="message" :class="{ outgoing: m.role === 'staff' || m.role === 'note', bot: m.role === 'bot' }">
      <span v-if="m.role === 'bot'" class="avatar small green"><Icon name="spark" /></span>
      <Avatar v-else :name="m.role === 'customer' ? customer : (m.author ?? '坐')" :color="m.role === 'customer' ? 'blue' : 'green'" small />
      <div class="message-body">
        <div class="message-label"><b>{{ name(m, customer) }}</b><time>{{ shortTime(m.created_at) }}</time></div>
        <div class="bubble" :style="m.role === 'note' ? 'background:var(--amber-soft)' : undefined" style="white-space: pre-line">{{ m.content }}</div>
        <div v-if="m.role === 'note'" class="message-note">仅团队可见</div>
        <div v-else-if="m.role === 'bot'" class="message-note">AI 回复</div>
      </div>
    </article>
  </template>
  <div v-if="!messages.length" class="empty"><p>这个会话还没有消息</p></div>
</template>
