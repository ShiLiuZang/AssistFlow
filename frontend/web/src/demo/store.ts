// 演示数据（客户咨询页、客服工作台、工单、客户、商品、设置共用）。
// 与 V2 prototype.js / service-panels.js 相同：只在内存中，刷新后重置，不调用任何接口。
import { computed, reactive } from 'vue'

export type Role = 'customer' | 'bot' | 'staff' | 'note' | 'system'
export interface Message {
  role: Role
  text: string
  time: string
  source?: number | null
  feedback?: 'up' | 'down'
}
export interface Conversation {
  id: number
  name: string
  color: string
  status: 'queued' | 'human' | 'auto'
  subject: string
  order: string
  product: string
  amount: string
  time: string
  tags: string[]
  messages: Message[]
}
export interface Doc {
  id: number
  title: string
  category: string
  scope: string
  status: 'published' | 'review' | 'draft'
  version: string
  date: string
  text: string
}
export interface Ticket {
  id: string
  customer: string
  conv: number
  title: string
  type: string
  status: 'open' | 'working' | 'resolved'
  priority: string
  time: string
  desc: string
  history: string[]
}
export interface Member {
  id: number
  name: string
  role: string
  status: 'active' | 'disabled'
  self?: boolean
}

export const now = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

export const demo = reactive({
  conversations: [
    {
      id: 1,
      name: '林女士',
      color: 'green',
      status: 'queued',
      subject: '退换货咨询',
      order: 'MH202609180021',
      product: '静音智能猫砂盆 · 奶油白',
      amount: '699.00',
      time: '14:32',
      tags: ['老客户', '售后咨询'],
      messages: [
        { role: 'customer', text: '你好，上周买的猫砂盆已经收到了，尺寸有点大，可以退吗？', time: '14:30' },
        { role: 'bot', text: '您好，您这笔订单仍在 7 天退货申请期内。若商品未使用、配件齐全，可申请退货；运费与包装要求需要进一步确认。', time: '14:30', source: 1 },
        { role: 'customer', text: '还没有使用，外包装已经拆了，想请人工帮我确认一下。', time: '14:31' },
        { role: 'system', text: '客户申请人工服务 · 进入待接待队列', time: '14:32' },
      ],
    },
    {
      id: 2,
      name: '王先生',
      color: 'blue',
      status: 'queued',
      subject: '物流进度',
      order: 'MH202609200018',
      product: '冻干双拼猫粮 · 2 kg',
      amount: '129.00',
      time: '14:28',
      tags: ['物流咨询'],
      messages: [{ role: 'customer', text: '物流两天没有更新了，能帮我查一下吗？', time: '14:28' }],
    },
    {
      id: 3,
      name: '陈女士',
      color: 'rose',
      status: 'human',
      subject: '商品咨询',
      order: 'MH202609210037',
      product: '陶瓷饮水机 · 月白',
      amount: '219.00',
      time: '14:24',
      tags: ['商品咨询'],
      messages: [
        { role: 'customer', text: '饮水机滤芯多久更换一次？', time: '14:24' },
        { role: 'staff', text: '您好，建议每 2–4 周更换一次，具体可参考使用频率和水质。', time: '14:25' },
      ],
    },
    {
      id: 4,
      name: '赵先生',
      color: '',
      status: 'auto',
      subject: '发货时效',
      order: 'MH202609210026',
      product: '猫抓板 · 原木色',
      amount: '59.00',
      time: '14:20',
      tags: ['新客户'],
      messages: [
        { role: 'customer', text: '今天下单什么时候发货？', time: '14:20' },
        { role: 'bot', text: '常规商品付款后 48 小时内发出，预售商品以商品页约定为准。', time: '14:20', source: 2 },
      ],
    },
    {
      id: 5,
      name: '许小姐',
      color: 'green',
      status: 'human',
      subject: '售后跟进',
      order: 'MH202609160039',
      product: '便携宠物包 · 苔绿',
      amount: '159.00',
      time: '14:15',
      tags: ['售后咨询'],
      messages: [
        { role: 'customer', text: '补发的肩带有单号了吗？', time: '14:15' },
        { role: 'staff', text: '我正在为您确认仓库的补发记录，稍后同步给您。', time: '14:16' },
      ],
    },
    {
      id: 6,
      name: '刘女士',
      color: 'blue',
      status: 'auto',
      subject: '商品选购',
      order: 'MH202609220003',
      product: '逗猫棒补充装 · 3 支',
      amount: '29.90',
      time: '14:09',
      tags: ['新客户'],
      messages: [
        { role: 'customer', text: '补充装适配旧款手柄吗？', time: '14:09' },
        { role: 'bot', text: '请提供手柄的型号或购买订单，以便确认接口是否兼容。', time: '14:09' },
      ],
    },
  ] as Conversation[],
  docs: [
    { id: 1, title: '退换货与售后政策', category: '售后政策', scope: '全部商品', status: 'published', version: 'v1.3', date: '09-21 16:40', text: '签收后 7 天内可申请退货。商品需未使用，配件齐全。拆开外包装不直接等同于商品已使用；具体包装状态由客服审核。特殊商品与活动订单以订单约定为准。申请通过后按指定地址寄回，仓库验收后进入退款处理。' },
    { id: 2, title: '配送范围与发货时效', category: '物流服务', scope: '全部商品', status: 'published', version: 'v1.2', date: '09-20 10:15', text: '常规现货商品付款后 48 小时内发出。预售、定制商品以商品页说明为准。物流超过 48 小时没有更新，可联系人工客服核查。' },
    { id: 3, title: '智能猫砂盆使用与保养', category: '商品说明', scope: '智能猫砂盆', status: 'review', version: 'v1.0', date: '09-22 09:30', text: '首次使用应放置在平整地面并保持通风，按说明书连接电源。猫砂容量不应超过刻度线。清洁前请断电，电子部件不可水洗。' },
    { id: 4, title: '包装与配件完整性说明', category: '售后政策', scope: '全部商品', status: 'published', version: 'v1.0', date: '09-18 11:20', text: '退货前请保留产品主机、说明书及全部配件。原包装拆封后，请拍照说明现状，由客服确认是否影响寄回与验收。' },
    { id: 5, title: '饮水机常见问题整理', category: '商品说明', scope: '陶瓷饮水机', status: 'draft', version: 'v0.1', date: '09-22 11:08', text: '待完善：滤芯更换周期、噪音排查、清洁步骤与断电保护说明。' },
  ] as Doc[],
  tickets: [
    { id: 'TK-1026', customer: '许小姐', conv: 5, title: '宠物包肩带缺件补发', type: '补发', status: 'working', priority: '普通', time: '09-22 13:40', desc: '已确认缺件，等待仓库提供补发物流单号。', history: ['客户反馈肩带缺失', '周小雨接单并联系仓库'] },
    { id: 'TK-1025', customer: '王先生', conv: 2, title: '猫粮订单物流停滞核查', type: '物流', status: 'open', priority: '优先', time: '09-22 11:20', desc: '物流超过 48 小时未更新，请核查运输状态。', history: ['由客服会话创建工单'] },
    { id: 'TK-1024', customer: '陈女士', conv: 3, title: '饮水机使用说明补充', type: '咨询', status: 'resolved', priority: '普通', time: '09-21 16:05', desc: '已提供完整的电子说明书，客户确认收到。', history: ['客服创建咨询工单', '已补充使用说明，工单已解决'] },
  ] as Ticket[],
  members: [
    { id: 1, name: '周小雨', role: '管理员', status: 'active', self: true },
    { id: 2, name: '陈主管', role: '主管', status: 'active' },
    { id: 3, name: '小许', role: '客服', status: 'active' },
    { id: 4, name: '知识运营', role: '知识运营', status: 'active' },
  ] as Member[],
  rules: { start: '09:00', end: '18:00', mode: 'assist', offline: 'ticket' },
  audit: [] as { time: string; action: string; detail: string }[],
  preferences: {} as Record<number, string>,
  seq: 1026,
})

