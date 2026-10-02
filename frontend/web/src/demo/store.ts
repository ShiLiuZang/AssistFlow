// 演示数据（客服工作台、工单、客户等演示页面共用）。迁移各演示页时补全。
import { computed, reactive } from 'vue'

export const demo = reactive({
  conversations: [
    { id: 1, status: 'queued' },
    { id: 2, status: 'queued' },
    { id: 3, status: 'human' },
    { id: 4, status: 'auto' },
    { id: 5, status: 'human' },
  ] as { id: number; status: string }[],
})

export const queuedCount = computed(() => demo.conversations.filter((c) => c.status === 'queued').length)
