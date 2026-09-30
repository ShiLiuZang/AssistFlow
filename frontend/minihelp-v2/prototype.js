/* Minihelp V2. Local, in-memory demonstration. No API calls or real customer data. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const paths = {
    chat:'M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2a8.5 8.5 0 0 1 8.5 8.5ZM7 10h10M7 14h6',
    ticket:'M4 4h16v5a3 3 0 0 0 0 6v5H4v-5a3 3 0 0 0 0-6V4Zm10 0v3m0 3v4m0 3v3',
    users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M15 3a4 4 0 0 1 0 8m7 10v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    box:'m12 3 9 5v10l-9 5-9-5V8l9-5Zm0 10 9-5M12 13 3 8m9 5v10M7.5 5.5l9 5',
    book:'M12 5c-3-2-7-2-10-1v16c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Zm0 0v16',
    chart:'M3 3v18h18M7 16v-5m5 5V7m5 9v-8',
    settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4 4l3 1 2-3h6l2 3 3-1 2 5-2 3 2 3-2 5-3-1-2 3H9l-2-3-3 1-2-5 2-3-2-3 2-5Z',
    search:'m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
    chevron:'m8 5 7 7-7 7', down:'m6 9 6 6 6-6', plus:'M12 5v14M5 12h14',
    arrow:'M5 12h14m-6-6 6 6-6 6', close:'m6 6 12 12M6 18 18 6',
    check:'m5 12 4 4L19 6', clock:'M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
    send:'m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13',
    file:'M14 2H4v20h16V8l-6-6Zm0 0v6h6M8 13h8m-8 4h5',
    headset:'M3 14v-2a9 9 0 0 1 18 0v2M3 12h3v8H3v-8Zm15 0h3v8h-3v-8Zm3 8v2h-8',
    shield:'m12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6l9-4Zm-4 10 3 3 5-6',
    truck:'M1 4h13v13H1V4Zm13 5h4l4 4v4h-8M8 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm12 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
    back:'M20 12H4m6-6-6 6 6 6', info:'M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z'
  };
  const icon = name => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.chat}"/></svg>`;
  const avatar = (name, color = '', small = false) => `<span class="avatar ${color} ${small ? 'small' : ''}">${esc(name.slice(0, 1))}</span>`;
  const now = () => new Date().toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
  const conversations = [
    {id:1,name:'林女士',color:'green',status:'queued',subject:'退换货咨询',order:'MH202609180021',product:'静音智能猫砂盆 · 奶油白',amount:'699.00',time:'14:32',tags:['老客户','售后咨询'],messages:[
      {role:'customer',text:'你好，上周买的猫砂盆已经收到了，尺寸有点大，可以退吗？',time:'14:30'},
      {role:'bot',text:'您好，您这笔订单仍在 7 天退货申请期内。若商品未使用、配件齐全，可申请退货；运费与包装要求需要进一步确认。',time:'14:30',source:1},
      {role:'customer',text:'还没有使用，外包装已经拆了，想请人工帮我确认一下。',time:'14:31'},
      {role:'system',text:'客户申请人工服务 · 进入待接待队列',time:'14:32'}]},
    {id:2,name:'王先生',color:'blue',status:'queued',subject:'物流进度',order:'MH202609200018',product:'冻干双拼猫粮 · 2 kg',amount:'129.00',time:'14:28',tags:['物流咨询'],messages:[{role:'customer',text:'物流两天没有更新了，能帮我查一下吗？',time:'14:28'}]},
    {id:3,name:'陈女士',color:'rose',status:'human',subject:'商品咨询',order:'MH202609210037',product:'陶瓷饮水机 · 月白',amount:'219.00',time:'14:24',tags:['商品咨询'],messages:[{role:'customer',text:'饮水机滤芯多久更换一次？',time:'14:24'},{role:'staff',text:'您好，建议每 2–4 周更换一次，具体可参考使用频率和水质。',time:'14:25'}]},
    {id:4,name:'赵先生',color:'',status:'auto',subject:'发货时效',order:'MH202609210026',product:'猫抓板 · 原木色',amount:'59.00',time:'14:20',tags:['新客户'],messages:[{role:'customer',text:'今天下单什么时候发货？',time:'14:20'},{role:'bot',text:'常规商品付款后 48 小时内发出，预售商品以商品页约定为准。',time:'14:20',source:2}]},
    {id:5,name:'许小姐',color:'green',status:'human',subject:'售后跟进',order:'MH202609160039',product:'便携宠物包 · 苔绿',amount:'159.00',time:'14:15',tags:['售后咨询'],messages:[{role:'customer',text:'补发的肩带有单号了吗？',time:'14:15'},{role:'staff',text:'我正在为您确认仓库的补发记录，稍后同步给您。',time:'14:16'}]},
    {id:6,name:'刘女士',color:'blue',status:'auto',subject:'商品选购',order:'MH202609220003',product:'逗猫棒补充装 · 3 支',amount:'29.90',time:'14:09',tags:['新客户'],messages:[{role:'customer',text:'补充装适配旧款手柄吗？',time:'14:09'},{role:'bot',text:'请提供手柄的型号或购买订单，以便确认接口是否兼容。',time:'14:09'}]}
  ];
  const docs = [
    {id:1,title:'退换货与售后政策',category:'售后政策',scope:'全部商品',status:'published',version:'v1.3',date:'09-21 16:40',text:'签收后 7 天内可申请退货。商品需未使用，配件齐全。拆开外包装不直接等同于商品已使用；具体包装状态由客服审核。特殊商品与活动订单以订单约定为准。申请通过后按指定地址寄回，仓库验收后进入退款处理。'},
    {id:2,title:'配送范围与发货时效',category:'物流服务',scope:'全部商品',status:'published',version:'v1.2',date:'09-20 10:15',text:'常规现货商品付款后 48 小时内发出。预售、定制商品以商品页说明为准。物流超过 48 小时没有更新，可联系人工客服核查。'},
    {id:3,title:'智能猫砂盆使用与保养',category:'商品说明',scope:'智能猫砂盆',status:'review',version:'v1.0',date:'09-22 09:30',text:'首次使用应放置在平整地面并保持通风，按说明书连接电源。猫砂容量不应超过刻度线。清洁前请断电，电子部件不可水洗。'},
    {id:4,title:'包装与配件完整性说明',category:'售后政策',scope:'全部商品',status:'published',version:'v1.0',date:'09-18 11:20',text:'退货前请保留产品主机、说明书及全部配件。原包装拆封后，请拍照说明现状，由客服确认是否影响寄回与验收。'},
    {id:5,title:'饮水机常见问题整理',category:'商品说明',scope:'陶瓷饮水机',status:'draft',version:'v0.1',date:'09-22 11:08',text:'待完善：滤芯更换周期、噪音排查、清洁步骤与断电保护说明。'}
  ];
  const tickets = [
    {id:'TK-1026',customer:'许小姐',conv:5,title:'宠物包肩带缺件补发',type:'补发',status:'working',priority:'普通',time:'09-22 13:40',desc:'已确认缺件，等待仓库提供补发物流单号。',history:['客户反馈肩带缺失','周小雨接单并联系仓库']},
    {id:'TK-1025',customer:'王先生',conv:2,title:'猫粮订单物流停滞核查',type:'物流',status:'open',priority:'优先',time:'09-22 11:20',desc:'物流超过 48 小时未更新，请核查运输状态。',history:['由客服会话创建工单']},
    {id:'TK-1024',customer:'陈女士',conv:3,title:'饮水机使用说明补充',type:'咨询',status:'resolved',priority:'普通',time:'09-21 16:05',desc:'已提供完整的电子说明书，客户确认收到。',history:['客服创建咨询工单','已补充使用说明，工单已解决']}
  ];
  const state = {surface:'workbench',page:'workbench',selected:1,queue:'all',search:'',mode:'reply',drafts:{},clientDraft:'',docFilter:'all',docSearch:'',ticketFilter:'all',ticketSearch:'',palette:0,seq:1026};
  const current = () => conversations.find(c => c.id === state.selected);
  const pill = (text, color = '') => `<span class="pill ${color}">${esc(text)}</span>`;
  const convStatus = c => c.status === 'queued' ? pill('待接待','amber') : c.status === 'human' ? pill('人工接待','blue') : pill('AI 接待');
  const docStatus = d => d.status === 'published' ? pill('已发布') : d.status === 'review' ? pill('待审核','amber') : pill('草稿','neutral');
  const ticketStatus = t => t.status === 'open' ? pill('待处理','amber') : t.status === 'working' ? pill('处理中','blue') : pill('已解决');
  const navItem = (page, label, ico, count = '') => `<button class="nav-item ${state.page === page ? 'active' : ''}" data-page="${page}" title="${label}" ${state.page === page ? 'aria-current="page"' : ''}>${icon(ico)}<span class="nav-name">${label}</span>${count ? `<span class="nav-count">${count}</span>` : ''}</button>`;
  function shell(content, title) {
    const admin = state.surface==='admin';
    return `<div class="shell"><aside class="sidebar"><div class="brand"><img src="assets/minihelp-cat.svg" alt=""><span>Minihelp</span></div>
      <button class="workspace-selector" data-action="workspace"><span class="shop-letter">喵</span><span>喵喵优选</span>${icon('down')}</button>
      ${admin?`<nav class="nav-group" aria-label="管理总览">${navItem('overview','管理总览','chart')}</nav><p class="nav-label">知识与质量</p><nav class="nav-group" aria-label="知识与质量">${navItem('knowledge','知识中心','book')}${navItem('review','知识缺口','search',panels.pendingReviews())}${navItem('quality','RAG 质量','shield')}</nav><p class="nav-label">运营与模型</p><nav class="nav-group" aria-label="运营与模型">${navItem('observability','观测与成本','chart')}${navItem('topics','咨询主题','chat')}${navItem('models','分类器管理','spark')}${navItem('jobs','作业中心','clock')}</nav><nav class="nav-group nav-bottom" aria-label="系统与规划">${navItem('migration','原功能对照','file')}${navItem('settings','设置与权限','settings')}</nav>`:`<p class="nav-label">服务工作区</p><nav class="nav-group" aria-label="服务页面">${navItem('workbench','会话工作台','chat',conversations.filter(c=>c.status==='queued').length)}${navItem('tickets','工单中心','ticket')}${navItem('customers','客户资料','users')}${navItem('products','商品与订单','box')}</nav><p class="nav-label">运营管理</p><nav class="nav-group" aria-label="管理页面">${navItem('overview','进入管理后台','chart')}${navItem('migration','原功能对照','file')}</nav>`}
      <div class="rail-note">每一次对话，<br>都值得被认真回应。</div><div class="operator">${avatar('周')}<div>周小雨<small>${admin?'管理员':'客服'} · 演示视角</small></div><button class="icon-btn" data-action="profile" aria-label="当前账号">${icon('down')}</button></div></aside>
      <main class="main"><header class="topbar"><button class="btn menu-trigger" data-action="nav-menu" aria-label="打开页面菜单">${icon('book')}菜单</button><div class="breadcrumb">喵喵优选<span>/</span><strong>${title}</strong></div><div class="top-tools"><span class="small muted">${icon('clock')} 演示工作日 · 09 / 22</span><span class="pill neutral">${admin?'数据演示':'演示接待'}</span><button class="icon-btn" data-action="guide" aria-label="操作说明">${icon('info')}</button></div></header>${content}</main></div>`;
  }
  function queueList() {
    const filtered = conversations.filter(c => (state.queue === 'all' || c.status === (state.queue === 'waiting' ? 'queued' : 'human')) && `${c.name}${c.subject}${c.order}`.toLowerCase().includes(state.search.toLowerCase()));
    return filtered.length ? filtered.map(c => {
      const last = c.messages.filter(m => m.role !== 'system').at(-1);
      return `<button class="conversation-item ${c.id===state.selected?'active':''}" data-conversation="${c.id}" aria-pressed="${c.id===state.selected}">${avatar(c.name,c.color)}<div class="conversation-copy"><div class="row"><strong>${c.name}</strong><time>${c.time}</time></div><p>${esc(last?.text || c.subject)}</p><div class="row">${convStatus(c)}<span class="small muted">${c.subject}</span>${c.status==='queued'?'<span class="unread" aria-label="待接待"></span>':''}</div></div></button>`;
    }).join('') : `<div class="empty">${icon('search')}<p>没有匹配的会话</p></div>`;
  }
  function messages(c, client = false) {
    return `<div class="day-divider">今天 · ${client?'您的专属服务':'会话记录'}</div>` + c.messages.filter(m=> !client || m.role !== 'note').map(m => {
      if(m.role==='system') return `<div class="system-message"><span>${esc(m.text)}</span></div>`;
      const outgoing = client ? m.role==='customer' : m.role==='staff' || m.role==='note';
      const name = m.role==='customer' ? (client?'我':c.name) : m.role==='bot'?'Minihelp 助手':m.role==='note'?'周小雨 · 内部备注':'周小雨';
      const av = m.role==='bot' ? `<span class="avatar small green">${icon('spark')}</span>` : avatar(m.role==='customer'?c.name:'周',m.role==='customer'?c.color:'green',true);
      return `<article class="message ${outgoing?'outgoing':''} ${m.role==='bot'?'bot':''}">${av}<div class="message-body"><div class="message-label"><b>${name}</b><time>${esc(m.time)}</time></div><div class="bubble" ${m.role==='note'?'style="background:var(--amber-soft)"':''}>${esc(m.text).replace(/\n/g,'<br>')}${m.source?`<button class="citation-link" data-doc="${m.source}">${icon('book')}${esc(docs.find(d=>d.id===m.source)?.title)} ${icon('chevron')}</button>`:''}</div>${m.role==='note'?'<div class="message-note">仅团队可见</div>':m.role==='bot'&&!client?'<div class="message-note">AI 回复 · 引用已发布知识</div>':''}${client&&m.role==='bot'?`<div class="client-feedback"><button data-feedback="${c.id}:${c.messages.indexOf(m)}:up" class="${m.feedback==='up'?'chosen':''}" ${m.feedback?'disabled':''}>${m.feedback==='up'?'已反馈有帮助':'有帮助'}</button><button data-feedback="${c.id}:${c.messages.indexOf(m)}:down" class="${m.feedback==='down'?'chosen':''}" ${m.feedback?'disabled':''}>${m.feedback==='down'?'已反馈未解决':'未解决'}</button></div>`:''}</div></article>`;
    }).join('');
  }
  function orderContent(c) {
    return `<div class="order-tile"><div class="row"><div class="image-placeholder">商品图待补</div><div><strong>${esc(c.product)}</strong><p>数量 1 · ¥ ${c.amount}</p></div></div><div class="detail-row"><span>订单状态</span>${servicePanels.orderStatus(c)}</div><div class="detail-row"><span>订单编号</span><span class="mono">${c.order.slice(-10)}</span></div><button class="btn" data-action="order" data-id="${c.id}">查看订单详情 ${icon('arrow')}</button></div>`;
  }
  function details(c) {
    const related = tickets.filter(t=>t.conv===c.id);
    return `<div class="detail-head"><span>客户资料</span><span class="muted">当前会话</span></div><section class="detail-section"><div class="detail-profile">${avatar(c.name,c.color)}<div><b>${c.name}</b><p>Web 访客 · 演示客户</p></div></div><div class="detail-row"><span>当前接待</span><span>${c.status==='human'?'周小雨（我）':c.status==='queued'?'等待分配':'Minihelp 助手'}</span></div><div class="detail-row"><span>最近到访</span><span>今天 ${c.time}</span></div><div class="detail-tags">${c.tags.map(t=>pill(t,'neutral')).join('')}</div></section><section class="detail-section"><h3>关联订单</h3>${orderContent(c)}</section><section class="detail-section"><div class="between"><h3>相关工单</h3><button class="text-button" data-action="ticket-new" data-id="${c.id}">${icon('plus')}新建</button></div>${related.length?related.map(t=>`<div class="record"><span class="dot"></span><div><button class="table-actions" data-ticket="${t.id}">${esc(t.title)}</button><small>${t.id} · ${t.status==='resolved'?'已解决':t.status==='working'?'处理中':'待处理'}</small></div></div>`).join(''):'<p class="small muted">暂时没有关联工单</p>'}</section><div class="notice" style="font-size:10px">接管后，AI 将暂停自动回复。你仍可使用 AI 辅助起草。</div>`;
  }
  function workbench() {
    const c = current();
    const canSend = c.status==='human'||state.mode==='note';
    return shell(`<div class="desk"><section class="queue" aria-label="会话列表"><div class="queue-top"><div class="queue-title between"><h2>会话</h2><span class="small muted">${conversations.length} 条</span></div><label class="search">${icon('search')}<input id="conversation-search" aria-label="搜索会话" placeholder="搜索客户或订单" value="${esc(state.search)}"><span class="key">⌘K</span></label><div class="queue-tabs" role="group" aria-label="会话筛选">${[['all','全部',conversations.length],['waiting','待接待',conversations.filter(c=>c.status==='queued').length],['mine','我的',conversations.filter(c=>c.status==='human').length]].map(([id,label,n])=>`<button data-queue="${id}" class="${state.queue===id?'active':''}" aria-pressed="${state.queue===id}">${label}<b>${n}</b></button>`).join('')}</div></div><div class="queue-sub"><span>最近活跃</span><span>Web 渠道</span></div><div class="conversation-list" id="conversation-list">${queueList()}</div><div class="queue-footer">${icon('shield')} 客户消息与团队备注分开显示</div></section>
      <section class="chat-area" aria-label="客户会话"><header class="chat-header">${avatar(c.name,c.color)}<div><h2>${c.name}</h2><div class="chat-meta"><span class="dot ${c.status==='queued'?'amber':''}"></span>${c.status==='queued'?'等待人工接待':c.status==='human'?'由你接待中':'AI 自动接待'}<span>·</span>Web 咨询</div></div><button class="btn ${c.status!=='human'?'primary':''}" data-action="${c.status!=='human'?'takeover':'finish'}">${icon(c.status!=='human'?'headset':'check')}${c.status!=='human'?'接管会话':'结束接待'}</button><button class="icon-btn" data-action="customer-details" aria-label="查看客户资料">${icon('info')}</button></header>
      <div class="chat-messages" id="staff-messages">${messages(c)}</div><div class="summary-strip">${icon('spark')}<div><b>接待提示</b><p>${c.id===1?'客户希望确认拆封包装是否影响退货，建议先核实商品与配件状态。':'可结合客户消息与订单信息继续跟进。涉及业务操作时，请创建工单。'}</p></div></div>
      <div class="composer"><div class="composer-box"><div class="composer-mode"><button data-mode="reply" class="${state.mode==='reply'?'active':''}">回复客户</button><button data-mode="note" class="${state.mode==='note'?'active':''}">内部备注</button></div><textarea id="staff-draft" aria-label="${state.mode==='note'?'内部备注':'回复内容'}" placeholder="${canSend?(state.mode==='note'?'添加仅团队可见的记录…':'写下你的回复…'):'接管会话后即可回复客户…'}" maxlength="2000">${esc(state.drafts[`${c.id}-${state.mode}`]||'')}</textarea><div class="composer-foot"><button class="text-button" data-action="ai-draft">${icon('spark')} AI 辅助</button><button class="icon-btn" data-action="ticket-new" data-id="${c.id}" aria-label="新建工单">${icon('ticket')}</button><span class="hint">Enter 发送 / Shift + Enter 换行</span><button class="btn primary" data-action="staff-send" ${canSend?'':'disabled'}>${state.mode==='note'?'保存备注':canSend?'发送':'请先接管'} ${icon('send')}</button></div></div></div></section><aside class="details">${details(c)}</aside></div>`, '会话工作台');
  }
  function stat(label, number, suffix, foot) { return `<div class="stat"><div class="stat-label">${label}</div><div class="stat-number">${number}<span>${suffix}</span></div><div class="stat-foot">${foot}</div></div>`; }
  function knowledgeRows() {
    const filtered = docs.filter(d=>(state.docFilter==='all'||d.status===state.docFilter)&&`${d.title}${d.category}`.includes(state.docSearch));
    return filtered.length ? filtered.map(d=>`<tr><td><div class="row"><div class="doc-icon">${icon('file')}</div><div class="table-title">${esc(d.title)}<span class="table-sub">${esc(d.category)} · ${d.version}</span></div></div></td><td>${esc(d.scope)}</td><td>${docStatus(d)}</td><td><span class="muted">${d.date}</span></td><td><button class="table-actions" data-doc="${d.id}">${d.status==='published'?'查看':d.status==='review'?'审核':'编辑'}</button></td></tr>`).join('') : '<tr><td colspan="5"><div class="empty">没有匹配的知识</div></td></tr>';
  }
  function knowledge() {
    return shell(`<div class="page"><div class="page-title between"><div><div class="eyebrow" style="margin-bottom:6px">KNOWLEDGE BASE</div><h1>让每一次回答，有据可依。</h1><p>管理店铺知识，审核内容，再发布给 AI 助手使用。</p></div><button class="btn primary" data-action="doc-new">${icon('plus')}添加知识</button></div><div class="stat-strip">${stat('知识总数',docs.length,'篇','当前店铺知识')}${stat('已发布',docs.filter(d=>d.status==='published').length,'篇','可作为回复依据')}${stat('待审核',docs.filter(d=>d.status==='review').length,'篇','等待内容确认')}${stat('草稿',docs.filter(d=>d.status==='draft').length,'篇','尚未对助手生效')}</div><div class="content-grid"><section class="panel"><div class="panel-head"><h2>知识内容</h2><span class="small muted">喵喵优选 · 店铺范围</span></div><div class="panel-toolbar">${[['all','全部'],['published','已发布'],['review','待审核'],['draft','草稿']].map(([id,label])=>`<button class="filter-chip ${state.docFilter===id?'active':''}" data-doc-filter="${id}">${label}</button>`).join('')}<label class="search">${icon('search')}<input id="doc-search" placeholder="搜索知识" aria-label="搜索知识" value="${esc(state.docSearch)}"></label></div><div class="table-wrap"><table><thead><tr><th>名称</th><th>适用范围</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody id="knowledge-rows">${knowledgeRows()}</tbody></table></div><div class="panel-footer"><span>${docs.length} 篇演示知识 · 状态可操作</span><span>每页 20 条</span></div></section><aside><section class="aside-panel accent"><div class="eyebrow">发布前，先试一试</div><h3>回答测试</h3><p>选一个真实场景，检查答案和引用是否符合店铺规则。</p><button class="btn" data-action="knowledge-test">${icon('spark')}测试一条问题</button></section><section class="aside-panel"><h3>知识如何生效</h3><div class="step-line"><span class="step-number">1</span>整理内容，保存草稿</div><div class="step-line"><span class="step-number">2</span>核对适用范围与版本</div><div class="step-line"><span class="step-number">3</span>审核后发布给助手</div><p>本预览演示编辑和发布状态。解析、索引构建与检索将由正式后端完成。</p></section></aside></div></div>`, '知识库');
  }
  function ticketRows() {
    const list = tickets.filter(t=>(state.ticketFilter==='all'||t.status===state.ticketFilter)&&`${t.id}${t.title}${t.customer}`.includes(state.ticketSearch));
    return list.length ? list.map(t=>`<tr><td><button class="table-actions table-title" data-ticket="${t.id}">${esc(t.title)}</button><span class="table-sub mono">${t.id} · ${esc(t.type)}</span></td><td>${esc(t.customer)}</td><td>${ticketStatus(t)}</td><td>${t.priority==='优先'?'<span class="priority"></span>':''}${t.priority}</td><td class="muted">${t.time}</td><td><button class="table-actions" data-ticket="${t.id}">跟进 ${icon('chevron')}</button></td></tr>`).join('') : '<tr><td colspan="6"><div class="empty">当前没有匹配工单</div></td></tr>';
  }
  function ticketPage() {
    return shell(`<div class="page"><div class="page-title between"><div><div class="eyebrow" style="margin-bottom:6px">SERVICE TICKETS</div><h1>把问题跟进到解决。</h1><p>让每一笔售后有负责人、有进展、有结果。</p></div><button class="btn primary" data-action="ticket-new" data-id="${state.selected}">${icon('plus')}新建工单</button></div><div class="stat-strip">${stat('全部工单',tickets.length,'笔','演示业务记录')}${stat('待处理',tickets.filter(t=>t.status==='open').length,'笔','需要客服领取')}${stat('处理中',tickets.filter(t=>t.status==='working').length,'笔','保持进展同步')}${stat('已解决',tickets.filter(t=>t.status==='resolved').length,'笔','可查看处理记录')}</div><section class="panel"><div class="panel-head"><h2>工单列表</h2><span class="small muted">会话与订单关联</span></div><div class="panel-toolbar"><div class="ticket-filter">${[['all','全部工单'],['open','待处理'],['working','处理中'],['resolved','已解决']].map(([id,label])=>`<button class="filter-chip ${state.ticketFilter===id?'active':''}" data-ticket-filter="${id}">${label}</button>`).join('')}</div><label class="search">${icon('search')}<input id="ticket-search" aria-label="搜索工单" placeholder="编号、标题或客户" value="${esc(state.ticketSearch)}"></label></div><div class="table-wrap"><table><thead><tr><th>工单</th><th>客户</th><th>状态</th><th>优先级</th><th>创建时间</th><th>操作</th></tr></thead><tbody class="ticket-rows" id="ticket-rows">${ticketRows()}</tbody></table></div><div class="panel-footer"><span>共 ${tickets.length} 笔工单</span><span>本页状态仅保留在当前预览中</span></div></section><div class="notice" style="margin-top:22px">${icon('info')} 退货工单负责记录申请和跟进。创建工单并不表示已退款，实际支付结果将在正式业务链路中核验。</div></div>`, '工单中心');
  }
  function client() {
    const c = conversations[0];
    const status = c.status==='human'?'周小雨正在为您服务':c.status==='queued'?'已转人工，等待客服接待':'Minihelp 助手在线';
    return `<main class="client-shell"><header class="store-header"><div class="store-brand"><img src="assets/minihelp-cat.svg" alt="">喵喵优选</div><nav class="store-nav" aria-label="店铺服务"><button class="active" data-action="client-focus">在线咨询</button><button data-action="order" data-id="1">我的订单</button><button data-action="client-tickets">服务记录</button></nav></header><div class="client-grid"><section class="client-intro"><div class="eyebrow">HERE TO HELP YOU</div><h1>关于小家伙的一切，<br>我们都认真对待。</h1><p>从选购建议到订单售后，<br>有问题，就来聊一聊。</p><div class="help-links"><button class="help-link" data-action="order" data-id="1">${icon('box')}查询我的订单</button><button class="help-link" data-doc="1">${icon('back')}了解退换货</button><button class="help-link" data-client-question="我想了解商品的使用方法">${icon('book')}商品使用帮助</button><button class="help-link" data-action="handoff">${icon('headset')}联系人工客服</button></div><div class="client-note">${icon('shield')}当前为演示会话，不涉及真实订单</div></section><section class="client-window" aria-label="客户咨询窗口"><header class="chat-header"><span class="avatar green">${icon(c.status==='human'?'headset':'spark')}</span><div><h2>喵喵优选 · 在线客服</h2><div class="chat-meta"><span class="dot ${c.status==='queued'?'amber':''}"></span>${status}</div></div><button class="icon-btn" data-action="client-service-info" aria-label="服务说明">${icon('info')}</button></header><div class="chat-messages" id="client-messages">${messages(c,true)}</div><div class="client-quick"><button data-action="order" data-id="1">查询订单</button><button data-action="client-ticket-new">申请退货</button><button data-action="handoff">转人工</button></div><div class="composer"><div class="composer-box"><textarea id="client-draft" aria-label="咨询内容" placeholder="说说你遇到的问题…" maxlength="2000">${esc(state.clientDraft)}</textarea><div class="composer-foot"><span class="small muted" style="padding-left:4px">演示聊天 · 刷新后重置</span><span class="spacer"></span><button class="btn primary" data-action="client-send">发送 ${icon('send')}</button></div></div></div><div class="powered">服务支持 <b>Minihelp</b> · 温暖，也高效</div></section></div></main>`;
  }
  function render() {
    document.querySelectorAll('[data-surface]').forEach(button=>{button.classList.toggle('active',button.dataset.surface===state.surface);button.setAttribute('aria-pressed',String(button.dataset.surface===state.surface));});
    $('#app').innerHTML = state.surface==='client' ? client() : dataPanels.hasPage(state.page)?shell(dataPanels.renderPage(state.page),dataPanels.title(state.page)):servicePanels.hasPage(state.page)?shell(servicePanels.renderPage(state.page),servicePanels.title(state.page)):panels.hasPage(state.page)?shell(panels.renderPage(state.page),panels.title(state.page)):state.page==='tickets'?ticketPage():workbench();
    if(state.surface==='admin'&&dataPanels.hasPage(state.page)) {
      const badge=$('.top-tools .pill');if(badge)badge.textContent=dataPanels.label();
      const context=$('.top-tools .small');if(context)context.textContent=['quality','observability','models'].includes(state.page)?'报告与评估状态':state.page==='topics'?'主题归类状态':'库存与运行状态';
      const marker=$('.demo-label');if(marker)marker.textContent=dataPanels.label();
      const reviewCount=$('[data-page="review"] .nav-count');if(reviewCount){const value=dataPanels.pendingReviews();reviewCount.textContent=value;reviewCount.hidden=!value;}
    } else {const marker=$('.demo-label');if(marker)marker.textContent='演示数据';}
    const route = '#/' + (state.surface==='client'?'client':state.page);
    if(location.hash!==route) history.pushState(null,'',route);
  }
  function scrollMessages() { document.querySelectorAll('.chat-messages').forEach(el=>{el.scrollTop=el.scrollHeight;}); }
  let toastTimer;
  function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('show'),3300); }
  function modal(title, body, footer = '<button class="btn" data-action="modal-close">知道了</button>') {
    $('#modal').classList.remove('workflow-dialog','report-dialog','classification-dialog','knowledge-dialog');delete $('#modal').dataset.workflowKey;delete $('#modal').dataset.knowledgeKey;
    $('#modal-content').innerHTML=`<div class="modal-head"><h2 id="modal-title">${esc(title)}</h2><button class="icon-btn" data-action="modal-close" aria-label="关闭对话框">${icon('close')}</button></div><div class="modal-body">${body}</div><div class="modal-foot">${footer}</div>`;
    if(!$('#modal').open) $('#modal').showModal();
  }
  function go(page) {
    if(page==='client') {state.surface='client';$('#modal').close();render();}
    else if(['workbench','tickets'].includes(page)||panels.hasPage(page)||servicePanels.hasPage(page)) {state.page=page;state.surface=servicePanels.hasPage(page)?servicePanels.surface(page):panels.hasPage(page)?'admin':'workbench';$('#modal').close();render();}
    else pagePlan(page);
  }
  function restoreRoute() {
    const page=location.hash.replace(/^#\//,'');
    if(page==='client'||['workbench','tickets'].includes(page)||panels.hasPage(page)||servicePanels.hasPage(page)) go(page);
    else {state.surface='workbench';state.page='workbench';history.replaceState(null,'','#/workbench');render();}
  }
  const pagePlans = {
    client:{name:'客户咨询页',icon:'chat',stage:'本轮可体验',text:'独立咨询页 / 嵌入式聊天窗，提供消息、引用、订单查询、转人工、售后申请和服务记录。'},
    workbench:{name:'客服工作台',icon:'headset',stage:'本轮可体验',text:'待接待 / 我的 / 全部队列，聊天与内部备注，人工接管，AI 辅助草稿，客户和订单上下文，创建工单。'},
    tickets:{name:'工单中心',icon:'ticket',stage:'本轮可体验',text:'统一承接退款、退换货、补发、物流核查。列表 → 详情 → 领取 → 处理 → 解决，完整保留操作记录。'},
    knowledge:{name:'知识库',icon:'book',stage:'本轮可体验',text:'草稿、审核、发布与测试。正式版补全文档上传、解析进度、索引版本、发布回滚和失败重试。'},
    customers:{name:'客户资料',icon:'users',stage:'下一轮规划',text:'客户列表与检索、资料详情、标签、联系偏好、历史会话与工单。合并客户前提供预览，敏感字段按角色展示。'},
    products:{name:'商品与订单',icon:'box',stage:'下一轮规划',text:'商品列表、SKU 与规格、订单详情、物流轨迹、售后资格与关联工单。展示同步状态，失败可重试。'},
    reports:{name:'服务报表',icon:'chart',stage:'下一轮规划',text:'接待量、首次响应时间、排队时长、解决率、转人工原因和知识命中。每项指标注明统计口径和时间范围。'},
    settings:{name:'设置与接入',icon:'settings',stage:'下一轮规划',text:'成员与角色、工作时间、渠道接入、模型配置、工具权限、通知、审计记录。配置保存前校验，敏感操作明确确认。'}
  };
  function pagePlan(page) {
    const items=page&&pagePlans[page] ? [[page,pagePlans[page]]] : Object.entries(pagePlans);
    modal(page&&pagePlans[page]?`${pagePlans[page].name} · 页面规划`:'Minihelp · 页面规划',`<div class="notice">这里说明页面结构与接入范围。页面会区分展示样例、实时只读和原型演示；展示样例刷新后重置。</div><div class="page-map">${items.map(([id,p])=>`<section class="map-row"><h3>${icon(p.icon)}${p.name}<span class="map-tag">${pill(p.stage,p.stage==='本轮可体验'?'':'neutral')}</span></h3><p>${p.text}</p>${p.stage==='本轮可体验'?`<button class="table-actions" data-open-view="${id}">打开页面 ${icon('arrow')}</button>`:''}</section>`).join('')}</div>`);
  }
  function showOrder(id) {
    servicePanels.showOrder(id);
  }
  function newTicket(id, fromClient = false) {
    const c=conversations.find(c=>c.id===id)||conversations[0];
    const existing=fromClient&&tickets.find(t=>t.conv===1&&t.type==='退货'&&t.status!=='resolved');
    if(existing) { showTicket(existing.id,true); return; }
    modal(fromClient?'确认退货申请':'新建工单',`<div class="notice ${fromClient?'amber':''}">${fromClient?'提交后将生成售后工单，由客服确认条件和寄回方式。此操作不会直接退款。':'工单将关联当前客户、会话和订单，便于后续追踪。'}</div><form id="ticket-form" data-conv="${c.id}" data-client="${fromClient}"><div class="row" style="margin-bottom:20px">${avatar(c.name,c.color)}<div><h3>${c.name}</h3><p class="muted mono">${c.order}</p></div></div><label class="field">工单类型<select name="type">${['退货','换货','补发','物流','咨询'].map(t=>`<option>${t}</option>`).join('')}</select></label><label class="field">问题标题<input name="title" required maxlength="70" value="${esc(c.id===1?'猫砂盆退货申请':c.subject)}"></label><label class="field">情况说明<textarea name="desc" required maxlength="1500" placeholder="描述商品情况和需要协助的事项">${c.id===1?'商品未使用，外包装已拆，想确认是否可以退货。':''}</textarea></label><p class="field-hint">所有内容均为演示，不会提交给真实店铺。</p></form>`, `<button class="btn" data-action="modal-close">取消</button><button class="btn primary" type="submit" form="ticket-form">${fromClient?'确认提交申请':'创建工单'} ${icon('arrow')}</button>`);
  }
  function showTicket(id, fromClient = state.surface==='client') {
    const t=tickets.find(t=>t.id===id); if(!t)return;
    const c=conversations.find(c=>c.id===t.conv);
    modal(t.title,`<div class="between" style="margin-bottom:20px"><span class="mono muted">${t.id}</span>${ticketStatus(t)}</div><div class="detail-row"><span>关联客户</span><span>${t.customer}</span></div><div class="detail-row"><span>关联订单</span><span class="mono">${c.order}</span></div><div class="detail-row"><span>负责客服</span><span>${t.status==='open'?'等待领取':'周小雨'}</span></div><div class="preview-text" style="margin-top:16px">${esc(t.desc).replace(/\n/g,'<br>')}</div><div class="timeline">${t.history.map(h=>`<div class="timeline-item">${esc(h)}<small>演示处理记录</small></div>`).join('')}</div>${!fromClient&&t.status==='working'?'<label class="field">处理结果<textarea id="resolution" placeholder="记录处理结果，方便客户和团队追踪" maxlength="1000"></textarea></label><p class="field-hint">结果会显示在客户的服务记录中，请勿填写内部信息。</p>':''}${fromClient?'<p class="muted">您可在服务记录中查看进展，实际退款以支付渠道结果为准。</p>':''}`, `<button class="btn" data-action="modal-close">关闭</button>${!fromClient&&t.status!=='resolved'?`<button class="btn primary" data-ticket-advance="${t.id}">${t.status==='open'?'领取工单':'标记已解决'} ${icon('check')}</button>`:''}`);
  }
  function showDoc(id) {
    const d=docs.find(d=>d.id===id);if(!d)return;
    const editable=state.surface==='admin'&&d.status!=='published';
    modal(d.title,`<div class="between" style="margin-bottom:18px">${docStatus(d)}<span class="small muted">${esc(d.category)} · ${d.version} · ${esc(d.scope)}</span></div>${editable?`<form id="doc-edit-form" data-doc-id="${d.id}"><label class="field">知识标题<input name="title" value="${esc(d.title)}" required maxlength="80"></label><label class="field">内容<textarea name="body" required maxlength="6000" style="min-height:180px">${esc(d.text)}</textarea></label></form>`:`<div class="preview-text">${esc(d.text).replace(/\n/g,'<br>')}</div>`}<p class="field-hint">${editable?'检查内容准确性后保存，再提交审核。':'演示政策 · 用于页面和引用样式预览，不代表实际店铺承诺。'}</p>`, `<button class="btn" data-action="modal-close">关闭</button>${editable?`<button class="btn" type="submit" form="doc-edit-form">保存修改</button><button class="btn primary" data-doc-promote="${d.id}">${d.status==='draft'?'提交审核':'审核并发布'} ${icon('check')}</button>`:''}`);
  }
  function newDoc() {
    modal('添加知识',`<div class="notice">先用一段文本体验草稿与审核流程。正式版本将支持文档上传、解析和索引状态。</div><form id="doc-form"><label class="field">知识标题<input name="title" required maxlength="80" placeholder="例如：宠物包清洁与保养"></label><label class="field">分类<select name="category"><option>商品说明</option><option>售后政策</option><option>物流服务</option><option>常见问题</option></select></label><label class="field">知识正文<textarea name="body" required maxlength="6000" placeholder="在这里填写完整、可核对的说明…"></textarea></label></form>`, '<button class="btn" data-action="modal-close">取消</button><button class="btn primary" type="submit" form="doc-form">保存为草稿</button>');
  }
  function knowledgeTest() {
    modal('回答测试',`<div class="notice">这是预设回答展示，用来确认测试页结构与引用样式。正式版将调用检索与模型服务。</div><form id="test-form"><label class="field">测试问题<input name="question" required maxlength="500" value="包装拆开了，还能申请退货吗？"></label></form><div id="test-result"></div>`, '<button class="btn" data-action="modal-close">关闭</button><button class="btn primary" type="submit" form="test-form">预览回答</button>');
  }
  function sendStaff() {
    const c=current(), text=$('#staff-draft')?.value.trim();
    if(!text) {toast('先输入回复内容');return;}
    if(state.mode==='reply'&&c.status!=='human') {toast('请先接管会话');return;}
    c.messages.push({role:state.mode==='note'?'note':'staff',text,time:now()});c.time=now();
    state.drafts[`${c.id}-${state.mode}`]='';render();scrollMessages();$('#staff-draft')?.focus();
    toast(state.mode==='note'?'已保存内部备注，仅团队可见':c.id===1?'已回复，可切换客户咨询页查看':'演示回复已发送');
  }
  function sendClient(preset) {
    const text=typeof preset==='string'?preset:$('#client-draft')?.value.trim(); if(!text) {toast('先输入咨询内容');return;}
    const c=conversations[0]; c.messages.push({role:'customer',text,time:now()});c.time=now();state.clientDraft='';
    if(c.status==='auto') {
      const source=/退|包装|售后/.test(text)?1:/快递|发货|物流/.test(text)?2:null;
      c.messages.push({role:'bot',text:source===1?'可以先提交退货申请。未使用、配件齐全的商品通常可申请；拆封包装的具体状态需要客服确认。':source===2?'常规现货商品付款后 48 小时内发出。物流长时间未更新时，我们可以转人工协助核查。':'收到您的咨询。请补充商品型号或订单信息，也可以选择转人工进一步沟通。',time:now(),source});
    }
    render();scrollMessages();$('#client-draft')?.focus();
    if(c.status!=='auto')toast(c.status==='queued'?'消息已加入待接待会话':'消息已同步到客服工作台');
  }
  function handoff() {
    const c=conversations[0];
    if(c.status==='human') {toast('周小雨已接管，可在客服工作台继续回复');return;}
    if(c.status==='queued') {toast('您已在待接待队列中，可切换工作台接管');return;}
    c.status='queued'; c.messages.push({role:'system',text:'客户申请人工服务 · 等待客服接待',time:now()});render();scrollMessages();toast('已转入客服工作台的待接待队列');
  }
  function readDocEdit(d) {
    const form=$('#doc-edit-form');if(!form)return true;
    if(!form.reportValidity())return false;
    const data=new FormData(form); const title=String(data.get('title')).trim(),body=String(data.get('body')).trim();
    if(!title||!body) {toast('标题和内容不能为空');return false;}
    d.title=title;d.text=body;return true;
  }
  const actions = {
    'modal-close':()=>$('#modal').close(),
    'nav-menu':()=>{const menu=state.surface==='admin'?['overview','knowledge','review','quality','observability','topics','models','jobs','settings','migration','workbench']:['workbench','tickets','customers','products','overview','settings'];modal('页面菜单',`<nav class="mobile-menu-list" aria-label="页面入口">${menu.map(page=>`<button data-page="${page}" class="${state.page===page?'active':''}">${icon(pagePlans[page]?.icon||'file')}${esc(pagePlans[page]?.name||page)}</button>`).join('')}</nav>`);},
    workspace:()=>modal('当前工作区','<div class="row"><span class="avatar green">喵</span><div><h3>喵喵优选</h3><p class="muted">独立店铺 · Web 咨询渠道</p></div></div><p style="margin-top:20px">首版以单组织、单工作区为产品边界。成员管理和渠道接入将在设置页中配置。</p>'),
    profile:()=>modal('周小雨 · 演示账号','<div class="notice">这是交互原型，没有登录会话和真实权限控制。</div><p>规划角色：管理员、主管、客服。生产版根据角色区分知识发布、成员管理、客服接管和工单处理权限。</p>'),
    guide:()=>modal('这样体验本轮原型','<div class="page-map"><div class="map-row"><h3>01 · 接待客户</h3><p>在工作台接管林女士的会话，输入回复，然后切换到客户咨询页查看。</p></div><div class="map-row"><h3>02 · 跟进售后</h3><p>在客户页提交退货申请，再到工单中心领取和记录处理结果。</p></div><div class="map-row"><h3>03 · 更新知识</h3><p>在知识库添加草稿、提交审核、发布，查看状态和数量变化。</p></div></div><p class="field-hint">右上角色视角用于预览；正式版会按登录身份展示对应入口。刷新页面会重置数据。</p>'),
    takeover:()=>{const c=current();c.status='human';c.messages.push({role:'system',text:'周小雨已接管会话 · AI 自动回复已暂停',time:now()});render();scrollMessages();toast('已接管，可回复客户或使用 AI 草稿');},
    finish:()=>modal('结束本次人工接待','<p>结束后，后续消息将恢复由 AI 助手接待。已创建的工单继续保留，不会自动标记为解决。</p>','<button class="btn" data-action="modal-close">继续接待</button><button class="btn primary" data-action="finish-confirm">确认结束</button>'),
    'finish-confirm':()=>{const c=current();c.status='auto';c.messages.push({role:'system',text:'本次人工接待结束 · 已恢复 AI 接待',time:now()});$('#modal').close();render();scrollMessages();toast('会话已恢复 AI 接待，工单继续保留');},
    'customer-details':()=>{servicePanels.onClick({dataset:{serviceViewCustomer:String(state.selected)}});},
    'ai-draft':()=>{const c=current();if(state.mode==='note'){toast('请切换到回复客户后使用 AI 辅助');return;}const draft=c.id===1?'您好，我来帮您确认。若商品未使用且配件齐全，我们可以先为您登记退货申请。请保留现有包装，并说明包装是否有破损，我会进一步核实寄回要求。':'您好，我已经收到您的问题，将结合订单信息为您核实具体情况，请稍候。';state.drafts[`${c.id}-reply`]=draft;$('#staff-draft').value=draft;$('#staff-draft').focus();toast('已填入预设辅助草稿，请确认后发送');},
    'staff-send':sendStaff,
    'ticket-new':el=>newTicket(Number(el.dataset.id)||state.selected),
    order:el=>showOrder(Number(el.dataset.id)||state.selected),
    'doc-new':newDoc,
    'knowledge-test':knowledgeTest,
    'client-send':()=>sendClient(),
    'client-ticket-new':()=>newTicket(1,true),
    handoff,
    'client-focus':()=>$('#client-draft')?.focus(),
    'client-tickets':()=>{const list=tickets.filter(t=>t.conv===1);modal('我的服务记录',list.length?list.map(t=>`<div class="map-row" style="margin-bottom:12px"><div class="between"><h3>${esc(t.title)}</h3>${ticketStatus(t)}</div><p class="mono muted">${t.id}</p><button class="table-actions" data-ticket="${t.id}">查看进展 ${icon('arrow')}</button></div>`).join(''):'<div class="empty">暂时没有服务记录<br>提交售后申请后，可以在这里跟进。</div>');},
    'client-service-info':()=>modal('服务说明','<p>AI 助手可协助解答常见问题。需要进一步核查订单、确认售后条件或人工帮助时，可以选择转人工。</p><div class="notice" style="margin-top:18px">本页面使用演示客户与预设回复。所有操作只在当前预览中生效。</div>')
  };
  document.addEventListener('click', event=>{
    const el=event.target.closest('button');if(!el||el.disabled)return;
    if(dataPanels.onClick(el)||servicePanels.onClick(el)||panels.onClick(el))return;
    if(el.dataset.feedback){const [cid,index,rating]=el.dataset.feedback.split(':');const c=conversations.find(c=>c.id===Number(cid)),m=c?.messages[Number(index)];if(!m||m.feedback)return;m.feedback=rating;if(rating==='down'){const question=c.messages.slice(0,Number(index)).filter(m=>m.role==='customer').at(-1)?.text||'客户反馈未解决';panels.addFeedback(question);}render();toast(rating==='down'?'已反馈，可在管理后台的知识缺口查看':'感谢反馈（演示）');return;}
    if(el.dataset.action) {actions[el.dataset.action]?.(el);return;}
    if(el.dataset.surface) {state.surface=el.dataset.surface;state.page=state.surface==='admin'?'overview':'workbench';render();return;}
    if(el.dataset.page) {go(el.dataset.page);return;}
    if(el.dataset.openView) {const page=el.dataset.openView;if(page==='client'){state.surface='client';$('#modal').close();render();}else go(page);return;}
    if(el.dataset.conversation) {state.selected=Number(el.dataset.conversation);state.mode='reply';render();return;}
    if(el.dataset.queue) {state.queue=el.dataset.queue;render();return;}
    if(el.dataset.mode) {state.mode=el.dataset.mode;render();$('#staff-draft')?.focus();return;}
    if(el.dataset.docFilter) {state.docFilter=el.dataset.docFilter;render();return;}
    if(el.dataset.ticketFilter) {state.ticketFilter=el.dataset.ticketFilter;render();return;}
    if(el.dataset.doc) {showDoc(Number(el.dataset.doc));return;}
    if(el.dataset.ticket) {showTicket(el.dataset.ticket);return;}
    if(el.dataset.clientQuestion) {sendClient(el.dataset.clientQuestion);return;}
    if(el.dataset.ticketAdvance) {
      const t=tickets.find(t=>t.id===el.dataset.ticketAdvance);if(!t)return;
      if(t.status==='open'){t.status='working';t.history.push('周小雨已领取工单');}
      else if(t.status==='working'){const result=$('#resolution')?.value.trim();if(!result){toast('请填写处理结果');$('#resolution')?.focus();return;}t.status='resolved';t.history.push(`处理结果：${result}`);}
      render();showTicket(t.id,false);toast('工单状态已更新');return;
    }
    if(el.dataset.docPromote) {
      const d=docs.find(d=>d.id===Number(el.dataset.docPromote));if(!d||!readDocEdit(d))return;
      d.status=d.status==='draft'?'review':'published';d.date='09-22 '+now();if(d.status==='published'){d.version='v1.0';panels.markPublished(d.id);}
      $('#modal').close();render();toast(d.status==='review'?'已提交审核':'已发布到演示知识库');return;
    }
    if(el.id==='plan-open')go('migration');
    if(el.id==='palette-open'){state.palette=(state.palette+1)%3;const id=['forest','white','paper'][state.palette],name=['森绿','纯白','暖纸'][state.palette];document.body.dataset.palette=id;el.setAttribute('aria-label',`切换配色，当前${name}`);toast(`配色方案 ${state.palette+1} / 3 · ${name}`);}
  });
  document.addEventListener('input', event=>{
    const el=event.target;
    dataPanels.onInput(el);
    panels.onInput(el);
    servicePanels.onInput(el);
    if(el.id==='staff-draft')state.drafts[`${state.selected}-${state.mode}`]=el.value;
    if(el.id==='client-draft')state.clientDraft=el.value;
    if(el.id==='conversation-search'){state.search=el.value;$('#conversation-list').innerHTML=queueList();}
    if(el.id==='doc-search'){state.docSearch=el.value;$('#knowledge-rows').innerHTML=knowledgeRows();}
    if(el.id==='ticket-search'){state.ticketSearch=el.value;$('#ticket-rows').innerHTML=ticketRows();}
  });
  document.addEventListener('keydown', event=>{
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){const field=$('#conversation-search')||$('#doc-search')||$('#ticket-search')||$('#customer-search')||$('#order-search')||$('#product-search');if(field){event.preventDefault();field.focus();}}
    if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&(event.target.id==='staff-draft'||event.target.id==='client-draft')){event.preventDefault();event.target.id==='staff-draft'?sendStaff():sendClient();}
  });
  document.addEventListener('submit', event=>{
    if(dataPanels.onSubmit(event)||servicePanels.onSubmit(event)||panels.onSubmit(event))return;
    const form=event.target;if(!['ticket-form','doc-form','doc-edit-form','test-form'].includes(form.id))return;
    event.preventDefault();const data=new FormData(form);
    if(form.id==='ticket-form') {
      const c=conversations.find(c=>c.id===Number(form.dataset.conv));const title=String(data.get('title')).trim(),desc=String(data.get('desc')).trim();if(!title||!desc){toast('请完整填写标题和情况说明');return;}
      const t={id:`TK-${++state.seq}`,customer:c.name,conv:c.id,title,type:String(data.get('type')),status:'open',priority:'普通',time:'09-22 '+now(),desc,history:['由'+(form.dataset.client==='true'?'客户申请':'客服会话')+'创建工单']};tickets.unshift(t);
      c.messages.push({role:'system',text:`已创建${t.type}工单 ${t.id} · 等待处理`,time:now()});$('#modal').close();render();scrollMessages();toast(`工单 ${t.id} 已创建，可在工单中心跟进`);
    }
    if(form.id==='doc-form') {
      const title=String(data.get('title')).trim(),body=String(data.get('body')).trim();if(!title||!body){toast('标题和内容不能为空');return;}
      docs.unshift({id:Math.max(...docs.map(d=>d.id))+1,title,category:String(data.get('category')),scope:'全部商品',status:'draft',version:'v0.1',date:'09-22 '+now(),text:body});state.docFilter='all';state.docSearch='';$('#modal').close();render();toast('草稿已保存，审核发布后才可使用');
    }
    if(form.id==='doc-edit-form') {const d=docs.find(d=>d.id===Number(form.dataset.docId));if(d&&readDocEdit(d)){d.date='09-22 '+now();$('#modal').close();render();toast('修改已保存');}}
    if(form.id==='test-form') {
      const question=String(data.get('question')).trim();if(!question){toast('请输入测试问题');return;}
      const d=/发货|快递|物流/.test(question)?docs.find(d=>d.id===2):/退|包装/.test(question)?docs.find(d=>d.id===1):null;
      $('#test-result').innerHTML=d?`<div class="preview-text"><span class="pill">预设示例</span><p style="margin-top:12px">${esc(d.text)}</p><button class="citation-link" data-doc="${d.id}">${icon('book')}${esc(d.title)} · ${d.version}</button></div>`:'<div class="notice amber">本轮仅准备了退换货与发货时效的回答示例。正式版会检索已发布知识，并展示真实引用和无结果状态。</div>';
    }
  });
  const panels = window.createMinihelpPanels({esc,icon,pill,stat,docs,tickets,conversations,modal,toast,render,go,knowledgeRows,state});
  const servicePanels = window.createMinihelpServicePanels({esc,icon,pill,avatar,docs,tickets,conversations,modal,toast,render,go,state});
  const dataPanels = window.createMinihelpDataPanels({esc,icon,pill,stat,modal,toast,render,go,state});
  document.addEventListener('change',event=>dataPanels.onChange(event.target));
  Object.assign(pagePlans,panels.pagePlans,servicePanels.pagePlans,dataPanels.pagePlans);
  window.addEventListener('popstate',restoreRoute);
  restoreRoute();
})();
