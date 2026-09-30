/* Product planning prototype. All records, metrics and task runs below are illustrative. */
window.createMinihelpPanels = function createMinihelpPanels(h) {
  'use strict';
  const {esc,icon,pill,stat,docs,tickets,conversations,modal,toast,render,go} = h;
  const $ = s => document.querySelector(s);
  const titles = {overview:'管理总览',knowledge:'知识中心',review:'知识缺口',quality:'RAG 质量',observability:'观测与成本',topics:'咨询主题',models:'分类器管理',jobs:'作业中心',migration:'原功能对照'};
  const tabs = {knowledge:'content',quality:'comparison',observability:'cost',models:'overview'};
  const ui = {reviewFilter:'pending',candidateFilter:'pending',caseFilter:'all',metric:'mrr',topic:'全部',jobGroup:'全部',jobStatus:'全部',importText:'## 退货包装要求\n商品未使用且配件齐全时，可先提交退货申请。\n\n## 包装已拆封\n请提供包装现状说明，由客服确认是否影响寄回和验收。',importType:'policy',chunks:[],searchQuery:'包装拆开可以退吗？',searchStrategy:'hybrid_rerank',searchDone:false,trialText:'物流一直没更新，我想申请退款',trialDone:false};
  const candidates = [
    {id:1,q:'猫砂盆外包装拆封后可以退吗？',a:'未使用且配件齐全的商品可以先登记申请，包装现状由客服进一步确认。',source:'历史会话 MH-0821',batch:'B-0922-01',state:'pending'},
    {id:2,q:'宠物包缺少肩带怎么处理？',a:'请提供订单和缺件照片，由客服核对后安排补发。',source:'历史会话 MH-0806',batch:'B-0922-01',state:'pending'},
    {id:3,q:'订单 MH-0123 什么时候送到？',a:'您的订单明天下午送到。',source:'历史会话 MH-0792',batch:'B-0922-01',state:'rejected',reason:'只适用于单笔订单，不能转成通用知识。'}
  ];
  const gaps = [
    {id:1,q:'智能猫砂盆可以放在阳台使用吗？',count:4,source:'低置信度',state:'pending',reason:'现有知识未说明使用环境限制。',snapshot:[['智能猫砂盆使用与保养','0.53','有清洁说明，缺少户外使用范围'],['商品保修说明','0.42','与使用环境相关性不足']]},
    {id:2,q:'换货期间可以先借用备用设备吗？',count:2,source:'用户反馈未解决',state:'pending',reason:'无备用设备服务条款，需运营确认。',snapshot:[['退换货与售后政策','0.49','没有备用设备条款']]},
    {id:3,q:'饮水机滤芯多久更换？',count:3,source:'低置信度',state:'approved',answer:'请参考产品说明书与实际水质，定期检查滤芯状态。',reason:'运营已补充产品使用说明。',snapshot:[['饮水机使用说明','0.61','示例检索快照']]}
  ];
  const indexRows = [{doc:1,blocks:7,state:'done',version:'v1.3'},{doc:2,blocks:5,state:'done',version:'v1.2'},{doc:4,blocks:4,state:'done',version:'v1.0'},{doc:3,blocks:6,state:'pending',version:'v1.0 待审核'}];
  const cases = [
    {id:'FC-008',q:'拆开包装后一定可以退货吗？',answer:'拆封也一定可以退，运费全部由店铺承担。',reason:'回答作出无依据的保证，运费责任缺少证据。',evidence:'规则只支持先登记申请，再审核商品和包装状态。',state:'pending',seen:3,note:''},
    {id:'FC-007',q:'周末也能当天发货吗？',answer:'周末下单一律当天发出。',reason:'知识库仅约定常规商品 48 小时内发货。',evidence:'常规现货付款后 48 小时内发出。',state:'resolved',seen:2,note:'已补充节假日说明，并要求回答引用发货政策。'},
    {id:'FC-006',q:'说明书在哪里下载？',answer:'可以联系人工客服获取电子说明书。',reason:'裁判认为没有给出下载链接。',evidence:'客服可提供对应型号说明书。',state:'dismissed',seen:1,note:'回答没有编造，原政策允许联系人工获取。'}
  ];
  const strategies = [
    {id:'vector',name:'纯向量',recall:0.79,mrr:0.68,coverage:0.73},
    {id:'bm25',name:'BM25',recall:0.75,mrr:0.65,coverage:0.70},
    {id:'hybrid',name:'混合检索',recall:0.88,mrr:0.78,coverage:0.83},
    {id:'hybrid_rerank',name:'混合 + 重排',recall:0.92,mrr:0.86,coverage:0.90}
  ];
  // Snapshot of Minihelp app/core/taxonomy.py, in the original label-id order.
  const topics = ['退换货','物流','尺码','发票','质量问题','运费','优惠活动','价保','支付','订单修改','库存补货','商品信息','保修维修','账号','会员积分','评价','其他'];
  const topicQuestions = [
    {q:'包装拆开了，可以退吗？',labels:['退换货'],score:.94}, {q:'物流一直没更新，我想申请退款',labels:['物流','退换货'],score:.91},
    {q:'猫砂盆的长宽分别是多少？',labels:['尺码'],score:.97}, {q:'滤芯多久需要更换？',labels:['商品信息'],score:.93},
    {q:'能修改收货地址吗？',labels:['订单修改'],score:.95}, {q:'这单怎么开电子发票？',labels:['发票'],score:.96},
    {q:'支付失败但银行卡扣款了',labels:['支付'],score:.90}, {q:'有新人优惠券吗？',labels:['优惠活动'],score:.96},
    {q:'饮水机收到后无法启动',labels:['质量问题'],score:.92}, {q:'断货的宠物包什么时候补货？',labels:['库存补货'],score:.97},
    {q:'过了七天还可以维修吗？',labels:['保修维修'],score:.93}, {q:'颜色拍错了，能换货吗？',labels:['退换货'],score:.95},
    {q:'这次购买可以积多少分？',labels:['会员积分'],score:.91}, {q:'怎么注销账号？',labels:['账号'],score:.94},
    {q:'刚买就降价了，可以补差价吗？',labels:['价保'],score:.96}, {q:'请帮我联系人工客服',labels:['其他'],score:.99},
    {q:'我想补充晒单评价',labels:['评价'],score:.93}, {q:'退货寄回的运费谁承担？',labels:['退换货','运费'],score:.92},
    {q:'快递已经签收但我没收到',labels:['物流'],score:.94}, {q:'保修期内维修需要付费吗？',labels:['保修维修'],score:.90}
  ];
  const jobDefs = [
    ['kb-preview','材料与切块预览','知识','本地材料'],['kb-build','离线建库','知识','数据库'],['kb-mine','对话挖知识','知识','数据库、模型'],['kb-vectorize','补齐待处理向量','知识','数据库、嵌入、Milvus'],['kb-repatch','知识补丁更新','知识','数据库、更新后的原文'],['seed-conv','导入历史会话样例','知识','测试数据库'],['kb-reset','清库重建','知识','数据库、Milvus；会清空知识'],
    ['eval-rag','RAG 四策略评估','质量','知识索引、模型'],['cost-report','意图成本报表','观测','Langfuse 记录'],['eval-flywheel','质量趋势评估','观测','数据库、索引、模型'],['calibrate-confidence','证据置信度校准','观测','索引、重排服务'],
    ['ch10-golden','黄金样例检查','分类器','模型'],['ch10-corpus','语料准备','分类器','问题池、模型'],['ch10-dataset','数据集划分与增强','分类器','语料、模型'],['ch10-train','分类器训练','分类器','数据集、训练依赖'],['ch10-eval','分类器评测','分类器','已训练权重'],['ch10-export','ONNX 导出与校验','分类器','已训练权重'],['ch10-threshold-scan','分类阈值扫描','分类器','推理服务'],['classifier-up','启动分类服务','分类器','已导出 ONNX'],['classifier-down','停止分类服务','分类器','分类服务'],['classify-pool','问题池批量归类','分类器','数据库、分类服务'],['classify-pool-force','小批问题归类','分类器','数据库、分类服务']
  ];
  const jobs = jobDefs.map(([id,name,group,needs])=>({id,name,group,needs,state:'idle',logs:[],timer:null}));
  const jobState = j => pill(({idle:'未运行',running:'演示运行中',done:'演示已完成',stopped:'演示已停止'})[j.state],j.state==='running'?'blue':j.state==='idle'?'neutral':'');
  const status = s => pill(({pending:'待审核',approved:'已采纳',rejected:'已驳回',resolved:'已解决',dismissed:'无需处理'})[s],s==='pending'?'amber':s==='rejected'||s==='dismissed'?'neutral':'');
  const button = (label, action, id='', cls='') => `<button class="btn ${cls}" data-panel-action="${action}" data-panel-id="${esc(id)}">${label}</button>`;
  const link = (label,page) => `<button class="table-actions" data-page="${page}">${label} ${icon('arrow')}</button>`;
  const task = (id,label='演示运行') => button(`${icon('arrow')}${label}`,'job-confirm',id,'soft');
  const panel = (title,body,extra='') => `<section class="panel"><div class="panel-head"><h2>${title}</h2>${extra}</div>${body}</section>`;
  const table = (heads,rows) => `<div class="table-wrap"><table><thead><tr>${heads.map(s=>`<th>${s}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${heads.length}"><div class="empty">暂无符合条件的记录</div></td></tr>`}</tbody></table></div>`;
  const pageHead = (eyebrow,title,desc,actions='') => `<div class="page-title between"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${desc}</p></div><div class="page-actions">${actions}</div></div>`;
  const demo = '<div class="demo-strip"><span class="dot amber"></span>本页为交互原型 · 数据、指标及运行结果均为示例，未连接原项目服务。</div>';
  const subnav = (section,items) => `<nav class="section-tabs" aria-label="${titles[section]}子页面">${items.map(([id,label])=>`<button data-panel-tab="${section}:${id}" class="${tabs[section]===id?'active':''}" aria-current="${tabs[section]===id?'page':'false'}">${label}</button>`).join('')}</nav>`;
  const sourceLine = text => `<p class="source-line">${icon('file')}原功能来源：${text}</p>`;
  function overview() {
    const items=[
      ['knowledge','book','知识中心','维护可信的回复依据',`${docs.filter(d=>d.status==='published').length} 篇已发布 · ${candidates.filter(r=>r.state==='pending').length} 条候选待审`,'内容与来源 / 切块入库 / 索引状态 / 检索自测'],
      ['review','search','知识缺口','把未解决的问题补进知识',`${gaps.filter(r=>r.state==='pending').length} 条待审核`,'原始问法 / 检索快照 / 填写答案 / 审核写回'],
      ['quality','shield','RAG 质量','查看回答质量与问题记录',`${cases.filter(r=>r.state==='pending').length} 条示例个案待处理`,'策略对照 / 证据覆盖 / 拒答 / 编造个案台账'],
      ['observability','chart','观测与成本','观察消耗、趋势和阈值','3 个报表视角','意图消耗 / 评估趋势 / 推荐阈值与当前值'],
      ['topics','chat','咨询主题','从问题分布发现需求',`${topicQuestions.length} 条示例问题`,'17 类统计 / 多标签 / 样例与问题明细'],
      ['models','spark','分类器管理','查看模型从数据到服务的状态','9 项验收入口','语料 / 评测 / ONNX / 错例 / 单句试分类']
    ];
    return `<div class="page admin-page">${pageHead('SERVICE OPERATIONS','把服务做好，也把系统看清。','从接待到知识、质量与模型，原有能力都有明确入口。',button(`${icon('file')}原功能对照`,'go','migration'))}${demo}<div class="overview-layout"><div><div class="overview-heading"><h2>管理工作区</h2><span class="small muted">承接原后台的六个模块</span></div><div class="module-grid">${items.map(([page,ico,title,desc,kpi,foot])=>`<button class="module-card" data-page="${page}"><div class="module-card-top"><span class="module-icon">${icon(ico)}</span>${icon('arrow')}</div><h2>${title}</h2><p>${desc}</p><strong>${kpi}</strong><small>${foot}</small></button>`).join('')}</div></div><aside><section class="aside-panel"><div class="eyebrow">需要处理</div><h3>先处理这些事</h3><button class="todo-row" data-page="review"><span>审核知识缺口<small>判断缺知识，还是没有检索到</small></span><b>${gaps.filter(r=>r.state==='pending').length}</b></button><button class="todo-row" data-panel-dest="knowledge:mining"><span>复核候选问答<small>历史对话挖出的内容</small></span><b>${candidates.filter(r=>r.state==='pending').length}</b></button><button class="todo-row" data-panel-dest="quality:cases"><span>处理质量个案<small>保留证据与处置理由</small></span><b>${cases.filter(r=>r.state==='pending').length}</b></button></section><section class="aside-panel accent"><div class="eyebrow">作业集中管理</div><h3>长任务有地方可追踪</h3><p>建库、评估、校准、训练和导出，在同一处查看运行状态与日志。</p>${button(`打开作业中心 ${icon('arrow')}`,'go','jobs')}</section><section class="aside-panel"><h3>与客服工作台连接</h3><p>接待会话、订单和工单在服务工作区。未解决反馈进入知识缺口，知识更新后再评估效果。</p>${button('进入客服工作台','go','workbench')}</section></aside></div>${sourceLine('/admin → 六模块状态汇总；新增待办与独立作业入口')}</div>`;
  }
  function knowledge() {
    const header=pageHead('KNOWLEDGE OPERATIONS','知识中心','保留录入、挖掘、审核、向量化和检索的完整工作流。',`<button class="btn primary" data-action="doc-new">${icon('plus')}添加知识</button>`);
    const nav=subnav('knowledge',[['content','知识内容'],['import','录入与切块'],['mining','对话挖知识'],['index','索引状态'],['search','检索自测']]);
    let body='';
    if(tabs.knowledge==='content') body=`<div class="stat-strip">${stat('知识总数',docs.length,'篇','演示内容')}${stat('已发布',docs.filter(d=>d.status==='published').length,'篇','示例发布状态')}${stat('待审核',docs.filter(d=>d.status==='review').length,'篇','等待确认')}${stat('草稿',docs.filter(d=>d.status==='draft').length,'篇','尚未生效')}</div>${panel('知识内容',`<div class="panel-toolbar">${[['all','全部'],['published','已发布'],['review','待审核'],['draft','草稿']].map(([id,label])=>`<button class="filter-chip ${h.state.docFilter===id?'active':''}" data-doc-filter="${id}">${label}</button>`).join('')}<label class="search">${icon('search')}<input id="doc-search" aria-label="搜索知识" placeholder="搜索知识" value="${esc(h.state.docSearch)}"></label></div><div class="table-wrap"><table><thead><tr><th>名称</th><th>适用范围</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody id="knowledge-rows">${h.knowledgeRows()}</tbody></table></div>`,link('处理知识缺口','review'))}`;
    if(tabs.knowledge==='import') body=`<div class="split-panels">${panel('录入内容',`<form class="panel-pad" id="chunk-form"><label class="field">内容类型<select id="import-type"><option value="policy" ${ui.importType==='policy'?'selected':''}>政策条款</option><option value="faq" ${ui.importType==='faq'?'selected':''}>常见问答</option><option value="product" ${ui.importType==='product'?'selected':''}>商品说明</option></select></label><label class="field">Markdown 正文<textarea id="import-text" required maxlength="10000" class="large-textarea">${esc(ui.importText)}</textarea></label><div class="form-actions"><button class="btn primary" type="submit">${icon('search')}切块预览</button>${button('填入示例','import-sample')}</div><p class="field-hint">此处按段落演示切块；正式版复用原有切块、关键条款识别和指纹去重接口。</p></form>`)}${panel('切块预览',`<div class="panel-pad" id="chunk-preview">${chunkPreview()}</div>`)} </div><div class="section-gap">${panel('建库材料',table(['来源','类型','说明','操作'],[['退换货与售后政策.md','政策条款'],['商品使用说明.md','商品说明'],['常见问题整理.md','FAQ']].map(([name,type])=>`<tr><td>${icon('file')} ${name}</td><td>${type}</td><td class="muted">示例来源文件</td><td>${button('载入示例','source-load',name)}</td></tr>`)),task('kb-build','演示离线建库'))}</div>`;
    if(tabs.knowledge==='mining') body=`<div class="notice">从历史对话抽取的问答，需要人工判断是否具有通用性。这里保留来源与批次，与“用户未解决问题”的知识缺口分别管理。</div>${panel('候选问答',`<div class="panel-toolbar">${[['pending','待审核'],['approved','已采纳'],['rejected','已弃用'],['all','全部']].map(([id,label])=>`<button class="filter-chip ${ui.candidateFilter===id?'active':''}" data-panel-filter="candidateFilter:${id}">${label}</button>`).join('')}</div>${candidateTable()}`,task('kb-mine','演示挖掘任务'))}`;
    if(tabs.knowledge==='index') {const done=indexRows.filter(r=>r.state==='done').reduce((n,r)=>n+r.blocks,0),pending=indexRows.filter(r=>r.state==='pending').reduce((n,r)=>n+r.blocks,0);body=`<div class="stat-strip">${stat('数据库知识块',done+pending,'块','演示索引批次')}${stat('已向量化',done,'块','示例向量记录')}${stat('待处理',pending,'块','保留原文，可补偿重试')}${stat('待处理文档',indexRows.filter(r=>r.state==='pending').length,'篇','发布前检查')}</div>${panel('索引与双写状态',table(['来源文档','版本','知识块','数据库','向量索引'],indexRows.map(r=>`<tr><td>${esc(docs.find(d=>d.id===r.doc)?.title||'新增内容')}</td><td>${r.version}</td><td>${r.blocks}</td><td>${pill('已保存')}</td><td>${r.state==='done'?pill('已同步'):pill('待向量化','amber')}</td></tr>`)),task('kb-vectorize','演示补齐索引'))}<div class="notice section-gap">原文保存与向量化分开显示。补齐索引不会自动把待审文档改为已发布；正式发布还需审核与版本激活。</div><div class="form-actions">${task('kb-repatch','演示补丁更新')}${button('查看作业记录','go','jobs')}</div>`;}
    if(tabs.knowledge==='search') body=`${panel('检索自测',`<form class="panel-pad" id="search-test-form"><div class="query-grid"><label class="field">换一种说法提问<input name="q" id="retrieval-query" required maxlength="500" value="${esc(ui.searchQuery)}"></label><label class="field">检索策略<select name="strategy" id="retrieval-strategy">${strategies.map(s=>`<option value="${s.id}" ${ui.searchStrategy===s.id?'selected':''}>${s.name}</option>`).join('')}</select></label><button class="btn primary" type="submit">${icon('search')}预览召回</button></div><p class="field-hint">示例按关键词匹配显示已发布内容，分数仅演示字段。正式版接入原 /api/kb/search。</p></form><div id="retrieval-results">${retrievalResults()}</div>`)} `;
    return `<div class="page admin-page">${header}${demo}${nav}${body}${sourceLine('/kb；知识缺口审核另见 /review')}</div>`;
  }
  function chunkPreview() {
    if(!ui.chunks.length)return '<div class="empty">先预览，确认内容结构后再保存。</div>';
    return `<p class="small muted" style="margin-bottom:16px">${ui.chunks.length} 个示例片段 · 未执行真实查重</p>${ui.chunks.map((text,i)=>`<article class="chunk-card"><div class="between"><span class="mono small">CHUNK ${String(i+1).padStart(2,'0')}</span>${pill(ui.importType,'neutral')}</div><p>${esc(text).replace(/\n/g,'<br>')}</p></article>`).join('')}${button('保存为演示草稿','chunks-save','','primary')}`;
  }
  function candidateTable() {
    return table(['候选问答','来源','状态','操作'],candidates.filter(r=>ui.candidateFilter==='all'||r.state===ui.candidateFilter).map(r=>`<tr><td class="wide-cell"><b>${esc(r.q)}</b><span class="table-sub">${esc(r.a)}</span></td><td>${esc(r.source)}<span class="table-sub mono">${r.batch}</span></td><td>${status(r.state)}</td><td>${button('复核','candidate',r.id)}</td></tr>`));
  }
  function retrievalResults() {
    if(!ui.searchDone)return '<div class="empty">召回结果将展示来源、片段和得分。</div>';
    const terms=/退|包装|运费/.test(ui.searchQuery)?['退','包装']:/发货|物流|快递/.test(ui.searchQuery)?['配送']:[];
    const hits=docs.filter(d=>d.status==='published'&&terms.some(k=>d.title.includes(k)));
    if(!hits.length)return '<div class="empty">示例知识未匹配到内容。正式版将在这里展示低置信度和转人工建议。</div>';
    return table(['召回内容','来源版本','示例得分','操作'],hits.map((d,i)=>`<tr><td class="wide-cell"><b>${esc(d.title)}</b><span class="table-sub">${esc(d.text.slice(0,85))}</span></td><td>${d.version}</td><td class="mono">${(.92-i*.07).toFixed(2)}</td><td><button class="table-actions" data-doc="${d.id}">查看来源</button></td></tr>`));
  }
  function review() {
    return `<div class="page admin-page">${pageHead('KNOWLEDGE GAPS','把未解决的问题，变成下一次的答案。','保留原始问法和检索证据，再决定是否补充知识。')}${demo}<div class="stat-strip">${stat('待审核',gaps.filter(g=>g.state==='pending').length,'条','需要人工判断')}${stat('已通过',gaps.filter(g=>g.state==='approved').length,'条','已记录处理结果')}${stat('已驳回',gaps.filter(g=>g.state==='rejected').length,'条','保留理由与来源')}${stat('来源',2,'类','低置信度 / 未解决反馈')}</div>${panel('知识缺口队列',`<div class="panel-toolbar">${[['pending','待审核'],['approved','已通过'],['rejected','已驳回'],['all','全部']].map(([id,label])=>`<button class="filter-chip ${ui.reviewFilter===id?'active':''}" data-panel-filter="reviewFilter:${id}">${label}</button>`).join('')}</div>${table(['标准化问题','来源','出现次数','状态','操作'],gaps.filter(g=>ui.reviewFilter==='all'||g.state===ui.reviewFilter).map(g=>`<tr><td class="wide-cell"><b>${esc(g.q)}</b><span class="table-sub">${esc(g.reason)}</span></td><td>${g.source}</td><td>${g.count}</td><td>${status(g.state)}</td><td>${button('查看证据','gap',g.id)}</td></tr>`))}`,link('候选问答在知识中心','knowledge'))}${sourceLine('/review → 原问题、检索快照、标准化查重、人工审核、写回知识库')}</div>`;
  }
  function quality() {
    const names={mrr:'MRR',recall:'Recall@5',coverage:'证据覆盖率'};
    let body='';
    if(tabs.quality==='comparison')body=`<div class="two-col"><section class="panel"><div class="panel-head"><h2>四策略检索对照</h2><span class="pill neutral">示例报告</span></div><div class="panel-toolbar">${Object.entries(names).map(([id,name])=>`<button class="filter-chip ${ui.metric===id?'active':''}" data-panel-filter="metric:${id}">${name}</button>`).join('')}</div><div class="bar-chart" aria-label="四策略示例指标">${strategies.map(s=>`<div class="bar-row"><span>${s.name}</span><div class="bar-track"><span style="width:${s[ui.metric]*100}%"></span></div><b>${s[ui.metric].toFixed(2)}</b></div>`).join('')}<div class="chart-foot">${names[ui.metric]} · 范围 0–1 · 此处数值仅用于预览图表</div></div></section>${panel('生成质量与拒答',`<div class="panel-pad"><div class="score-row"><span>回答忠实度</span><strong>0.91</strong>${pill('示例')}</div><div class="score-row"><span>库外正确拒答</span><strong>9 / 10</strong>${pill('示例')}</div><div class="score-row"><span>答案覆盖度</span><strong>0.88</strong>${pill('示例')}</div><p class="field-hint">检索与生成分别呈现。正式报告若只有检索段，应明确显示“生成评估未完成”。</p></div>`)}</div><div class="section-gap">${panel('策略详情',table(['检索策略','Recall@5','MRR','证据覆盖','来源'],strategies.map(s=>`<tr><td>${s.name}</td><td>${s.recall.toFixed(2)}</td><td>${s.mrr.toFixed(2)}</td><td>${s.coverage.toFixed(2)}</td><td class="muted">预设示例数据</td></tr>`)))}</div>`;
    if(tabs.quality==='cases')body=`<div class="notice">保留“裁判判出”和“人工确认”的区别。历史累计台账与本轮评估分母分开统计，处理记录不随新报告覆盖。</div>${panel('编造个案台账',`<div class="panel-toolbar">${[['all','全部'],['pending','未解决'],['resolved','已解决'],['dismissed','无需处理']].map(([id,label])=>`<button class="filter-chip ${ui.caseFilter===id?'active':''}" data-panel-filter="caseFilter:${id}">${label}</button>`).join('')}</div>${table(['问题与判断','出现次数','状态','操作'],cases.filter(c=>ui.caseFilter==='all'||c.state===ui.caseFilter).map(c=>`<tr><td class="wide-cell"><b>${esc(c.q)}</b><span class="table-sub">${esc(c.reason)}</span></td><td>${c.seen}</td><td>${status(c.state)}</td><td>${button('复核个案','case',c.id)}</td></tr>`))}`)}`;
    return `<div class="page admin-page">${pageHead('RAG QUALITY','让回答质量，经得起核对。','看策略、看证据，也跟进每一个需要纠正的回答。',task('eval-rag','演示重跑评估'))}${demo}${subnav('quality',[['comparison','检索与生成评估'],['cases','编造个案台账']])}${body}${sourceLine('/rag-eval → 四策略报告、生成评估、拒答案例、跨轮个案处理')}</div>`;
  }
  function observability() {
    let body='';
    if(tabs.observability==='cost')body=`${panel('按意图观察调用消耗',table(['意图','示例请求数','示例 token','占比','观察'],[['售后咨询','120','180,000','45%','上下文较长'],['商品咨询','100','120,000','30%','关注知识覆盖'],['物流查询','80','60,000','15%','优先业务查询'],['其他','40','40,000','10%','观察长尾']].map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`)),task('cost-report','演示生成报表'))}<div class="notice section-gap">token 用量与实际费用分开表达。原报表按意图汇总 trace；生产版按供应商价格和计费单位另算金额。</div>`;
    if(tabs.observability==='trend')body=`${panel('最近评估趋势',table(['示例轮次','Recall@5','MRR','忠实度','拒答率'],[['RUN-03','0.92','0.86','0.91','0.90'],['RUN-02','0.89','0.82','0.88','0.90'],['RUN-01','0.86','0.79','0.85','0.80']].map(r=>`<tr>${r.map(v=>`<td class="mono">${v}</td>`).join('')}</tr>`)),task('eval-flywheel','演示新增评估轮次'))}<p class="field-hint">正式数据以 eval_runs 为准，展示评估集版本与模型配置，避免比较不可比的轮次。</p>`;
    if(tabs.observability==='calibration')body=`<div class="stat-strip">${stat('示例当前阈值','0.65','','当前服务配置')}${stat('示例建议阈值','0.70','','校准报告结果')}${stat('候选阈值',5,'个','下表仅演示')}${stat('配置状态','待核对','','建议值未自动应用')}</div>${panel('证据置信度阈值扫描',table(['候选阈值','错误作答率 · 示例','覆盖率 · 示例','说明'],[['0.50','12%','96%','覆盖更广'],['0.60','9%','92%',''],['0.65','7%','88%','示例当前值'],['0.70','4%','84%','示例推荐值'],['0.80','2%','68%','更多请求转人工']].map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`)),task('calibrate-confidence','演示阈值校准'))}<div class="notice section-gap">这里校准的是 RAG 证据置信度；分类器的标签阈值另在模型中心管理。原页面只展示建议与当前值，预览不会修改配置。</div>`;
    return `<div class="page admin-page">${pageHead('OBSERVABILITY','消耗、质量与阈值，一处观察。','延续原有三块报表，保留各自数据来源与缺失状态。')}${demo}${subnav('observability',[['cost','意图消耗'],['trend','评估趋势'],['calibration','置信度校准']])}${body}${sourceLine('/observability → 成本产物、eval_runs、校准报告与当前配置')}</div>`;
  }
  function topicPage() {
    const counts=topics.map(label=>({label,count:topicQuestions.filter(q=>q.labels.includes(label)).length})).sort((a,b)=>b.count-a.count);
    const questions=topicQuestions.filter(q=>ui.topic==='全部'||q.labels.includes(ui.topic));
    return `<div class="page admin-page">${pageHead('CUSTOMER INSIGHTS','客户在问什么，下一步就改善什么。','主题统计与问题明细联动，多标签问题可以归入多个主题。',task('classify-pool','演示批量归类'))}${demo}<div class="topic-layout">${panel('17 类主题 · 演示分类',`<div class="topic-list"><button data-panel-topic="全部" class="topic-button ${ui.topic==='全部'?'active':''}"><span>全部问题</span><b>${topicQuestions.length}</b></button>${counts.map(t=>`<button class="topic-button ${ui.topic===t.label?'active':''}" data-panel-topic="${t.label}"><span>${t.label}</span><div class="mini-track"><span style="width:${t.count/Math.max(...counts.map(c=>c.count))*100}%"></span></div><b>${t.count}</b></button>`).join('')}</div>`)}${panel(`${esc(ui.topic)} · 问题明细`,table(['原始问题','主题标签','示例置信度'],questions.map(q=>`<tr><td class="wide-cell">${esc(q.q)}</td><td><div class="tag-row">${q.labels.map(l=>pill(l,'neutral')).join('')}</div></td><td class="mono">${q.score.toFixed(2)}</td></tr>`)),`<span class="small muted">${questions.length} 条示例</span>`)}</div><p class="field-hint">17 类名称与顺序取自原 app/core/taxonomy.py；问题和预测分数为演示数据。正式界面从后端读取类目。</p>${sourceLine('/topics + /topics/questions → 分布图、类目筛选、问题详情；正式版保留服务端分页')}</div>`;
  }
  const gates = [
    ['语料与数据集','数据规模、标签分布、划分与泄漏检查','data','ch10-dataset'],['黄金样例检查','先确认标签边界和预标质量','overview','ch10-golden'],['训练产物','权重、分词器与阈值配置','data','ch10-train'],
    ['ONNX 与服务','导出一致性、服务在线状态','data','ch10-export'],['测试集评测','micro / macro F1 与分类红线','evaluation','ch10-eval'],['阈值扫描','验证集候选值与当前配置','evaluation','ch10-threshold-scan'],
    ['混淆矩阵','按类检查误判与漏判','evaluation','ch10-eval'],['错例复核','原问题、标准标签、预测标签','errors','ch10-eval'],['旁路批量归类','问题池处理量与执行记录','trial','classify-pool']
  ];
  function models() {
    let body='';
    if(tabs.models==='overview')body=`<div class="notice">原分类器的九项验收入口全部保留。这里没有读取训练目录或探测服务，因此统一标为“待接入”，不代表模型已训练或已通过验收。</div><div class="gate-grid">${gates.map(([title,desc,tab,id],i)=>`<section class="gate-card"><div class="between"><span class="gate-number">${String(i+1).padStart(2,'0')}</span>${pill('待接入','neutral')}</div><h3>${title}</h3><p>${desc}</p><div class="form-actions"><button class="table-actions" data-panel-tab="models:${tab}" ${tab==='overview'?'disabled':''}>${tab==='overview'?'在作业中心查看':'查看页面'}</button>${task(id,'演示运行')}</div></section>`).join('')}</div>`;
    if(tabs.models==='evaluation')body=`<div class="stat-strip">${stat('micro-F1 示例','0.93','','所有标签整体表现')}${stat('macro-F1 示例','0.90','','各类等权平均')}${stat('候选阈值 示例','0.55','','分类标签判定阈值')}${stat('数据性质','示例','','未读取真实评测报告')}</div>${panel('各类指标与容错要求',table(['类目','容错档位','示例 Precision','示例 Recall','示例 F1','验收阈值'],topics.map((name,i)=>{const f=(.96-(i%4)*.02).toFixed(2);return `<tr><td>${name}</td><td>${i<5?'严':i<13?'中':'宽'}</td><td>${f}</td><td>${f}</td><td>${f}</td><td>${i<5?'F1 ≥ 0.90':i<13?'F1 ≥ 0.80':'关注整体表现'}</td></tr>`;})),task('ch10-eval','演示评测'))}<div class="two-col section-gap">${panel('阈值扫描 · 示例',table(['标签阈值','验证集 micro-F1'],[['0.45','.90'],['0.50','.92'],['0.55','.93'],['0.60','.91']].map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`)),task('ch10-threshold-scan'))}${panel('混淆矩阵 · 示例',table(['类目','TP','FP','FN','TN'],[['退换货',18,1,1,80],['物流',17,2,1,80],['商品信息',16,1,2,81]].map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`)))}</div>`;
    if(tabs.models==='data')body=`<div class="pipeline"><div><span>01</span><b>问题池</b><small>保留来源</small></div>${icon('arrow')}<div><span>02</span><b>脱敏去重</b><small>清理并归一化</small></div>${icon('arrow')}<div><span>03</span><b>标注与增强</b><small>检查标签边界</small></div>${icon('arrow')}<div><span>04</span><b>数据划分</b><small>检测交叉泄漏</small></div></div>${panel('数据集与产物清单',table(['产物','检查内容','当前原型状态','操作'],[
      ['训练 / 验证 / 测试集','规模、标签分布、重复与交叉泄漏','ch10-dataset'],['model.safetensors','模型权重与训练配置','ch10-train'],['tokenizer.json + threshold.json','分词器与标签判定阈值','ch10-eval'],['model.onnx','导出文件与 PyTorch 预测一致性','ch10-export']
    ].map(([name,desc,id])=>`<tr><td>${name}</td><td>${desc}</td><td>${pill('未读取真实目录','neutral')}</td><td>${task(id)}</td></tr>`)))}<div class="form-actions section-gap">${task('ch10-corpus','演示准备语料')}${task('classifier-up','演示启动服务')}${task('classifier-down','演示停止服务')}</div>`;
    if(tabs.models==='errors')body=`${panel('逐条错例与边界复核',table(['示例问题','标准标签','示例预测','错误方向','操作'],[
      ['退货的运费谁出？','退换货、运费','退换货','漏判运费'],['猫砂盆坏了，保修怎么处理？','质量问题、保修维修','退换货','漏判 + 误判'],['刚买完就降价了，可以补差价吗？','价保','优惠活动','近邻类别混淆']
    ].map((r,i)=>`<tr><td class="wide-cell">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${pill(r[3],'amber')}</td><td>${button('看边界说明','model-error',i)}</td></tr>`)))}<div class="notice section-gap">一条多标签错例可能对应多笔矩阵错误。保留原页面“错例条数”和“误判/漏判笔数”的区别。</div>`;
    if(tabs.models==='trial')body=`${panel('单句试分类',`<form class="panel-pad" id="model-trial-form"><label class="field">输入问题<textarea id="model-trial-text" name="text" required maxlength="500">${esc(ui.trialText)}</textarea></label><div class="form-actions"><button class="btn primary" type="submit">${icon('spark')}预览标签样式</button>${button('查看主题明细','go','topics')}</div><p class="field-hint">仅用预设关键词演示多标签结果。正式版调用原 /api/acceptance/classify，与实时客服主链路解耦。</p><div id="trial-result" class="section-gap">${trialResult()}</div></form>`)}`;
    return `<div class="page admin-page">${pageHead('MODEL OPERATIONS','分类器管理','保留数据、训练、评测、导出与旁路归类的全部入口。',button('查看分类器作业','model-jobs'))}${demo}${subnav('models',[['overview','验收总览'],['data','数据与产物'],['evaluation','评测与阈值'],['errors','错例复核'],['trial','单句试分类']])}${body}${sourceLine('/acceptance、/acceptance/data、/acceptance/eval、/acceptance/errors')}</div>`;
  }
  function trialResult() {
    if(!ui.trialDone)return '';
    const found=[];if(/退款|退货|换货/.test(ui.trialText))found.push('退换货');if(/物流|快递|发货/.test(ui.trialText))found.push('物流');if(/运费|包邮/.test(ui.trialText))found.push('运费');if(/保修|维修/.test(ui.trialText))found.push('保修维修');
    return `<div class="preview-text"><p class="small muted">预设规则示例 · 不代表模型预测</p><div class="tag-row section-gap">${(found.length?found:['其他']).map(label=>pill(label)).join('')}</div></div>`;
  }
  function jobsPage() {
    const list=jobs.filter(j=>(ui.jobGroup==='全部'||j.group===ui.jobGroup)&&(ui.jobStatus==='全部'||j.state===ui.jobStatus));
    return `<div class="page admin-page">${pageHead('BACKGROUND JOBS','运行过程，有迹可循。','原页面上的任务入口集中在这里，业务页仍保留快捷操作。')}${demo}<div class="stat-strip">${stat('登记作业',jobs.length,'项','对应原作业白名单')}${stat('演示运行中',jobs.filter(j=>j.state==='running').length,'项','仅浏览器内的计时器')}${stat('演示已完成',jobs.filter(j=>j.state==='done').length,'项','不代表真实产物生成')}${stat('演示已停止',jobs.filter(j=>j.state==='stopped').length,'项','不影响本地进程')}</div>${panel('作业列表',`<div class="panel-toolbar">${['全部','知识','质量','观测','分类器'].map(name=>`<button class="filter-chip ${ui.jobGroup===name?'active':''}" data-panel-filter="jobGroup:${name}">${name}</button>`).join('')}<label class="compact-select">状态<select id="job-status"><option value="全部">全部</option>${[['idle','未运行'],['running','运行中'],['done','已完成'],['stopped','已停止']].map(([v,label])=>`<option value="${v}" ${ui.jobStatus===v?'selected':''}>${label}</option>`).join('')}</select></label></div>${table(['作业','分类','真实执行前置条件','演示状态','操作'],list.map(j=>`<tr><td><b>${j.name}</b><span class="table-sub mono">${j.id}</span></td><td>${j.group}</td><td class="muted">${j.needs}</td><td>${jobState(j)}</td><td><div class="row">${j.state==='running'?button('停止演示','job-stop',j.id):task(j.id,j.state==='idle'?'演示运行':'再次演示')}${button('日志','job-log',j.id)}</div></td></tr>`))}`)}${sourceLine('/api/jobs、app/core/jobs.py → 同一作业白名单；本预览不发送执行请求')}</div>`;
  }
  const mapping = [
    ['客户聊天','/','客户咨询页','client','历史会话、流式消息、引用、反馈、订单选择、工单确认、续跑','部分演示；SSE 与历史回载待接入'],
    ['后台首页','/admin','管理总览','overview','六模块读数、缺数据和异常提示','布局演示'],
    ['知识库录入','/kb','知识中心','knowledge','录入、切块、查重、来源、挖 QA、审核、双写、向量化、检索','主要交互演示；无真实切块/索引'],
    ['飞轮待审','/review','知识缺口','review','来源、频次、原问题、检索快照、审核和写回','审核状态演示'],
    ['RAG 评估','/rag-eval','RAG 质量','quality','四策略、覆盖、生成、拒答、编造个案与处置','示例报告和个案处理'],
    ['观测与成本','/observability','观测与成本','observability','意图消耗、评估趋势、置信度校准','三类示例报表'],
    ['主题分布','/topics','咨询主题','topics','17 类统计、多标签计数、样例','演示问题统计'],
    ['类目问题','/topics/questions','咨询主题 → 问题明细','topics','类目筛选、问题明细、服务端分页','筛选演示；分页待接入'],
    ['分类器验收','/acceptance','分类器 → 验收总览','models','九项验收、产物缺失、服务状态、作业入口','状态占位与任务演示'],
    ['评测详情','/acceptance/eval','分类器 → 评测与阈值','models:evaluation','P/R/F1、容错红线、阈值扫描、混淆矩阵、单句分类','示例指标与预设分类'],
    ['数据产物','/acceptance/data','分类器 → 数据与产物','models:data','语料来源、数据划分、泄漏检查、权重与 ONNX','清单布局；无目录读取'],
    ['错例复核','/acceptance/errors','分类器 → 错例复核','models:errors','标准/预测对照、错误方向、近邻边界','示例错例'],
    ['共享作业','各后台页 /api/jobs','作业中心 + 页内入口','jobs','白名单、前置条件、启动、状态与日志；停止接口','22 项浏览器内模拟']
  ];
  function migration() {
    return `<div class="page admin-page">${pageHead('FUNCTION MIGRATION','原页面的能力，一项都要有去处。','先核对功能，再迁移界面。下表明确区分已有逻辑、原型效果和待接入部分。')}${demo}<div class="migration-summary"><div><strong>12</strong><span>原有页面</span></div><div><strong>6</strong><span>原后台模块</span></div><div><strong>${jobs.length}</strong><span>已有作业定义</span></div><div><strong>0</strong><span>被替换的原项目页面</span></div></div>${panel('页面与功能对照',table(['原页面','新入口','必须保留的能力','本轮原型状态','查看'],mapping.map(([old,path,next,dest,features,stage])=>`<tr><td><b>${old}</b><span class="table-sub mono">${path}</span></td><td>${next}</td><td class="wide-cell">${features}</td><td class="wide-cell muted">${stage}</td><td><button class="table-actions" data-panel-dest="${dest}">打开 ${icon('arrow')}</button></td></tr>`)))}<div class="two-col section-gap">${panel('已经有的，按契约迁移','<div class="panel-pad"><p>保留原接口、结果字段、错误状态和历史数据来源。新页面接入后逐项核对；原路径在迁移期间仍可访问。</p></div>')}${panel('需要新建的，单独交付','<div class="panel-pad"><p>真实登录权限、人工认领、可靠人工收发、工单负责人和处理流、发布版本、真实商家接入，按后端计划补建。</p></div>')}</div><div class="notice section-gap">完整迁移检查表保存在同目录 LEGACY_PAGE_MAP.md。页面入口可见不等于后端迁移完成，也不等于模型通过验收。</div></div>`;
  }
  function candidateModal(id) {
    const r=candidates.find(r=>r.id===Number(id));if(!r)return;
    modal('复核候选问答',`<div class="between">${status(r.state)}<span class="small muted">${r.batch}</span></div><h3 class="section-gap">${esc(r.q)}</h3><p class="field-hint">来源：${esc(r.source)}</p>${r.state==='pending'?`<form id="candidate-form" data-record="${r.id}"><label class="field section-gap">可复用的答案<textarea name="answer" required maxlength="2000">${esc(r.a)}</textarea></label><p class="field-hint">采纳后演示写入知识内容，保留来源与批次。</p></form>`:`<div class="preview-text section-gap">${esc(r.a)}</div><p class="field-hint">${esc(r.reason||'已采纳到演示知识内容')}</p>`}`,`<button class="btn" data-action="modal-close">关闭</button>${r.state==='pending'?`${button('弃用','candidate-reject',id)}<button class="btn primary" type="submit" form="candidate-form">采纳并写回</button>`:''}`);
  }
  function gapModal(id) {
    const r=gaps.find(r=>r.id===Number(id));if(!r)return;
    modal('知识缺口 · 证据与审核',`<div class="between">${status(r.state)}<span class="small muted">${r.source} · 出现 ${r.count} 次</span></div><h3 class="section-gap">${esc(r.q)}</h3><p class="muted small">${esc(r.reason)}</p><h3 class="section-gap">当时检索到了什么</h3>${table(['来源','示例得分','缺失内容'],r.snapshot.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`))}${r.state==='pending'?`<form id="gap-form" data-record="${r.id}"><label class="field section-gap">经人工确认的答案<textarea name="answer" required maxlength="2000" placeholder="填写核对过的答案，避免引入未经确认的承诺"></textarea></label></form>`:`<div class="preview-text section-gap">${esc(r.answer||r.reason)}</div>`}`,`<button class="btn" data-action="modal-close">关闭</button>${r.state==='pending'?`${button('驳回','gap-reject',id)}<button class="btn primary" type="submit" form="gap-form">通过并写回知识</button>`:''}`);
  }
  function caseModal(id) {
    const c=cases.find(c=>c.id===id);if(!c)return;
    modal('质量个案复核',`<div class="between"><span class="mono">${c.id}</span>${status(c.state)}</div><h3 class="section-gap">${esc(c.q)}</h3><div class="evidence-pair"><section><span class="small muted">原回答</span><p>${esc(c.answer)}</p></section><section><span class="small muted">引用证据</span><p>${esc(c.evidence)}</p></section></div><div class="notice amber">${esc(c.reason)}</div><form id="case-form" data-record="${c.id}"><label class="field">处理结论<select name="status"><option value="resolved" ${c.state==='resolved'?'selected':''}>已解决</option><option value="dismissed" ${c.state==='dismissed'?'selected':''}>无需处理</option><option value="pending" ${c.state==='pending'?'selected':''}>未解决</option></select></label><label class="field">处理说明<textarea name="note" required maxlength="1000" placeholder="说明修正了什么，或为何无需处理">${esc(c.note)}</textarea></label></form>`,`<button class="btn" data-action="modal-close">取消</button><button class="btn primary" form="case-form" type="submit">保存处理记录</button>`);
  }
  function jobConfirm(id) {
    const j=jobs.find(j=>j.id===id);if(!j)return;
    modal(`演示任务 · ${j.name}`,`<div class="notice">这里只演示任务状态和日志，不启动进程，不调用模型，不修改原数据库或文件。</div><div class="detail-row"><span>作业标识</span><span class="mono">${j.id}</span></div><p class="section-gap small muted">正式执行的前置条件：${j.needs}</p>${id==='kb-reset'?'<div class="notice amber section-gap">真实“清库重建”会删除知识数据，应放入管理员维护区并进行单独确认。本次仅演示，原数据不受影响。</div>':''}`,`<button class="btn" data-action="modal-close">取消</button>${button('开始演示','job-start',j.id,'primary')}`);
  }
  function jobLog(id) {
    const j=jobs.find(j=>j.id===id);if(!j)return;
    modal(`作业日志 · ${j.name}`,`<div class="between"><span class="mono small">${j.id}</span>${jobState(j)}</div><pre class="task-log">${esc(j.logs.join('\n')||'尚未运行演示。\n此处会展示启动、运行、完成或停止记录。')}</pre><p class="field-hint">预设演示日志；正式日志来自 /api/jobs/{name}。</p>`,`<button class="btn" data-action="modal-close">关闭</button>${j.state==='running'?button('停止演示','job-stop',id):button('刷新日志','job-log',id)}`);
  }
  function startJob(id) {
    const j=jobs.find(j=>j.id===id);if(!j||j.state==='running')return;
    j.state='running';j.logs=['[DEMO] 收到任务请求：'+j.id,'[DEMO] 状态变为 running；未启动真实进程。'];
    $('#modal').close();render();toast('演示已开始，可在作业中心查看或停止');
    j.timer=setTimeout(()=>{j.state='done';j.logs.push('[DEMO] 状态变为 done。','[DEMO] 未调用真实服务，也未生成真实评估或模型产物。');if(j.id==='kb-vectorize'){indexRows.forEach(r=>{r.state='done';});j.logs.push('[DEMO] 演示索引行已同步。');}render();toast(`${j.name}：演示完成`);},5000);
  }
  function addKnowledge(title,text,category) {
    const id=Math.max(...docs.map(d=>d.id))+1;docs.unshift({id,title,text,category,scope:'全部商品',status:'published',version:'v1.0',date:'09-22 演示'});indexRows.push({doc:id,blocks:1,state:'done',version:'v1.0'});
  }
  function onClick(el) {
    if(el.dataset.panelTab){const [section,id]=el.dataset.panelTab.split(':');tabs[section]=id;render();return true;}
    if(el.dataset.panelFilter){const [key,val]=el.dataset.panelFilter.split(':');ui[key]=val;render();return true;}
    if(el.dataset.panelTopic){ui.topic=el.dataset.panelTopic;render();return true;}
    if(el.dataset.panelDest){const [page,tab]=el.dataset.panelDest.split(':');if(page==='client'){h.state.surface='client';$('#modal').close();render();}else{if(tab)tabs[page]=tab;go(page);}return true;}
    const a=el.dataset.panelAction,id=el.dataset.panelId;if(!a)return false;
    if(a==='go')go(id);
    if(a==='import-sample'||a==='source-load'){ui.importText=id?`## ${id.replace(/\.md$/,'')}\n这是一段来源材料示例，请编辑后进行切块预览。\n\n## 使用范围\n确认政策适用范围和版本后，再保存为草稿。`:'## 退货包装要求\n商品未使用且配件齐全时，可先提交退货申请。\n\n## 包装已拆封\n请提供包装现状说明，由客服确认是否影响寄回和验收。';ui.chunks=[];render();}
    if(a==='chunks-save'){if(!ui.chunks.length){toast('请先预览切块');return true;}const title=ui.chunks[0].split('\n')[0].replace(/^#+\s*/,'').slice(0,80);const docId=Math.max(...docs.map(d=>d.id))+1;docs.unshift({id:docId,title,text:ui.importText,category:'手工录入',scope:'全部商品',status:'draft',version:'v0.1',date:'09-22 演示'});indexRows.push({doc:docId,blocks:ui.chunks.length,state:'pending',version:'v0.1 草稿'});ui.chunks=[];tabs.knowledge='content';h.state.docFilter='all';h.state.docSearch='';render();toast('已保存演示草稿，尚未审核和发布');}
    if(a==='candidate')candidateModal(id);
    if(a==='gap')gapModal(id);
    if(a==='candidate-reject'||a==='gap-reject')modal('记录驳回原因',`<form id="reject-form" data-kind="${a}" data-record="${id}"><label class="field">原因<textarea name="reason" required maxlength="800" placeholder="例如：仅适用于个别订单，无法作为通用知识"></textarea></label></form>`,'<button class="btn" data-action="modal-close">取消</button><button class="btn primary" form="reject-form" type="submit">确认驳回</button>');
    if(a==='case')caseModal(id);
    if(a==='job-confirm')jobConfirm(id);
    if(a==='job-start')startJob(id);
    if(a==='job-log')jobLog(id);
    if(a==='job-stop'){const j=jobs.find(j=>j.id===id);if(j?.state==='running'){clearTimeout(j.timer);j.state='stopped';j.logs.push('[DEMO] 用户停止演示；未操作系统进程。');$('#modal').close();render();toast('已停止演示任务');}}
    if(a==='model-jobs'){ui.jobGroup='分类器';go('jobs');}
    if(a==='model-error'){const notes=['退换货处理退货、换货和退款流程；运费处理费用承担与运费险，可同时出现。','商品本身故障归质量问题；保修或修理诉求归保修维修，不能自动替换成退换货。','价保是购买后降价补差；优惠活动是优惠券和活动使用。'];modal('类目边界说明',`<div class="notice">取自原 taxonomy 的边界语义</div><p>${notes[Number(id)]}</p>`);}
    return true;
  }
  function onInput(el) {
    if(el.id==='import-text'){ui.importText=el.value;ui.chunks=[];$('#chunk-preview').innerHTML=chunkPreview();}
    if(el.id==='import-type'){ui.importType=el.value;ui.chunks=[];$('#chunk-preview').innerHTML=chunkPreview();}
    if(el.id==='retrieval-query')ui.searchQuery=el.value;
    if(el.id==='retrieval-strategy')ui.searchStrategy=el.value;
    if(el.id==='model-trial-text')ui.trialText=el.value;
    if(el.id==='job-status'){ui.jobStatus=el.value;render();}
  }
  function onSubmit(event) {
    const form=event.target;if(!['chunk-form','search-test-form','candidate-form','gap-form','reject-form','case-form','model-trial-form'].includes(form.id))return false;
    event.preventDefault();const data=new FormData(form);const record=Number(form.dataset.record);
    if(form.id==='chunk-form'){ui.importText=$('#import-text').value;ui.importType=$('#import-type').value;if(!ui.importText.trim()){toast('请填写正文');return true;}ui.chunks=ui.importText.trim().split(/\n\s*\n/).filter(Boolean);$('#chunk-preview').innerHTML=chunkPreview();}
    if(form.id==='search-test-form'){ui.searchQuery=String(data.get('q')).trim();ui.searchStrategy=String(data.get('strategy'));if(!ui.searchQuery){toast('请输入问题');return true;}ui.searchDone=true;$('#retrieval-results').innerHTML=retrievalResults();}
    if(form.id==='candidate-form'||form.id==='gap-form'){const answer=String(data.get('answer')).trim();if(!answer){toast('请填写经确认的答案');return true;}const r=(form.id==='candidate-form'?candidates:gaps).find(r=>r.id===record);if(!r||r.state!=='pending')return true;r.state='approved';r.answer=answer;if(form.id==='candidate-form')r.a=answer;addKnowledge(r.q,answer,form.id==='candidate-form'?'历史对话':'知识缺口补充');$('#modal').close();render();toast('演示审核通过，已写入知识内容');}
    if(form.id==='reject-form'){const reason=String(data.get('reason')).trim();if(!reason){toast('请填写原因');return true;}const r=(form.dataset.kind==='candidate-reject'?candidates:gaps).find(r=>r.id===record);if(r&&r.state==='pending'){r.state='rejected';r.reason=reason;}$('#modal').close();render();toast('已记录演示审核结论');}
    if(form.id==='case-form'){const c=cases.find(c=>c.id===form.dataset.record);const note=String(data.get('note')).trim();if(!note){toast('请填写处理说明');return true;}c.state=String(data.get('status'));c.note=note;$('#modal').close();render();toast('演示处理记录已保存');}
    if(form.id==='model-trial-form'){ui.trialText=String(data.get('text')).trim();if(!ui.trialText){toast('请输入问题');return true;}ui.trialDone=true;$('#trial-result').innerHTML=trialResult();}
    return true;
  }
  function addFeedback(question) {
    const known=gaps.find(g=>g.q===question);if(known){known.count++;return;}gaps.push({id:Math.max(0,...gaps.map(g=>g.id))+1,q:question,count:1,source:'用户反馈未解决',state:'pending',reason:'来自客户咨询页的演示反馈。',snapshot:[['退换货与售后政策','示例','正式版需要按回答关联真实检索快照']]});
  }
  const views={overview,knowledge,review,quality,observability,topics:topicPage,models,jobs:jobsPage,migration};
  function markPublished(id) {const row=indexRows.find(r=>r.doc===id);if(row){row.state='done';row.version='v1.0';}else indexRows.push({doc:id,blocks:1,state:'done',version:'v1.0'});}
  const pagePlans=Object.fromEntries(Object.keys(views).map(id=>[id,{name:titles[id],icon:({overview:'chart',knowledge:'book',review:'search',quality:'shield',observability:'chart',topics:'chat',models:'spark',jobs:'clock',migration:'file'})[id],stage:'本轮可体验',text:({overview:'承接原六模块，汇总待办与状态。',knowledge:'内容、录入切块、候选问答、索引状态、检索自测。',review:'知识缺口、问题来源与检索快照、人工审核写回。',quality:'四策略、生成与拒答评估、编造个案台账。',observability:'意图消耗、评估趋势、证据置信度校准。',topics:'原有 17 类名称、演示分布与明细联动。',models:'九项验收、数据产物、评测阈值、错例与单句分类。',jobs:'原白名单中的 22 项作业，浏览器内模拟运行。',migration:'原 12 页面与共享作业逐项对应；列明演示和待接入边界。'})[id]}]));
  return {hasPage:page=>Object.hasOwn(titles,page),title:page=>titles[page],renderPage:page=>views[page](),pendingReviews:()=>gaps.filter(g=>g.state==='pending').length,onClick,onInput,onSubmit,pagePlans,addFeedback,markPublished};
};
