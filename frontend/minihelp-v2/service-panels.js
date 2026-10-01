/* V2 product flows. Shared illustrative records; no network or persisted settings. */
window.createMinihelpServicePanels = function createMinihelpServicePanels(h) {
  'use strict';
  const { esc, icon, pill, avatar, conversations, tickets, docs, state, modal, toast, render, go } =
    h;
  const $ = (selector) => document.querySelector(selector);
  const titles = { customers: '客户资料', products: '商品与订单', settings: '设置与权限' };
  const ui = {
    customer: 1,
    customerQuery: '',
    customerFilter: 'all',
    customerTab: 'summary',
    productTab: 'orders',
    orderQuery: '',
    orderFilter: 'all',
    productQuery: '',
    settingsTab: 'members',
    sync: 'idle',
  };
  const preferences = new Map();
  const members = [
    { id: 1, name: '周小雨', role: '管理员', status: 'active', self: true },
    { id: 2, name: '陈主管', role: '主管', status: 'active' },
    { id: 3, name: '小许', role: '客服', status: 'active' },
    { id: 4, name: '知识运营', role: '知识运营', status: 'active' },
  ];
  const rules = { start: '09:00', end: '18:00', mode: 'assist', offline: 'ticket' };
  const audit = [];
  const stamp = () =>
    new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const log = (action, detail) => audit.unshift({ time: stamp(), action, detail });
  const orderInfo = (c) => ({
    state: { 1: '已签收', 2: '运输异常', 3: '已签收', 4: '待发货', 5: '已签收', 6: '待发货' }[c.id],
    source: 'Web 演示订单',
  });
  const orderStatus = (c) =>
    pill(orderInfo(c).state, c.id === 2 ? 'amber' : [4, 6].includes(c.id) ? 'neutral' : '');
  const relatedTickets = (c) => tickets.filter((t) => t.conv === c.id);
  const activeTickets = (c) => relatedTickets(c).filter((t) => t.status !== 'resolved');
  const ticketStatus = (t) =>
    pill(
      { open: '待处理', working: '处理中', resolved: '已解决' }[t.status],
      t.status === 'open' ? 'amber' : t.status === 'working' ? 'blue' : '',
    );
  const match = (text, query) => text.toLowerCase().includes(query.trim().toLowerCase());
  const demo =
    '<div class="demo-strip"><span class="dot amber"></span>演示工作区 · 数据与修改仅在当前页面会话中保留，刷新后重置。</div>';
  const heading = (eyebrow, title, description, actions = '') =>
    `<div class="page-title between"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div><div class="page-actions">${actions}</div></div>${demo}`;
  const tabs = (key, values, selected) =>
    `<nav class="section-tabs" aria-label="${esc(titles[key] || key)}子页面">${values.map(([id, label]) => `<button data-service-tab="${key}:${id}" class="${selected === id ? 'active' : ''}" aria-pressed="${selected === id}">${label}</button>`).join('')}</nav>`;
  const empty = (message, reset) =>
    `<div class="empty"><p>${message}</p>${reset ? `<button class="btn" data-service-action="${reset}">清除筛选</button>` : ''}</div>`;
  const ticketCards = (c) =>
    relatedTickets(c).length
      ? relatedTickets(c)
          .map(
            (t) =>
              `<button class="relation-row" data-ticket="${t.id}"><span class="relation-icon">${icon('ticket')}</span><span><strong>${esc(t.title)}</strong><small>${t.id} · ${esc(t.type)}</small></span>${ticketStatus(t)}${icon('chevron')}</button>`,
          )
          .join('')
      : empty('暂时没有关联工单');

  function customerList() {
    const list = conversations.filter(
      (c) =>
        match(`${c.name} ${c.order} ${c.tags.join(' ')}`, ui.customerQuery) &&
        (ui.customerFilter === 'all' ||
          (ui.customerFilter === 'follow' && activeTickets(c).length) ||
          (ui.customerFilter === 'human' && c.status === 'human')),
    );
    return list.length
      ? list
          .map(
            (c) =>
              `<button class="customer-item ${c.id === ui.customer ? 'selected' : ''}" data-service-customer="${c.id}" aria-pressed="${c.id === ui.customer}">${avatar(c.name, c.color)}<span><strong>${esc(c.name)}</strong><small>${esc(c.subject)}</small></span>${activeTickets(c).length ? `<span class="pill amber">${activeTickets(c).length} 待跟进</span>` : icon('chevron')}</button>`,
          )
          .join('')
      : empty('没有符合条件的客户', 'reset-customers');
  }

  function customerDetail() {
    const c = conversations.find((c) => c.id === ui.customer);
    const notes = c.messages.filter((m) => m.role === 'note');
    let content;
    if (ui.customerTab === 'summary') {
      content = `<div class="customer-context"><section><div class="section-heading"><h3>服务上下文</h3><span>来自当前演示会话</span></div><dl class="property-grid"><div><dt>咨询渠道</dt><dd>网站咨询</dd></div><div><dt>当前接待</dt><dd>${c.status === 'human' ? '周小雨' : c.status === 'queued' ? '等待分配' : 'Minihelp 助手'}</dd></div><div><dt>联系偏好</dt><dd>${esc(preferences.get(c.id) || '优先站内回复')}</dd></div><div><dt>最近咨询</dt><dd>${c.time} · ${esc(c.subject)}</dd></div></dl><div class="section-heading"><h3>关联订单</h3><button class="text-button" data-service-order="${c.id}">查看详情 ${icon('arrow')}</button></div><div class="linked-order"><div class="image-placeholder">商品图待补</div><div><strong>${esc(c.product)}</strong><small class="mono">${c.order}</small><span>¥ ${c.amount} · ${orderInfo(c).state}</span></div></div></section><section><div class="section-heading"><h3>关联工单</h3><button class="text-button" data-action="ticket-new" data-id="${c.id}">${icon('plus')}新建</button></div>${ticketCards(c)}<div class="quiet-note">工单、会话和客户资料共用同一组演示记录，处理状态会同步显示。</div></section></div>`;
    } else if (ui.customerTab === 'history') {
      content = `<div class="section-heading"><h3>当前会话记录</h3><button class="btn" data-service-conversation="${c.id}">进入会话 ${icon('arrow')}</button></div><div class="customer-history">${c.messages
        .filter((m) => m.role !== 'note')
        .map(
          (m) =>
            `<article><div><b>${{ customer: c.name, staff: '周小雨', bot: 'Minihelp 助手', system: '服务记录' }[m.role]}</b><time>${esc(m.time)}</time></div><p>${esc(m.text)}</p></article>`,
        )
        .join('')}</div>`;
    } else {
      content = `<div class="section-heading"><h3>内部备注</h3><span>仅团队可见</span></div><form id="customer-note-form" data-customer="${c.id}" class="note-compose"><label for="customer-note">记录需要继续跟进的信息</label><textarea id="customer-note" name="note" required maxlength="1000" placeholder="例如：客户希望工作日下午通过站内消息联系。"></textarea><button class="btn primary" type="submit">保存备注</button></form>${
        notes.length
          ? `<div class="customer-history">${notes
              .toReversed()
              .map(
                (m) =>
                  `<article><div><b>周小雨</b><time>${esc(m.time)}</time></div><p>${esc(m.text)}</p></article>`,
              )
              .join('')}</div>`
          : empty('暂无内部备注，保存后也能在客服会话中看到。')
      }`;
    }
    return `<div class="customer-profile"><div class="row">${avatar(c.name, c.color)}<div><h2>${esc(c.name)}</h2><p>客户 C-${String(c.id).padStart(4, '0')} · Web 演示访客</p></div></div><button class="btn" data-service-edit-customer="${c.id}">编辑资料</button></div><div class="customer-tags">${c.tags.map((t) => pill(t, 'neutral')).join('')}</div>${tabs(
      'customer-detail',
      [
        ['summary', '资料概况'],
        ['history', '会话记录'],
        ['notes', `内部备注${notes.length ? ` · ${notes.length}` : ''}`],
      ],
      ui.customerTab,
    )}<div class="customer-detail-body">${content}</div>`;
  }

  function customersPage() {
    return `<div class="page admin-page service-page">${heading('CUSTOMER CONTEXT', '了解客户，再开始下一次对话。', '把资料、历史会话与售后进展放在一起。')}<div class="customer-workspace"><section class="panel customer-directory"><div class="panel-head"><h2>客户列表</h2><span class="muted small">${conversations.length} 位演示客户</span></div><div class="directory-tools"><label class="search">${icon('search')}<input id="customer-search" aria-label="搜索客户资料" placeholder="客户、标签或订单" value="${esc(ui.customerQuery)}"></label><div class="filter-row">${[
      ['all', '全部'],
      ['follow', '待跟进'],
      ['human', '我接待的'],
    ]
      .map(
        ([id, label]) =>
          `<button class="filter-chip ${ui.customerFilter === id ? 'active' : ''}" data-service-customer-filter="${id}" aria-pressed="${ui.customerFilter === id}">${label}</button>`,
      )
      .join(
        '',
      )}</div></div><div id="customer-list" class="customer-list">${customerList()}</div></section><section class="panel customer-detail" aria-label="客户详情">${customerDetail()}</section></div></div>`;
  }

  function orderRows() {
    const list = conversations.filter(
      (c) =>
        match(`${c.order} ${c.name} ${c.product}`, ui.orderQuery) &&
        (ui.orderFilter === 'all' ||
          (ui.orderFilter === 'exception' && c.id === 2) ||
          (ui.orderFilter === 'aftersales' && activeTickets(c).length)),
    );
    return list.length
      ? list
          .map(
            (c) =>
              `<tr><td><button class="table-actions table-title mono" data-service-order="${c.id}">${c.order}</button><span class="table-sub">Web · 演示订单</span></td><td><strong class="table-title">${esc(c.product)}</strong><span class="table-sub">数量 1 · 商品快照</span></td><td><button class="table-actions" data-service-view-customer="${c.id}">${esc(c.name)}</button></td><td class="mono">¥ ${c.amount}</td><td>${orderStatus(c)}</td><td>${activeTickets(c).length ? pill(`${activeTickets(c).length} 笔待跟进`, 'amber') : '<span class="muted">—</span>'}</td><td><button class="table-actions" data-service-order="${c.id}">详情 ${icon('chevron')}</button></td></tr>`,
          )
          .join('')
      : `<tr><td colspan="7">${empty('没有匹配的订单', 'reset-orders')}</td></tr>`;
  }

  function productCards() {
    const list = conversations.filter((c) => match(c.product, ui.productQuery));
    return list.length
      ? list
          .map(
            (c) =>
              `<article class="catalog-card"><div class="catalog-image"><div class="image-placeholder">商品图片待补</div><span class="muted small">演示商品</span></div><div class="catalog-body"><div class="between"><span class="mono small muted">SKU-${String(c.id).padStart(4, '0')}</span>${pill('样例', 'neutral')}</div><h3>${esc(c.product)}</h3><div class="catalog-price">¥ ${c.amount}<span>订单价格快照</span></div><div class="catalog-bottom"><span class="small muted">实时库存待接入</span><button class="text-button" data-service-product="${c.id}">商品资料 ${icon('arrow')}</button></div></div></article>`,
          )
          .join('')
      : empty('没有匹配的商品', 'reset-products');
  }

  function productsPage() {
    const aftersales = conversations.filter((c) => activeTickets(c).length).length;
    return `<div class="page admin-page service-page">${heading('COMMERCE CONTEXT', '商品与订单', '查询交易上下文，衔接每一步售后。', `<button class="btn" data-service-action="sync" ${ui.sync === 'running' ? 'disabled' : ''}>${icon('clock')}${ui.sync === 'running' ? '演示同步中…' : '演示同步'}</button>`)}${tabs(
      'products',
      [
        ['orders', '订单列表'],
        ['catalog', '商品目录'],
      ],
      ui.productTab,
    )}${ui.sync === 'done' ? '<div class="notice">已完成前端同步演示，沿用当前样例；没有获取真实平台数据。</div>' : ''}${
      ui.productTab === 'orders'
        ? `<div class="compact-metrics"><span>演示订单 <b>${conversations.length}</b></span><span>需核查物流 <b>1</b></span><span>售后跟进中 <b>${aftersales}</b></span></div><section class="panel"><div class="panel-toolbar"><div class="filter-row">${[
            ['all', '全部订单'],
            ['exception', '物流异常'],
            ['aftersales', '售后跟进'],
          ]
            .map(
              ([id, label]) =>
                `<button class="filter-chip ${ui.orderFilter === id ? 'active' : ''}" data-service-order-filter="${id}" aria-pressed="${ui.orderFilter === id}">${label}</button>`,
            )
            .join(
              '',
            )}</div><label class="search">${icon('search')}<input id="order-search" aria-label="搜索订单" placeholder="订单号、客户或商品" value="${esc(ui.orderQuery)}"></label></div><div class="table-wrap"><table><thead><tr><th>订单编号</th><th>商品</th><th>客户</th><th>实付金额</th><th>物流状态</th><th>售后</th><th>操作</th></tr></thead><tbody id="order-rows">${orderRows()}</tbody></table></div><div class="panel-footer">当前展示 6 笔样例订单，金额与物流均非真实业务数据。</div></section>`
        : `<div class="catalog-toolbar"><p class="muted">商品信息用于查看咨询上下文，库存与价格以正式业务系统为准。</p><label class="search">${icon('search')}<input id="product-search" aria-label="搜索商品" placeholder="搜索商品名称" value="${esc(ui.productQuery)}"></label></div><div class="catalog-grid" id="product-grid">${productCards()}</div>`
    }</div>`;
  }

  function showOrder(id) {
    const c = conversations.find((c) => c.id === Number(id));
    if (!c) return;
    const delivery =
      c.id === 2
        ? [
            ['已支付', '演示记录'],
            ['已交承运商', '演示记录'],
            ['运输信息超过 48 小时未更新', '待客服核查'],
          ]
        : [4, 6].includes(c.id)
          ? [
              ['已支付', '演示记录'],
              ['等待仓库发货', '尚无物流单号'],
            ]
          : [
              ['已支付', '演示记录'],
              ['已发货', '演示记录'],
              ['已签收', '演示记录'],
            ];
    const isClient = state.surface === 'client';
    modal(
      '订单详情',
      `<div class="between">${orderStatus(c)}<span class="small muted">Web 演示订单</span></div><div class="linked-order"><div class="image-placeholder">商品图待补</div><div><h3>${esc(c.product)}</h3><small class="mono">${c.order}</small><span>数量 1 · 实付 ¥ ${c.amount}</span></div></div><dl class="property-grid"><div><dt>客户</dt><dd>${esc(c.name)}</dd></div><div><dt>收货信息</dt><dd>待接入业务系统</dd></div></dl><h3>物流进展</h3><div class="timeline">${delivery.map(([title, time]) => `<div class="timeline-item">${title}<small>${time}</small></div>`).join('')}</div>${isClient ? '' : `<div class="section-heading"><h3>售后跟进</h3></div>${ticketCards(c)}`}<div class="quiet-note">本页为示例。申请售后后会创建待处理工单，是否符合退货条件仍需审核。</div>`,
      `<button class="btn" data-action="modal-close">关闭</button><button class="btn primary" data-action="${isClient ? 'client-ticket-new' : 'ticket-new'}" data-id="${c.id}">${icon('ticket')}${isClient ? '申请售后' : '创建售后工单'}</button>`,
    );
  }

  function showProduct(id) {
    const c = conversations.find((c) => c.id === Number(id));
    if (!c) return;
    const related = docs.filter((d) => d.scope === '全部商品' || c.product.includes(d.scope));
    modal(
      '商品资料',
      `<div class="linked-order"><div class="image-placeholder">商品图待补</div><div><h3>${esc(c.product)}</h3><small class="mono">SKU-${String(c.id).padStart(4, '0')}</small><span>订单快照 ¥ ${c.amount}</span></div></div><dl class="property-grid"><div><dt>实时库存</dt><dd>待接入</dd></div><div><dt>当前售价</dt><dd>待接入</dd></div></dl><div class="section-heading"><h3>相关知识</h3><span>含草稿与待审内容</span></div>${related.map((d) => `<button class="relation-row" data-doc="${d.id}"><span class="relation-icon">${icon('book')}</span><span><strong>${esc(d.title)}</strong><small>${d.version} · ${d.status === 'published' ? '已发布' : d.status === 'review' ? '待审核' : '草稿'}</small></span>${icon('chevron')}</button>`).join('')}<div class="quiet-note">商品图片和实时字段待提供；示例资料不用于判断实际库存或售后资格。</div>`,
    );
  }

  function membersPanel() {
    const roles = ['管理员', '主管', '客服', '知识运营'];
    const permissions = [
      ['接待与处理工单', [1, 1, 1, 0]],
      ['审核知识', [1, 1, 0, 1]],
      ['分配会话与工单', [1, 1, 0, 0]],
      ['配置成员与渠道', [1, 0, 0, 0]],
    ];
    const rows = permissions
      .map(
        ([label, values]) =>
          `<tr><td>${label}</td>${values.map((v) => `<td>${v ? '<span class="permission-yes">允许</span>' : '<span class="muted">—</span>'}</td>`).join('')}</tr>`,
      )
      .join('');
    return `<section class="panel"><div class="panel-head"><h2>团队成员</h2><span class="small muted">演示角色，不改变实际权限</span></div><div class="table-wrap"><table><thead><tr><th>成员</th><th>角色</th><th>范围</th><th>状态</th><th>操作</th></tr></thead><tbody>${members.map((m) => `<tr><td><div class="row">${avatar(m.name, 'green', true)}<strong>${esc(m.name)}${m.self ? '（我）' : ''}</strong></div></td><td>${esc(m.role)}</td><td>喵喵优选</td><td>${pill(m.status === 'active' ? '启用' : '停用', m.status === 'active' ? '' : 'neutral')}</td><td><button class="table-actions" data-service-member="${m.id}" ${m.self ? 'disabled title="当前演示管理员保留管理权限"' : ''}>调整角色</button></td></tr>`).join('')}</tbody></table></div></section><section class="panel settings-secondary"><div class="panel-head"><h2>角色权限方案</h2><span class="small muted">首版产品规划</span></div><div class="table-wrap"><table class="permission-table"><thead><tr><th>操作</th>${roles.map((r) => `<th>${r}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  function receptionPanel() {
    return `<form id="reception-form" class="panel settings-form"><div class="panel-head"><div><h2>接待规则</h2><p class="field-hint">预览工作时间和自动接待配置的操作方式。</p></div>${pill('演示配置', 'neutral')}</div><div class="settings-fields"><h3>服务时间</h3><div class="field-pair"><label class="field">开始时间<input name="start" type="time" value="${rules.start}" required></label><label class="field">结束时间<input name="end" type="time" value="${rules.end}" required></label></div><p class="field-hint">此处演示同一天的工作时段；跨夜排班将在正式版单独设置。</p><h3>默认接待方式</h3><div class="radio-cards">${[
      ['assist', 'AI 辅助', '先生成建议，由客服确认后发送。'],
      ['auto', 'AI 自动接待', '先由助手回复，必要时进入人工队列。'],
    ]
      .map(
        ([value, label, text]) =>
          `<label><input type="radio" name="mode" value="${value}" ${rules.mode === value ? 'checked' : ''}><span><strong>${label}</strong><small>${text}</small></span></label>`,
      )
      .join(
        '',
      )}</div><label class="field">非工作时间<select name="offline"><option value="ticket" ${rules.offline === 'ticket' ? 'selected' : ''}>记录问题并引导提交工单</option><option value="queue" ${rules.offline === 'queue' ? 'selected' : ''}>进入待接待队列</option></select></label><p id="reception-error" class="form-error" role="alert"></p></div><div class="settings-save"><span class="small muted">保存仅更新当前原型，不修改现有会话模式。</span><button class="btn primary" type="submit">保存演示配置</button></div></form>`;
  }

  function channelsPanel() {
    return `<section class="panel"><div class="panel-head"><h2>渠道接入</h2><span class="small muted">接入状态预览</span></div><div class="channel-row"><span class="relation-icon">${icon('chat')}</span><div><h3>网站咨询</h3><p>连接客户咨询页与客服工作台。</p></div>${pill('前端演示', 'neutral')}<button class="btn" data-page="client">打开咨询页</button></div><div class="channel-row"><span class="relation-icon">${icon('box')}</span><div><h3>电商平台</h3><p>等待确定首发平台与正式接入方式。</p></div>${pill('待接入', 'amber')}<button class="btn" data-service-action="channel-details">查看接入项</button></div></section><div class="quiet-note">原型不接收账号密码、Cookie 或密钥；没有真实的登录、连接测试和平台授权。</div>`;
  }

  function auditPanel() {
    return `<section class="panel"><div class="panel-head"><h2>本次演示操作</h2><span class="small muted">刷新后清空</span></div>${audit.length ? `<div class="table-wrap"><table><thead><tr><th>时间</th><th>操作人</th><th>操作</th><th>内容</th></tr></thead><tbody>${audit.map((a) => `<tr><td>${esc(a.time)}</td><td>周小雨</td><td>${esc(a.action)}</td><td>${esc(a.detail)}</td></tr>`).join('')}</tbody></table></div>` : empty('还没有设置变更。保存接待规则或调整成员角色后，会在这里留下演示记录。')}</section>`;
  }

  function settingsPage() {
    const sections = [
      ['members', '成员与角色', 'users'],
      ['reception', '接待规则', 'headset'],
      ['channels', '渠道接入', 'box'],
      ['audit', '操作记录', 'file'],
    ];
    const views = {
      members: membersPanel,
      reception: receptionPanel,
      channels: channelsPanel,
      audit: auditPanel,
    };
    return `<div class="page admin-page service-page">${heading('WORKSPACE SETTINGS', '设置与权限', '让团队的接待方式、成员职责和渠道状态清楚可见。')}<div class="settings-layout"><nav class="settings-nav" aria-label="设置分类">${sections.map(([id, label, ico]) => `<button class="${ui.settingsTab === id ? 'active' : ''}" data-service-tab="settings:${id}" aria-pressed="${ui.settingsTab === id}">${icon(ico)}${label}${icon('chevron')}</button>`).join('')}</nav><div class="settings-content">${views[ui.settingsTab]()}</div></div></div>`;
  }

  function editCustomer(id) {
    const c = conversations.find((c) => c.id === Number(id));
    modal(
      `${c.name} · 编辑资料`,
      `<form id="customer-edit-form" data-customer="${c.id}"><label class="field">客户标签<input name="tags" value="${esc(c.tags.join('，'))}" maxlength="100"><span class="field-hint">最多 5 个标签，用逗号分隔，每个标签不超过 12 字。</span></label><label class="field">联系偏好<select name="preference">${['优先站内回复', '工作时间联系', '等待客户主动联系'].map((value) => `<option ${value === (preferences.get(c.id) || '优先站内回复') ? 'selected' : ''}>${value}</option>`).join('')}</select></label><p class="quiet-note">仅修改演示资料；标签会同步出现在客服工作台。</p><p class="form-error" id="customer-edit-error" role="alert"></p></form>`,
      `<button class="btn" data-action="modal-close">取消</button><button class="btn primary" type="submit" form="customer-edit-form">保存资料</button>`,
    );
  }

  function editMember(id) {
    const member = members.find((m) => m.id === Number(id));
    if (!member || member.self) return;
    modal(
      `${member.name} · 调整角色`,
      `<form id="member-edit-form" data-member="${member.id}"><label class="field">角色<select name="role">${['管理员', '主管', '客服', '知识运营'].map((role) => `<option ${member.role === role ? 'selected' : ''}>${role}</option>`).join('')}</select></label><label class="field">成员状态<select name="status"><option value="active" ${member.status === 'active' ? 'selected' : ''}>启用</option><option value="disabled" ${member.status === 'disabled' ? 'selected' : ''}>停用</option></select></label><div class="notice">这里只演示设置流程，不修改任何真实账号和访问权限。</div></form>`,
      `<button class="btn" data-action="modal-close">取消</button><button class="btn primary" type="submit" form="member-edit-form">保存演示设置</button>`,
    );
  }

  function onClick(el) {
    const d = el.dataset;
    if (d.serviceTab) {
      const [group, tab] = d.serviceTab.split(':');
      ui[
        group === 'customer-detail'
          ? 'customerTab'
          : group === 'products'
            ? 'productTab'
            : 'settingsTab'
      ] = tab;
      render();
      return true;
    }
    if (d.serviceCustomer) {
      ui.customer = Number(d.serviceCustomer);
      render();
      return true;
    }
    if (d.serviceCustomerFilter) {
      ui.customerFilter = d.serviceCustomerFilter;
      render();
      return true;
    }
    if (d.serviceViewCustomer) {
      ui.customer = Number(d.serviceViewCustomer);
      ui.customerQuery = '';
      ui.customerFilter = 'all';
      ui.customerTab = 'summary';
      go('customers');
      return true;
    }
    if (d.serviceEditCustomer) {
      editCustomer(d.serviceEditCustomer);
      return true;
    }
    if (d.serviceConversation) {
      state.selected = Number(d.serviceConversation);
      state.mode = 'reply';
      go('workbench');
      return true;
    }
    if (d.serviceOrder) {
      showOrder(d.serviceOrder);
      return true;
    }
    if (d.serviceProduct) {
      showProduct(d.serviceProduct);
      return true;
    }
    if (d.serviceOrderFilter) {
      ui.orderFilter = d.serviceOrderFilter;
      render();
      return true;
    }
    if (d.serviceMember) {
      editMember(d.serviceMember);
      return true;
    }
    if (d.serviceAction === 'reset-customers') {
      ui.customerQuery = '';
      ui.customerFilter = 'all';
      render();
      return true;
    }
    if (d.serviceAction === 'reset-orders') {
      ui.orderQuery = '';
      ui.orderFilter = 'all';
      render();
      return true;
    }
    if (d.serviceAction === 'reset-products') {
      ui.productQuery = '';
      render();
      return true;
    }
    if (d.serviceAction === 'channel-details') {
      modal(
        '电商渠道 · 待接入项',
        '<div class="page-map"><div class="map-row"><h3>账号与授权</h3><p>明确店铺范围、授权状态、失效后的重新连接流程。</p></div><div class="map-row"><h3>消息与业务</h3><p>验证消息收发、订单查询、商品同步和人工转接。</p></div></div><p class="quiet-note">这些能力仍待后端实现，本页不进行平台登录。</p>',
      );
      return true;
    }
    if (d.serviceAction === 'sync') {
      ui.sync = 'running';
      render();
      setTimeout(() => {
        ui.sync = 'done';
        log('同步演示', '沿用现有商品与订单样例');
        if (state.page === 'products') render();
        toast('同步演示完成，没有连接外部平台');
      }, 900);
      return true;
    }
    return false;
  }

  function onInput(el) {
    if (el.id === 'customer-search') {
      ui.customerQuery = el.value;
      $('#customer-list').innerHTML = customerList();
    }
    if (el.id === 'order-search') {
      ui.orderQuery = el.value;
      $('#order-rows').innerHTML = orderRows();
    }
    if (el.id === 'product-search') {
      ui.productQuery = el.value;
      $('#product-grid').innerHTML = productCards();
    }
  }

  function onSubmit(event) {
    const form = event.target;
    if (
      !['customer-note-form', 'customer-edit-form', 'member-edit-form', 'reception-form'].includes(
        form.id,
      )
    )
      return false;
    event.preventDefault();
    const data = new FormData(form);
    if (form.id === 'customer-note-form') {
      const note = String(data.get('note')).trim();
      if (!note) {
        toast('请填写备注内容');
        return true;
      }
      conversations
        .find((c) => c.id === Number(form.dataset.customer))
        .messages.push({ role: 'note', text: note, time: stamp() });
      render();
      toast('内部备注已保存，仅在团队视角显示');
    }
    if (form.id === 'customer-edit-form') {
      const tags = [
        ...new Set(
          String(data.get('tags'))
            .split(/[,，]/)
            .map((t) => t.trim())
            .filter(Boolean),
        ),
      ];
      if (tags.length > 5 || tags.some((t) => t.length > 12)) {
        $('#customer-edit-error').textContent = '最多填写 5 个标签，每个不超过 12 字。';
        return true;
      }
      const c = conversations.find((c) => c.id === Number(form.dataset.customer));
      c.tags = tags;
      preferences.set(c.id, String(data.get('preference')));
      $('#modal').close();
      render();
      toast('演示客户资料已更新');
    }
    if (form.id === 'member-edit-form') {
      const m = members.find((m) => m.id === Number(form.dataset.member));
      m.role = String(data.get('role'));
      m.status = String(data.get('status'));
      log('成员设置', `${m.name} · ${m.role} · ${m.status === 'active' ? '启用' : '停用'}`);
      $('#modal').close();
      render();
      toast('演示角色已更新，不改变实际权限');
    }
    if (form.id === 'reception-form') {
      const start = String(data.get('start')),
        end = String(data.get('end'));
      if (start >= end) {
        $('#reception-error').textContent = '结束时间需晚于开始时间。';
        return true;
      }
      rules.start = start;
      rules.end = end;
      rules.mode = String(data.get('mode'));
      rules.offline = String(data.get('offline'));
      log('接待规则', `${start}–${end} · ${rules.mode === 'assist' ? 'AI 辅助' : 'AI 自动接待'}`);
      render();
      toast('演示配置已保存，可在操作记录查看');
    }
    return true;
  }

  return {
    hasPage: (page) => Object.hasOwn(titles, page),
    title: (page) => titles[page],
    renderPage: (page) =>
      ({ customers: customersPage, products: productsPage, settings: settingsPage })[page](),
    surface: (page) => (page === 'settings' ? 'admin' : 'workbench'),
    onClick,
    onInput,
    onSubmit,
    showOrder,
    orderStatus,
    pagePlans: {
      customers: {
        name: '客户资料',
        icon: 'users',
        stage: '本轮可体验',
        text: '客户搜索与筛选、标签与联系偏好、关联会话及工单、仅团队可见的内部备注。',
      },
      products: {
        name: '商品与订单',
        icon: 'box',
        stage: '本轮可体验',
        text: '订单筛选与详情、物流进展、售后工单、商品目录和相关知识；同步仅为演示。',
      },
      settings: {
        name: '设置与权限',
        icon: 'settings',
        stage: '本轮可体验',
        text: '成员角色与权限矩阵、接待规则、渠道接入说明和本次演示操作记录。',
      },
    },
  };
};
