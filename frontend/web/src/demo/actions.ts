// 演示页共用的弹窗入口（订单、工单、知识、商品、服务记录）
import SimpleModal from '../components/SimpleModal.vue'
import { openModal } from '../composables/useModal'
import ClientTicketsModal from './ClientTicketsModal.vue'
import DocModal from './DocModal.vue'
import OrderModal from './OrderModal.vue'
import ProductModal from './ProductModal.vue'
import TicketFormModal from './TicketFormModal.vue'
import TicketModal from './TicketModal.vue'
import { demo } from './store'

export const showOrder = (id: number) => openModal({ title: '订单详情', view: OrderModal, props: { id } })
export const showProduct = (id: number) => openModal({ title: '商品资料', view: ProductModal, props: { id } })
export const showDoc = (id: number) => {
  const d = demo.docs.find((x) => x.id === id)
  if (d) openModal({ title: d.title, view: DocModal, props: { id } })
}
export function showTicket(id: string, fromClient = false) {
  const t = demo.tickets.find((x) => x.id === id)
  if (t) openModal({ title: t.title, view: TicketModal, props: { id, fromClient } })
}
// 客户已有未完结的退货工单时，直接打开它，不重复申请
export function newTicket(id: number, fromClient = false) {
  const existing = fromClient && demo.tickets.find((t) => t.conv === 1 && t.type === '退货' && t.status !== 'resolved')
  if (existing) showTicket(existing.id, true)
  else openModal({ title: fromClient ? '确认退货申请' : '新建工单', view: TicketFormModal, props: { id, fromClient } })
}
export const showClientTickets = () => openModal({ title: '我的服务记录', view: ClientTicketsModal })
export const showNote = (title: string, html: string) => openModal({ title, view: SimpleModal, props: { html } })