// 页面内状态（切换页面后保留，与 V2 一致）
export const view = reactive({
  selected: 1,
  queue: 'all',
  search: '',
  mode: 'reply' as 'reply' | 'note',
  drafts: {} as Record<string, string>,
  clientDraft: '',
  ticketFilter: 'all',
  ticketSearch: '',
  customer: 1,
  customerQuery: '',
  customerFilter: 'all',
  customerTab: 'summary',
  productTab: 'orders',
  orderQuery: '',
  orderFilter: 'all',
  productQuery: '',
  settingsTab: 'members',
  sync: 'idle' as 'idle' | 'running' | 'done',
})

export const queuedCount = computed(() => demo.conversations.filter((c) => c.status === 'queued').length)
export const findConv = (id: number) => demo.conversations.find((c) => c.id === id)
export const relatedTickets = (c: Conversation) => demo.tickets.filter((t) => t.conv === c.id)
export const activeTickets = (c: Conversation) => relatedTickets(c).filter((t) => t.status !== 'resolved')
export const orderState = (c: Conversation) => ({ 1: '已签收', 2: '运输异常', 3: '已签收', 4: '待发货', 5: '已签收', 6: '待发货' })[c.id] ?? '未知'
export const orderColor = (c: Conversation) => (c.id === 2 ? 'amber' : [4, 6].includes(c.id) ? 'neutral' : '')
export const ticketLabel = { open: '待处理', working: '处理中', resolved: '已解决' } as const
export const ticketColor = (t: Ticket) => (t.status === 'open' ? 'amber' : t.status === 'working' ? 'blue' : '')
export const docLabel = (d: Doc) => (d.status === 'published' ? '已发布' : d.status === 'review' ? '待审核' : '草稿')
export const docColor = (d: Doc) => (d.status === 'published' ? '' : d.status === 'review' ? 'amber' : 'neutral')
export const match = (text: string, query: string) => text.toLowerCase().includes(query.trim().toLowerCase())
export const log = (action: string, detail: string) => demo.audit.unshift({ time: now(), action, detail })
