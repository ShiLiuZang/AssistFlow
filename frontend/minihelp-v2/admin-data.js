/* V2 data-display draft. Samples are explicit; live mode uses the current project's API. */
window.createMinihelpDataPanels = function(h) {
  'use strict';
  const {esc,icon,pill:basePill,stat,modal,toast,render,go} = h;
  const pill = (label,color='') => basePill(esc(label),color);
  const typeNames = {faq:'商品问答',policy:'政策条款',manual:'售后手册',spec:'商品规格',mined:'对话提取'};
  const pageNames = {overview:'管理总览',knowledge:'知识中心',review:'知识缺口',jobs:'作业中心',quality:'RAG 质量',observability:'观测与成本',topics:'咨询主题',models:'分类器管理'};
  const tabs = [['content','知识内容'],['materials','建库材料'],['import','录入与切块'],['mining','候选问答'],['index','索引状态'],['search','检索自测']];
  const exampleText = '# 退换货政策\n\n## 申请条件\n签收后 7 天内可申请退货。商品需未使用，配件齐全。\n\n## 包装要求\n拆开外包装不直接等同于商品已使用，应由客服核对包装现状。';
  const sampleChunks = [
    [108,'退货需要保留哪些配件？','请保留产品主机、说明书及全部配件。','policy','售后政策','退换货 / 配件完整性','pending',true],
    [107,'饮水机滤芯多久更换？','根据使用频率和水质，建议每 2–4 周检查并更换滤芯。','faq','商品问答','饮水机 / 滤芯更换','done',false],
    [106,'物流超过 48 小时没有更新怎么办？','联系人工客服核查运输状态，记录最近一次物流信息。','manual','物流服务','售后手册 / 物流异常','done',false],
    [105,'智能猫砂盆的适用尺寸','选购前请核对机身尺寸、摆放空间及宠物体型。','spec','商品规格','猫砂盆 / 尺寸规格','pending',false],
    [104,'拆开外包装是否影响退货？','拆开外包装不直接等同于商品已使用，应由客服核对包装现状。','policy','售后政策','退换货 / 包装要求','done',true],
    [103,'常规现货多久发货？','常规现货商品付款后 48 小时内发出，预售以商品说明为准。','faq','物流服务','配送 / 发货时效','done',false],
    [102,'退货申请期限','签收后 7 天内可申请退货，具体条件需结合订单与商品状态核对。','policy','售后政策','退换货 / 申请条件','done',true],
    [101,'活动订单与特殊商品','特殊商品与活动订单以订单约定及可信材料为准。','policy','售后政策','退换货 / 特殊规则','pending',false]
  ].map(([id,questions,answer,content_type,category,section_path,status,is_key_clause])=>({id,questions,answer,content_type,category,section_path,status,is_key_clause,created_at:null}));
  const sampleCandidates = {
    stats:{total:6,batches:2,latest_batch:'展示批次 B',counts:{extracted:1,kept:2,discarded:1,approved:1,rejected:1}},
    rows:{
      kept:[{id:21,question:'拆开外包装后，还能申请退货吗？',answer:'需核对商品使用情况与配件完整性，拆封外包装本身不能直接判断退货资格。',source_ref:'returns-policy.md',batch_no:'展示批次 B'}, {id:20,question:'物流不更新时应该如何处理？',answer:'联系人工客服核查最近一次物流记录和承运状态。',source_ref:'after-sales-manual.md',batch_no:'展示批次 B'}],
      extracted:[{id:19,question:'首次使用饮水机有什么注意事项？',answer:'阅读说明书并确认电源、水位及摆放位置。',source_ref:'product-faq.md',batch_no:'展示批次 A'}],
      discarded:[{id:18,question:'现货什么时候发出？',answer:'已有相同内容，本条在去重时丢弃。',source_ref:'billing-shipping.md',batch_no:'展示批次 A'}],
      approved:[{id:17,question:'退货要保留配件吗？',answer:'保留全部配件，核对退货材料要求。',source_ref:'returns-policy.md',batch_no:'展示批次 A'}],
      rejected:[{id:16,question:'我的订单能马上退款吗？',answer:'仅适用于单笔订单，不能作为通用知识。',source_ref:null,batch_no:'展示批次 A'}]
    }
  };
  sampleChunks[0].answer+='\n\n核对清单\n1. 对照商品说明核对主机、说明书和随机配件，记录缺失项目。\n2. 核对配件数量、外观和包装现状；实际条件需以订单对应的可信政策为准。\n3. 对无法确认的配件，请先联系人工客服，提供商品名称与配件照片。\n\n处理说明\n这段正文用于展示长内容的阅读效果。展示样例中的政策、期限与处理步骤不作为实际售后承诺。完整内容应保留适用范围、限制条件和需要人工核查的事项，避免仅凭列表摘要决定退货资格。';
  const ui = {mode:location.pathname.startsWith('/v2/')?'live':'sample',scenario:'normal',tab:'content',filter:'all',type:'all',query:'',queryDraft:'',page:1,size:20,candidate:'kept',text:location.pathname.startsWith('/v2/')?'':exampleText,importType:'policy',preview:null,previewError:'',previewBusy:false,previewVersion:0,ingestBusy:false,ingestResult:null,ingestError:null,searchQuery:'拆开外包装后还能退货吗？',strategy:'hybrid',hits:null,searchError:'',searchBusy:false,cache:{},epoch:0};
  let confirmedInput=null;
  Object.assign(ui,{vectorChecking:false,vectorStarting:false,vectorReading:false,vectorNotice:'',vectorStartUnknown:false});
  const vectorJobPath='/api/jobs/kb-vectorize';
  const vectorLabels={idle:'本次服务未运行',running:'运行中',ok:'进程执行完成',failed:'进程执行失败',stopped:'已停止'};
  let vectorPollTimer=null,confirmedVector=false;
  const operationBusy=()=>ui.ingestBusy||ui.vectorChecking||ui.vectorStarting||ui.actionBusy||ui.classifyBusy;
  const number = value => value == null ? '—' : esc(value);
  const metric = (label,value,unit,foot) => stat(esc(label),number(value),unit,esc(foot));
  const button = (label,action,extra='',cls='') => `<button class="btn ${cls}" data-data-action="${action}" ${extra}>${label}</button>`;
  const panel = (title,body,extra='') => `<section class="panel"><div class="panel-head"><h2>${title}</h2>${extra}</div>${body}</section>`;
  const table = (heads,rows) => `<div class="table-wrap"><table><thead><tr>${heads.map(head=>`<th>${head}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${heads.length}"><div class="empty">没有符合条件的记录</div></td></tr>`}</tbody></table></div>`;
  const type = value => typeNames[value] || value || '未标注';
  const stamp = value => value ? esc(value.replace('T',' ')) : '—';
  const listStamp = value => value ? esc(value.replace('T',' ').slice(5,16)) : '—';
  const vectorState = value => pill(value==='done'?'已向量化':value==='pending'?'待向量化':value||'未知',value==='pending'?'amber':value==='done'?'':'neutral');
  const moduleState = value => pill(({ok:'正常',attention:'需关注',missing:'尚无数据',error:'读取失败'})[value]||'未知',({ok:'',attention:'amber',missing:'neutral',error:'red'})[value]||'neutral');

  function sampleKnowledge() {
    const rows=ui.scenario==='empty'?[]:[...workflows.publishedChunks(),...sampleChunks];
    const byType={}; rows.forEach(row=>{byType[row.content_type]=(byType[row.content_type]||0)+1;});
    const unavailable=ui.scenario==='error', offline=ui.scenario==='offline';
    const chunks=unavailable?{total:null,done:null,pending:null,key_clause:null,by_content_type:{}}:{total:rows.length,done:rows.filter(row=>row.status==='done').length,pending:rows.filter(row=>row.status==='pending').length,key_clause:rows.filter(row=>row.is_key_clause).length,by_content_type:byType};
    return {chunks,recent:unavailable?[]:rows,staging:sampleCandidates.stats,db_error:unavailable?'展示状态：库存数据库读取失败':null,milvus:{online:!offline,count:offline?null:rows.filter(row=>row.status==='done').length,collection:'knowledge'},consistent:unavailable||offline?null:chunks.pending===0,sources:[['product-faq.md','faq'],['returns-policy.md','policy'],['after-sales-manual.md','manual'],['product-specs.md','spec'],['member-benefits.md','policy'],['billing-shipping.md','policy']].map(([file,content_type])=>({file,content_type,present:true,path:`data/kb/${file}`})),content_types:Object.entries(typeNames).filter(([key])=>key!=='mined').map(([key,desc])=>({key,desc})),jobs:[]};
  }
  function sampleOverview() {
    const kb=sampleKnowledge();
    const reviews=workflows.reviewCounts(), reviewUnknown=reviews.pending==null, reviewTotal=Object.values(reviews).reduce((sum,value)=>sum+(value||0),0);
    return {modules:[
      {key:'kb',title:'知识中心',status:kb.db_error?'error':kb.consistent?'ok':'attention',headline:kb.db_error?'库存读数暂时不可用':!kb.milvus.online?'原文已保存，向量库暂时离线':kb.chunks.pending?'有知识块等待补齐向量':'知识块与向量数量一致',metrics:[{label:'知识块',value:kb.chunks.total},{label:'待向量化',value:kb.chunks.pending},{label:'Milvus',value:kb.milvus.online?kb.milvus.count:'离线'}],note:'数量检查与检索质量分别判断。'},
      {key:'review',title:'知识缺口',status:reviewUnknown?'error':!reviewTotal?'missing':reviews.pending||reviews.publishing?'attention':'ok',headline:reviewUnknown?'审核读数暂时不可用':!reviewTotal?'尚无知识缺口审核记录':reviews.pending||reviews.publishing?`${reviews.pending} 条待审，${reviews.publishing} 条待完成发布`:'当前没有待审或发布中的记录',metrics:[{label:'待审',value:reviews.pending},{label:'发布中',value:reviews.publishing},{label:'已通过',value:reviews.approved},{label:'已驳回',value:reviews.rejected}],note:'候选问答与知识缺口分别管理。'},
      ...reports.overviewModules(),
      ...classification.overviewModules()
    ]};
  }
  async function request(path,body) {
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
    try {
      const response=await fetch(path,{signal:controller.signal,cache:'no-store',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});
      if(response.status===404&&!location.pathname.startsWith('/v2/'))throw new Error('当前地址是静态展示服务。请从后端 /v2/ 入口打开实时数据。');
      if(response.status>=500)throw new Error(response.status===503?'后台数据服务暂不可用，请检查服务后重新读取。':'后台读取失败，请检查数据服务后重试。');
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('服务没有返回可读取的数据。');
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`请求失败（HTTP ${response.status}）`);
      return data;
    } catch(error) {
      if(error.name==='AbortError')throw new Error('服务响应超时，请重试。');
      if(error instanceof TypeError)throw new Error('无法连接后台服务。');
      throw error;
    } finally {clearTimeout(timer);}
  }
  function resource(key,pathOverride) {
    if(ui.mode==='sample'&&classification.hasResource(key))return classification.sampleResource(key);
    if(ui.mode==='sample'&&reports.hasResource(key))return reports.sampleResource(key);
    if(ui.mode==='sample'&&workflows.hasResource(key))return workflows.sampleResource(key);
    if(ui.mode==='sample') {
      if(key==='staging'&&ui.scenario==='error')return {status:'error',error:'展示状态：候选队列读取失败。'};
      const candidates=ui.scenario==='empty'?{stats:{total:0,batches:0,counts:Object.fromEntries(Object.keys(sampleCandidates.rows).map(key=>[key,0]))},rows:{},limit:30}:sampleCandidates;
      return {status:'ready',data:key==='kb'?sampleKnowledge():key==='admin'?sampleOverview():candidates,time:null};
    }
    if(!ui.cache[key]) {
      ui.cache[key]={status:'loading'};
      const epoch=ui.epoch, path=pathOverride||({kb:'/api/kb/overview',admin:'/api/admin/overview',staging:'/api/kb/staging',...workflows.paths,...reports.paths,...classification.paths})[key];
      request(path).then(data=>{if(epoch===ui.epoch)ui.cache[key]={status:'ready',data,time:new Date().toLocaleTimeString('zh-CN')};}).catch(error=>{if(epoch===ui.epoch)ui.cache[key]={status:'error',error:error.message};}).finally(()=>{if(epoch===ui.epoch&&h.state.surface==='admin'&&Object.hasOwn(pageNames,h.state.page))render();});
    }
    return ui.cache[key];
  }
  function scenarioOptions() {
    const page=h.state.page;
    if(reports.hasPage(page))return reports.scenarioOptions(page);
    if(classification.hasPage(page))return classification.scenarioOptions(page);
    return [['normal',page==='jobs'?'运行状态样例':page==='review'?'完整审核队列':'正常库存'],['empty',page==='jobs'?'尚无运行记录':page==='review'?'暂无审核记录':'空库存'],['offline',page==='jobs'?'依赖不可用':page==='review'?'待发布与恢复':'向量库离线'],['error',page==='knowledge'?'库存读取失败':'读取失败']];
  }
  function sourceBar() {
    return `<div class="data-source-bar"><div><span class="dot ${ui.mode==='sample'?'amber':''}"></span><strong>${ui.mode==='sample'?'展示样例':h.state.page==='observability'?'实时接口 · 只读':'实时接口'}</strong><span>${ui.mode==='sample'?'用于查看字段、布局和异常状态，读数均为样例。':h.state.page==='knowledge'?'库存来自真实接口；原文录入、候选审核与向量补齐均需确认。':'读取当前项目后端，库存、报告和服务状态分别查询。'}</span></div><div class="data-source-actions"><div class="data-mode-switch" role="group" aria-label="数据来源"><button data-data-mode="sample" ${operationBusy()?'disabled':''} aria-pressed="${ui.mode==='sample'}" class="${ui.mode==='sample'?'active':''}">展示样例</button><button data-data-mode="live" ${operationBusy()?'disabled':''} aria-pressed="${ui.mode==='live'}" class="${ui.mode==='live'?'active':''}">实时数据</button></div>${ui.mode==='sample'?`<label class="data-scenario-label">展示状态<select aria-label="展示状态" id="data-scenario">${scenarioOptions().map(([value,label])=>`<option value="${value}" ${ui.scenario===value?'selected':''}>${label}</option>`).join('')}</select></label>`:''}</div></div>`;
  }
  function emptyState(title,desc,loading=false) {
    return `<div class="data-empty-state" ${loading?'role="status"':''}>${icon(loading?'clock':'info')}<h2>${esc(title)}</h2><p>${esc(desc)}</p>${!loading?button('重新读取','refresh'):''}${ui.mode==='live'&&!location.pathname.startsWith('/v2/')?`<a class="btn soft" href="http://127.0.0.1:8000/v2/#/${h.state.page}">打开后端页面 ${icon('arrow')}</a>`:''}</div>`;
  }
  function loadingOrError(value) {
    return value.status==='loading'?emptyState('正在读取后台数据','库存、报告和列表将使用真实接口返回值。',true):value.status==='error'?emptyState('暂时无法读取数据',value.error):null;
  }
  function header(page) {
    const desc={knowledge:'维护回复依据，核对原文、审核与向量状态。',overview:'查看知识、质量与模型的当前状态，找到下一件需要处理的事。',review:'从未解决的问题出发，核对依据，再确认可复用的答案。',jobs:'查看执行条件、运行状态与日志，回到业务页核对结果。',quality:'看策略、看逐题证据，分清检索结果与生成判断。',observability:'核对调用消耗、可比较评测与证据阈值。',topics:'看清问题分布，按权威类目核对完整问法与归类依据。',models:'核对数据、评测与产物，分别判断验收结果和服务状态。'};
    const primary=page==='knowledge'?button('建库材料','materials','','soft')+button(`${icon('plus')}录入内容`,'import','','primary'):page==='review'?`${ui.mode==='live'?'<button class="btn soft" data-wf-action="process-live">生成待审建议</button>':''}<button class="btn primary" data-wf-action="review-next">核对下一条</button>`:page==='jobs'?'<button class="btn soft" data-wf-action="job-guide">查看运行流程</button>':reports.hasPage(page)?'<button class="btn soft" data-report-action="guide">报告运行说明</button>':classification.hasPage(page)?'<button class="btn soft" data-cls-action="guide">查看查询范围</button>':button('打开知识中心','knowledge','','primary');
    return `<div class="page-title between"><div><div class="eyebrow">${page==='knowledge'?'KNOWLEDGE OPERATIONS':page==='review'?'KNOWLEDGE REVIEW':page==='jobs'?'BACKGROUND OPERATIONS':page==='quality'?'RAG QUALITY':page==='observability'?'OBSERVABILITY':page==='topics'?'CONSULTATION TOPICS':page==='models'?'CLASSIFIER MANAGEMENT':'SERVICE OPERATIONS'}</div><h1>${pageNames[page]}</h1><p>${desc[page]}</p></div><div class="page-actions">${button(`${icon('clock')}刷新读数`,'refresh',operationBusy()?'disabled':'')}${primary}</div></div>`;
  }
  function knowledgeMetrics(data) {
    const s=data.chunks||{},v=data.milvus||{},consistent=data.consistent;
    const verdict=consistent===true?'一致':consistent===false?'对不上':'未知';
    const note=consistent===true?'数量一致不代表检索合格':consistent===false?'有待补块或两端数量不同':data.db_error?'原文统计不可读，暂不下结论':v.online===false?'向量库离线，暂不下结论':'数量读数未知，暂不下结论';
    return `<div class="stat-strip data-metrics data-knowledge-metrics" role="group" aria-label="知识库存统计" data-consistency="${consistent===true?'consistent':consistent===false?'mismatch':'unknown'}">${metric('知识块总数',s.total,'块','数据库原文记录（MySQL）')}${metric('已向量化',s.done,'块','MySQL 中标记已向量化')}${metric('待向量化',s.pending,'块','保留原文，等待补齐')}${metric('关键条款',s.key_clause,'块','需完整保留的约束')}${metric('Milvus 条数',v.online===true?v.count:v.online===false?'离线':null,v.online===true&&v.count!=null?'条':'',v.online===true?'向量库实际记录数':v.online===false?'向量库连接不可用':'向量库状态未知')}${metric('双写核对',verdict,'',note)}</div>`;
  }
  function inventoryResource() {
    const params=new URLSearchParams({page:ui.page,size:ui.size});
    if(ui.query)params.set('q',ui.query);
    if(ui.filter!=='all')params.set('status',ui.filter);
    if(ui.type!=='all')params.set('content_type',ui.type);
    if(ui.mode==='live')return resource('chunks:'+params,'/api/kb/chunks?'+params);
    if(ui.scenario==='error')return {status:'error',error:'展示状态：知识库存读取失败，无法确认记录数。'};
    const rows=sampleKnowledge().recent.filter(row=>(ui.filter==='all'||row.status===ui.filter)&&(ui.type==='all'||(ui.type==='unmarked'?!row.content_type:row.content_type===ui.type))&&`${row.questions||''} ${row.answer||''} ${row.section_path||''} ${row.category||''}`.toLowerCase().includes(ui.query.toLowerCase())).sort((a,b)=>b.id-a.id);
    const pages=Math.max(1,Math.ceil(rows.length/ui.size)),page=Math.min(ui.page,pages);
    return {status:'ready',data:{items:rows.slice((page-1)*ui.size,page*ui.size).map(row=>({...row,answer:row.answer.slice(0,160),answer_chars:row.answer.length})),total:rows.length,page,size:ui.size,pages},time:null};
  }
  function chunkRows(data) {
    return (data.items||[]).map(row=>`<tr><td class="mono muted">#${esc(row.id)}</td><td class="data-content-cell"><strong>${esc(row.questions||row.section_path||'未标注问法')}</strong><p class="data-answer-preview">${esc(row.answer)}</p><span class="table-sub">${esc(row.section_path||'未标注章节')}${row.is_key_clause?' · 关键条款':''}</span></td><td>${esc(type(row.content_type))}<span class="table-sub">${esc(row.category||'未标注分类')}</span></td><td>${vectorState(row.status)}</td><td class="data-time-cell">${listStamp(row.created_at)}</td><td><button class="table-actions" data-data-action="chunk" data-id="${esc(row.id)}">查看全文 ${icon('arrow')}</button></td></tr>`);
  }
  function contentPage(data) {
    const value=inventoryResource(),list=value.data;
    if(list)ui.page=list.page;
    const toolbar=`<div class="panel-toolbar data-toolbar"><div class="data-filters">${[['all','全部'],['done','已向量化'],['pending','待向量化']].map(([value,label])=>`<button class="filter-chip ${ui.filter===value?'active':''}" data-data-filter="${value}" aria-pressed="${ui.filter===value}">${label}</button>`).join('')}</div><div class="data-table-tools"><select id="data-type" aria-label="筛选内容类型"><option value="all">全部类型</option>${[...Object.keys(typeNames),'unmarked'].map(key=>`<option value="${key}" ${ui.type===key?'selected':''}>${esc(key==='unmarked'?'未标注':type(key))}</option>`).join('')}</select><form id="data-inventory-form" class="data-inventory-search"><label class="search">${icon('search')}<input id="data-query" maxlength="200" aria-label="搜索全库知识" placeholder="搜索问法、正文或章节" value="${esc(ui.queryDraft)}"></label><button class="btn soft" type="submit">搜索</button>${ui.query||ui.queryDraft?button('清除','clear-query','','text-btn'):''}</form></div></div>`;
    const rows=list?`<div class="table-wrap"><table class="data-chunk-table"><thead><tr>${['ID','问法与答案摘要','类型 / 分类','向量状态','录入时间','操作'].map(value=>`<th>${value}</th>`).join('')}</tr></thead><tbody id="data-chunk-rows">${chunkRows(list).join('')||'<tr><td colspan="6"><div class="empty">'+(ui.query||ui.filter!=='all'||ui.type!=='all'?'全库中没有符合条件的知识块':'尚无知识块，可先预览材料')+'</div></td></tr>'}</tbody></table></div>`:`<div class="panel-pad">${loadingOrError(value)}</div>`;
    const footer=`<div class="data-table-footer data-inventory-footer"><span>${list?`筛选结果 ${number(list.total)} 块${list.total?` · 本页 ${(list.page-1)*list.size+1}–${(list.page-1)*list.size+list.items.length}`:''}`:'筛选结果 —'}${ui.query?` · 搜索「${esc(ui.query)}」`:''}<small>统计卡为全库总数；搜索范围包含完整正文。</small></span><div class="data-pagination"><label>每页<select id="data-size" aria-label="知识列表每页条数">${[5,10,20,50].map(size=>`<option ${ui.size===size?'selected':''}>${size}</option>`).join('')}</select>块</label>${button('上一页','chunk-page',`data-page="${list?list.page-1:1}" ${!list||list.page<=1?'disabled':''}`)}<span>${list?`${list.page} / ${list.pages}`:'— / —'}</span>${button('下一页','chunk-page',`data-page="${list?list.page+1:1}" ${!list||list.page>=list.pages?'disabled':''}`)}</div></div>`;
    return `${knowledgeMetrics(data)}${data.db_error?'<div class="notice data-alert" role="alert">库存统计暂不可读取，未知值显示为 —；列表单独查询。</div>':''}${panel('知识内容',toolbar+rows+footer,pill(ui.mode==='sample'?'样例库存':'全库查询','neutral'))}`;
  }
  function importPage(data) {
    return `${ingestResultView()}<div class="data-import-steps" aria-label="录入流程"><span>01 填写原文</span>${icon('arrow')}<span>02 预览与查重</span>${icon('arrow')}<span>03 核对后入库</span></div><div class="data-material-entry"><span>已有源文件？在建库材料中查看清单与切块。</span>${button('查看建库材料','materials','','soft')}</div><div class="split-panels data-import-panels">${panel('录入内容',`<form id="data-preview-form" class="panel-pad"><label class="field">内容类型<select id="data-import-type" ${operationBusy()?'disabled':''}>${(data.content_types||[]).map(row=>`<option value="${esc(row.key)}" ${ui.importType===row.key?'selected':''}>${esc(type(row.key))}</option>`).join('')}</select></label><label class="field">Markdown 正文<textarea id="data-import-text" required maxlength="40000" placeholder="粘贴需要入库的完整材料，保留标题、适用范围和限制条件…" ${operationBusy()?'disabled':''} class="large-textarea">${esc(ui.text)}</textarea></label><div class="form-actions"><button class="btn primary" type="submit" ${ui.previewBusy||operationBusy()?'disabled':''}>${icon('file')}${ui.previewBusy?'正在预览…':'预览切块'}</button>${button('填入示例材料','reset-text',operationBusy()?'disabled':'')}</div><p class="field-hint" id="data-preview-hint">${ui.mode==='sample'?'展示模式预览内置材料；样例不会写入真实知识库。':'预览不会写入。确认入库后保存原文，状态为待向量化；此步骤不启动向量化。'}</p></form>`)}${panel('切块预览',`<div class="panel-pad" id="data-preview-result" aria-live="polite">${previewView()}</div>`)}</div>`;
  }
  function sourceFeatures(features) {
    if(!features)return '—';
    return `<div class="data-source-features">${features.table_split?pill('拆表'):''}${features.overlap?pill('重叠'):''}${pill(number(features.sections)+' 节','neutral')}</div>`;
  }
  function materialsPage(data) {
    const sources=data.sources||[],readable=sources.filter(row=>row.present),known=sources.every(row=>row.present&&Number.isInteger(row.chunks));
    const summary=`${sources.length} 份材料 · 共切 ${known?readable.reduce((sum,row)=>sum+row.chunks,0):'—'} 块`;
    const rows=sources.map(row=>`<tr><td class="data-source-file"><strong>${esc(row.file)}</strong><span class="table-sub mono">${esc(row.path)}</span></td><td>${esc(type(row.content_type))}<span class="table-sub">${row.present?pill('可读'):pill('文件缺失','amber')}</span></td><td>${number(row.chars)}</td><td>${number(row.lines)}</td><td>${number(row.chunks)}</td><td>${number(row.key_clause)}</td><td>${sourceFeatures(row.features)}</td><td>${button('看切块','source-preview',`data-file="${esc(row.file)}" ${!row.present||ui.mode!=='live'||operationBusy()?'disabled':''}`,'soft')}</td></tr>`);
    return `${panel('建库材料',`<div class="panel-pad data-material-description"><p><span class="mono">data/kb/</span> 下的源文件是离线建库的输入。点击“看切块”核对章节、正文与关键条款。</p><p class="muted">这里展示当前文件的切块预估，不代表已入库。预览不写库、不执行向量化。</p>${ui.mode==='sample'?'<p class="field-hint">样例只展示文件清单；查看项目文件切块请切换到实时数据。</p>':''}</div><div class="data-source-table">${table(['材料文件','类型 / 状态','字符','行','切出块数','关键条款','特性','操作'],rows)}</div><div class="data-table-footer"><span>源文件已修改时，请刷新读数后重新预览。</span><div class="form-actions">${button('重新读取材料','refresh',operationBusy()?'disabled':'')}${button('查看离线建库作业','source-jobs','','soft')}</div></div>`,pill(summary,'neutral'))}`;
  }
  function previewView() {
    if(ui.previewBusy)return '<div class="data-empty-state compact" role="status"><h2>正在切块与查重</h2><p>预览不写入知识库。</p></div>';
    if(ui.previewError)return `<div class="notice data-alert" role="alert">${esc(ui.previewError)}</div>`;
    if(!ui.preview)return `<div class="data-empty-state compact">${icon('file')}<h2>先预览，再核对</h2><p>切块结果会保留章节、关键条款和查重状态。</p></div>`;
    const data=ui.preview;
    const ready=canIngest(),note=ui.ingestBusy?'正在保存原文，请等待返回结果。':ui.ingestResult?'本次录入已返回结果；再次录入前请重新预览。':!data.total?'没有切出正文，请补充内容。':!data.dedup_known?'查重未完成，请恢复数据服务后重新预览。':data.total===data.duplicates?'内容全部重复，本次无需新增。':'预览尚未写入；提交时后端会再次查重，实际新增数量以返回结果为准。';
    return `<div class="data-preview-summary"><span>切块 <b>${data.total}</b></span><span>关键条款 <b>${data.key_clause}</b></span><span>${data.dedup_known?`重复 <b>${data.duplicates}</b>`:'查重状态：未知'}</span></div><div class="data-preview-list">${data.chunks.map(row=>`<article class="data-preview-chunk"><div class="between"><strong>${row.seq}. ${esc(row.section_path)}</strong>${row.duplicate==null?pill('未查重','neutral'):row.duplicate?pill('重复','amber'):pill('未发现重复')}</div><p>${esc(row.answer)}</p><div class="small muted">${row.chars} 字${row.is_key_clause?' · 关键条款':''}</div></article>`).join('')}</div><div class="data-import-next"><p class="field-hint">${ui.mode==='sample'?'这是展示样例，确认入库仅在后端实时页面开放。':note}</p>${button(ui.ingestBusy?'正在入库…':'核对并入库','confirm-ingest',ready?'':'disabled','primary')}${ui.mode==='sample'||!location.pathname.startsWith('/v2/')?'<a class="table-actions" href="http://127.0.0.1:8000/v2/#/knowledge">打开实时页面 →</a>':''}</div>`;
  }
  function canIngest() {
    return ui.mode==='live'&&location.pathname.startsWith('/v2/')&&!ui.previewBusy&&!operationBusy()&&!ui.ingestResult&&!ui.ingestError&&ui.preview?.dedup_known&&ui.preview.total>ui.preview.duplicates;
  }
  function invalidatePreview() {
    ui.previewVersion++;ui.preview=null;ui.previewBusy=false;ui.previewError='';confirmedInput=null;
    const target=document.getElementById('data-preview-result');if(target)target.innerHTML=previewView();
  }
  function ingestResultView() {
    if(ui.ingestBusy)return '<div class="notice data-ingest-status" role="status">正在保存原文，请勿重复提交。录入结果返回后会重新读取库存。</div>';
    if(ui.ingestError)return `<div class="data-ingest-result">${panel(ui.ingestError.uncertain?'录入结果待核对':'录入未完成',`<div class="panel-pad"><div class="notice data-alert ${ui.ingestError.uncertain?'amber':'data-ingest-error'}" role="alert">${esc(ui.ingestError.message)}</div><p class="field-hint">${ui.ingestError.uncertain?'请求可能已写入原文，请先查看库存，再重新预览查重；不要直接重复提交。':'原文仍保留在表单中，请检查内容后重新预览。'}</p><div class="form-actions">${button('查看知识库存','ingest-inventory','','soft')}</div></div>`)}</div>`;
    if(!ui.ingestResult)return '';
    const data=ui.ingestResult;
    return `<div class="data-ingest-result">${panel(data.inserted?'原文已入库':'内容已存在，本次未新增',`<div class="panel-pad"><div class="data-ingest-counts"><span>实际新增 <b>${data.inserted}</b> 块</span><span>跳过重复 <b>${data.skipped}</b> 块</span><span>${pill('本次未执行向量化','amber')}</span></div>${data.ids.length?`<div class="data-ingest-ids"><span class="muted">入库记录</span>${data.ids.map(id=>button('#'+esc(id),'chunk',`data-id="${esc(id)}"`,'soft')).join('')}</div>`:''}<p class="field-hint">${data.inserted?'原文已保存，录入时为待向量化。点击记录核对完整正文和当前状态。':'提交时再次查重，全部内容已存在。'}</p><div class="form-actions">${button('查看知识库存','ingest-inventory','','soft')}${data.inserted?button('查看索引并补齐','vector-index','','primary'):''}${button('录入下一份','ingest-next')}</div></div>`,pill('真实录入结果'))}</div>`;
  }
  function confirmIngest() {
    if(!canIngest())return;
    confirmedInput={text:ui.text,content_type:ui.importType,version:ui.previewVersion};
    modal('核对本次录入',`<form id="data-ingest-form"><div class="data-detail-meta">${pill(type(ui.importType),'neutral')}${pill('仅保存原文，待向量化','amber')}</div><p>预览 ${ui.preview.total} 块，重复 ${ui.preview.duplicates} 块，预计新增 ${ui.preview.total-ui.preview.duplicates} 块。实际结果以提交时再次查重为准。</p><details class="data-source-excerpt" open><summary>本次提交的完整原文 · ${ui.text.length} 字</summary><div class="data-detail-text data-ingest-original">${esc(ui.text)}</div></details><label class="data-ingest-check"><input type="checkbox" required name="checked">我已核对内容与适用范围，确认将原文存入当前知识库。</label></form>`,'<button class="btn" data-action="modal-close">继续检查</button><button class="btn primary" type="submit" form="data-ingest-form">确认入库原文</button>');
    document.getElementById('modal').classList.add('knowledge-dialog');
  }
  function miningPage() {
    const value=resource('staging'), pending=loadingOrError(value);if(pending)return pending;
    const data=value.data, counts=data.stats?.counts||{}, labels={kept:'待审核',extracted:'已抽取',discarded:'去重已丢弃',approved:'已采纳',rejected:'人工已弃用'};
    const rows=(data.rows?.[ui.candidate]||[]).map(row=>`<tr><td class="data-content-cell"><strong>${esc(row.question)}</strong><p class="data-answer-preview">${esc(row.answer)}</p></td><td class="mono">${esc(row.source_ref||'未标注材料')}</td><td>${esc(row.batch_no||'—')}</td><td>${pill(labels[ui.candidate],ui.candidate==='kept'?'amber':'neutral')}</td><td><button class="table-actions" data-data-action="candidate" data-id="${esc(row.id)}">查看</button></td></tr>`);
    return `<div class="stat-strip data-metrics">${metric('待人工审核',counts.kept,'条','去重后保留的候选')}${metric('已采纳入库',counts.approved,'条','以全量统计为准')}${metric('人工已弃用',counts.rejected,'条','与去重丢弃分别计数')}${metric('抽取批次',data.stats?.batches,'批','保留来源和批次')}</div>${panel('候选问答',`<div class="panel-toolbar data-filters">${Object.entries(labels).map(([key,label])=>`<button class="filter-chip ${ui.candidate===key?'active':''}" data-data-candidate="${key}" aria-pressed="${ui.candidate===key}">${label} <span>${number(counts[key])}</span></button>`).join('')}</div>${table(['问题与答案摘要','材料来源','批次','状态','操作'],rows)}<p class="data-table-footer"><span>当前状态全量 ${number(counts[ui.candidate])} 条 · 本次展示 ${number((data.rows?.[ui.candidate]||[]).length)} 条<br>每种状态最多读取 ${number(data.limit||30)} 条；查看详情可核对完整答案与当前材料。</span>${pill(ui.mode==='live'?'核对后采纳或弃用':'样例核对','neutral')}</p>`,pill('独立审核队列','neutral'))}`;
  }
  function indexPage(data) {
    const s=data.chunks||{}, v=data.milvus||{};
    const label=data.consistent===true?'两端数量一致':data.consistent===false?'仍有待补向量或数量不一致':'暂无法核对';
    return `<div class="stat-strip data-metrics">${metric('数据库知识块',s.total,'块','保存原文和元数据')}${metric('已向量化',s.done,'块','已完成向量化')}${metric('待向量化',s.pending,'块','可补齐，无需重录')}${metric('向量库记录',v.online?v.count:null,'条',v.online?'Milvus 返回的数量':'向量库当前不可用')}</div><div class="data-status-grid">${panel('原文与向量',`<div class="panel-pad"><div class="data-status-title">${pill(data.db_error?'原文读取失败':'原文数据库可读',data.db_error?'red':'')}${pill(v.online?'向量库在线':'向量库离线',v.online?'':'amber')}</div><h3>${label}</h3><p class="muted section-gap">数量一致是库存检查，检索质量需要单独自测。</p><div class="form-actions">${button('检索自测','search','','soft')}${button('查看待向量化原文','vector-pending')}</div></div>`)}${panel('按内容类型',`<div class="panel-pad data-type-breakdown">${Object.entries(s.by_content_type||{}).map(([key,count])=>`<div class="between"><span>${esc(type(key))}</span><strong>${number(count)} <small class="muted">块</small></strong></div>`).join('')||'<p class="muted">暂无可读取的类型统计</p>'}</div>`)}</div><div class="section-gap">${vectorJobView(data)}</div>`;
  }
  function vectorJobResource() {
    if(ui.mode==='sample'){
      const value=resource('jobs');return value.status==='ready'?{...value,data:value.data.jobs?.find(row=>row.name==='kb-vectorize')}:value;
    }
    return resource('vectorJob',vectorJobPath);
  }
  function canPrepareVector(data,job) {
    return ui.mode==='live'&&location.pathname.startsWith('/v2/')&&!operationBusy()&&!ui.vectorReading&&!data.db_error&&Number.isInteger(data.chunks?.pending)&&data.chunks.pending>0&&data.milvus?.online===true&&job?.name==='kb-vectorize'&&Object.hasOwn(vectorLabels,job.status)&&job.status!=='running';
  }
  function vectorJobView(data) {
    const value=vectorJobResource(),job=value.data,s=data.chunks||{};
    if(job?.status==='running'&&ui.mode==='live')scheduleVectorPoll();
    const note=ui.mode==='sample'?'展示模式仅查看作业状态，不启动向量化。':value.status==='error'?'作业状态读取失败，请重新查询；不能据此判断任务已停止。':!job?'正在读取向量化作业状态。':job.status==='running'?'作业正在运行。仅查询真实状态，不按耗时推测进度。':job.status==='failed'?'进程失败，可能已完成部分批次。按当前库存核对剩余原文，修复依赖后再补齐，无需重录。':job.status==='ok'?'进程已执行完成。请核对当前待向量化数量与向量库记录；完成状态不代替检索质量验收。':job.status==='stopped'?'作业已停止，已完成批次仍需按库存核对。':job.status==='idle'&&job.log_mtime?'本次服务没有运行记录，存在既有日志。服务重启会清空运行状态，旧日志不代表本次结果。':s.pending===0?'当前没有待向量化原文，无需启动作业。':'处理全库待向量化原文，需要数据库、嵌入服务与向量库。';
    return panel('向量补齐作业',`<div class="panel-pad"><div class="data-vector-top"><div><p class="mono muted">kb-vectorize</p><p class="data-vector-note">${esc(note)}</p></div>${pill(job?vectorLabels[job.status]||'状态未知':value.status==='error'?'状态读取失败':'正在读取',job?.status==='failed'?'red':job?.status==='running'?'amber':'neutral')}</div>${ui.mode==='live'&&ui.vectorNotice?`<div class="notice amber" role="status">${esc(ui.vectorNotice)}</div>`:''}<dl class="data-record-fields"><div><dt>全库待向量化</dt><dd>${number(s.pending)} 块</dd></div><div><dt>开始时间</dt><dd>${stamp(job?.started_at)}</dd></div><div><dt>结束时间</dt><dd>${stamp(job?.finished_at)}</dd></div><div><dt>退出码</dt><dd>${number(job?.returncode)}</dd></div><div><dt>日志更新时间</dt><dd>${stamp(job?.log_mtime)}</dd></div></dl><div class="form-actions">${button(ui.vectorStarting?'正在提交启动…':ui.vectorChecking?'正在核对…':'核对并补齐向量','vectorize',canPrepareVector(data,job)?'':'disabled','primary')}${button(ui.vectorReading?'正在查询…':'刷新作业状态','vector-refresh',operationBusy()||ui.vectorReading?'disabled':'','soft')}${button('打开作业中心','vector-jobs')}</div>${job?`<details class="data-vector-log"><summary>查看日志末尾 · 最多 400 行</summary><pre tabindex="0" aria-label="向量补齐作业日志">${esc(job.log||'暂无可读取的日志。')}</pre></details>`:''}<p class="field-hint section-gap">此作业处理启动时全库 pending 原文，包含历史待补块；不会只处理上一次录入的记录。启动需要人工确认，会调用嵌入服务。</p></div>`);
  }
  function vectorPageActive(){return ui.mode==='live'&&h.state.surface==='admin'&&h.state.page==='knowledge'&&ui.tab==='index';}
  function stopVectorPoll(){if(vectorPollTimer!=null)clearTimeout(vectorPollTimer);vectorPollTimer=null;}
  function scheduleVectorPoll(){if(vectorPageActive()&&!ui.vectorReading&&!vectorPollTimer)vectorPollTimer=setTimeout(()=>{vectorPollTimer=null;if(vectorPageActive())readVectorJob();},3000);}
  async function readVectorJob() {
    if(ui.mode!=='live'||operationBusy()||ui.vectorReading)return;
    const epoch=ui.epoch;stopVectorPoll();ui.vectorReading=true;render();
    try {
      const job=await request(vectorJobPath);if(epoch!==ui.epoch)return;
      if(job.name!=='kb-vectorize'||!Object.hasOwn(vectorLabels,job.status))throw new Error('作业状态不完整，请重新查询。');
      if(job.status!=='idle'&&ui.vectorStartUnknown){ui.vectorStartUnknown=false;ui.vectorNotice='已查询到真实作业状态，请结合库存和日志核对。';}
      if(job.status!=='idle'&&job.status!=='running')ui.vectorNotice='作业已返回结束状态，库存已重新读取；请核对剩余原文和日志。';
      if(job.status==='running')ui.cache.vectorJob={status:'ready',data:job};
      else {ui.epoch++;ui.cache={vectorJob:{status:'ready',data:job}};}
    } catch(error) {if(epoch===ui.epoch)ui.cache.vectorJob={status:'error',error:error.message};}
    finally {ui.vectorReading=false;render();}
  }
  async function prepareVector() {
    const data=ui.cache.kb?.data,job=ui.cache.vectorJob?.data;
    if(!canPrepareVector(data||{},job))return;
    const epoch=ui.epoch,key='vector-'+(++detailSequence),dialog=document.getElementById('modal');
    ui.vectorChecking=true;confirmedVector=false;render();
    modal('核对向量补齐','<div class="empty" role="status">正在重新读取全库待补数量和作业状态…</div>');dialog.dataset.knowledgeKey=key;
    try {
      const [latest,currentJob]=await Promise.all([request('/api/kb/overview'),request(vectorJobPath)]);
      if(epoch!==ui.epoch||!dialog.open||dialog.dataset.knowledgeKey!==key)return;
      ui.cache.kb={status:'ready',data:latest};ui.cache.vectorJob={status:'ready',data:currentJob};ui.vectorChecking=false;
      if(!canPrepareVector(latest,currentJob)){
        modal('暂不能启动向量补齐',`<p>${currentJob.status==='running'?'同一作业已经运行，请查看状态和日志。':latest.db_error?'原文库存暂不可读取。':latest.chunks?.pending===0?'当前已没有待向量化原文。':latest.milvus?.online!==true?'向量库当前不可用，请恢复服务后重新核对。':'作业状态暂不可确认，请重新查询。'}</p>`);return;
      }
      confirmedVector=true;
      modal('核对全库向量补齐',`<form id="data-vector-form">${ui.vectorStartUnknown?'<div class="notice amber">上次启动未收到明确结果。请结合当前运行状态、库存与日志核对，再决定是否重新启动。</div>':''}<div class="data-detail-meta">${pill('全库待向量化 '+latest.chunks.pending+' 块','amber')}${pill('向量库在线')}${pill(vectorLabels[currentJob.status],'neutral')}</div><p>启动现有向量化作业，处理启动时所有 pending 原文，包含历史待补块；实际数量可能随库存变化。会调用嵌入服务，将向量写入向量库，再更新原文状态。</p><p class="field-hint section-gap">失败时保留已完成批次；修复后仅补齐剩余 pending 原文，无需重新录入。运行记录属于当前服务，服务重启后需结合库存与日志核对。</p><label class="data-ingest-check"><input type="checkbox" required name="checked">我已核对全库处理范围及执行条件，确认启动向量补齐。</label></form>`,'<button class="btn" data-action="modal-close">继续检查</button><button class="btn primary" type="submit" form="data-vector-form">确认启动向量补齐</button>');
      dialog.classList.add('knowledge-dialog');dialog.dataset.knowledgeKey=key;
    } catch(error) {if(epoch===ui.epoch&&dialog.open&&dialog.dataset.knowledgeKey===key)modal('执行条件暂时无法核对',`<p>${esc(error.message)}</p><p class="field-hint section-gap">尚未发送启动请求，请恢复查询后再核对。</p>`);}
    finally {ui.vectorChecking=false;render();}
  }
  async function startVector() {
    if(!confirmedVector||!canPrepareVector(ui.cache.kb?.data||{},ui.cache.vectorJob?.data))return;
    confirmedVector=false;stopVectorPoll();ui.vectorStarting=true;ui.vectorNotice='';ui.vectorStartUnknown=false;
    document.getElementById('modal').close();render();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await fetch(vectorJobPath,{method:'POST',signal:controller.signal,headers:{Accept:'application/json'}});
      if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{}throw Object.assign(new Error(response.status===409?'同一作业已经运行，请查看现有运行状态。':typeof detail==='string'&&response.status<500?detail:`启动请求未返回完整结果（HTTP ${response.status}）。`),{uncertain:response.status>=500});}
      const job=await response.json();
      if(job.name!=='kb-vectorize'||!Object.hasOwn(vectorLabels,job.status)||job.status==='idle')throw new Error('启动结果不完整，请查询真实作业状态。');
      ui.epoch++;ui.cache={vectorJob:{status:'ready',data:job}};
      ui.vectorNotice=job.status==='running'?'已提交启动，正在读取真实作业状态。':'作业已返回结束状态，请核对库存与日志。';
    } catch(error) {
      ui.vectorStartUnknown=error.uncertain!==false;ui.vectorNotice=error.name==='AbortError'?'启动请求超时，尚不能确认是否已启动。请先刷新作业状态，不要直接重复提交。':error.message;delete ui.cache.vectorJob;
    } finally {clearTimeout(timer);ui.vectorStarting=false;render();}
  }
  function searchPage() {
    const results=ui.hits==null?`<div class="data-empty-state compact">${icon('search')}<h2>看看知识能否被找到</h2><p>输入另一种问法，核对召回的内容与依据。</p></div>`:ui.hits.length?ui.hits.map((hit,index)=>`<article class="data-search-hit"><div class="between"><h3>${index+1}. ${esc(hit.question||hit.section_path||'未标注问法')}</h3>${pill(type(hit.content_type),'neutral')}</div><p>${esc(hit.answer)}</p><div class="small muted">${esc(hit.section_path||'未标注章节')} · 检索分数 ${number(hit.score)} · 重排分数 ${number(hit.rerank_score)}</div></article>`).join(''):'<div class="empty">检索已完成，没有命中知识块。</div>';
    return panel('检索自测',`<form id="data-search-form" class="panel-pad"><div class="query-grid"><label class="field">换一种说法提问<input id="data-search-query" required maxlength="500" value="${esc(ui.searchQuery)}"></label><label class="field">检索策略<select id="data-search-strategy">${[['vector','向量检索'],['bm25','关键词检索'],['hybrid','混合检索'],['hybrid_rerank','混合 + 重排']].map(([key,label])=>`<option value="${key}" ${ui.strategy===key?'selected':''}>${label}</option>`).join('')}</select></label><button class="btn primary" type="submit" ${ui.searchBusy?'disabled':''}>${icon('search')}${ui.searchBusy?'正在检索…':'检索'}</button></div><p class="field-hint">${ui.mode==='sample'?'展示模式只显示内置召回样例，分数留空。':'点击后调用检索服务，可能使用嵌入或重排模型。'}检索分数不等于答案正确率。</p></form>${ui.searchError?`<div class="panel-pad notice" role="alert">${esc(ui.searchError)}</div>`:''}<div class="panel-pad" id="data-search-result">${results}</div>`);
  }
  function overviewPage() {
    const value=resource('admin'), stateView=loadingOrError(value);if(stateView)return stateView;
    const routes={kb:'knowledge',review:'review',rageval:'quality',observability:'observability',topics:'topics',classifier:'models'};
    const icons={kb:'book',review:'search',rageval:'shield',observability:'chart',topics:'chat',classifier:'spark'};
    const data=value.data, attention=(data.modules||[]).filter(row=>row.status==='attention'||row.status==='error');
    return `<div class="overview-layout"><div><div class="overview-heading"><h2>管理工作区</h2><span class="small muted">六个模块，分别读取业务状态</span></div><div class="module-grid">${(data.modules||[]).map(row=>`<button class="module-card data-module" data-page="${routes[row.key]||'overview'}"><div class="module-card-top"><span class="module-icon">${icon(icons[row.key]||'chart')}</span>${moduleState(row.status)}</div><h2>${esc(({kb:'知识中心',review:'知识缺口',rageval:'RAG 质量',classifier:'分类器管理'})[row.key]||row.title)}</h2><p>${esc(row.headline)}</p><div class="data-module-metrics">${(row.metrics||[]).map(m=>`<span>${esc(m.label)} <b>${number(m.value)}</b></span>`).join('')||'<span class="muted">等待读数或报告</span>'}</div><small>${esc(row.note||row.lede||'查看详细业务状态')}</small></button>`).join('')}</div></div><aside><section class="aside-panel"><div class="eyebrow">需要关注</div><h3>从这里开始处理</h3>${attention.map(row=>`<button class="todo-row" data-page="${routes[row.key]||'knowledge'}"><span>${esc(row.title)}<small>${esc(row.headline)}</small></span>${icon('arrow')}</button>`).join('')||'<p class="small muted section-gap">当前没有读到需关注事项。</p>'}<button class="todo-row" data-page="knowledge"><span>核对知识与索引<small>原文、待向量化与向量数量</small></span>${icon('arrow')}</button></section><section class="aside-panel data-scope-note"><h3>每个数字，都有来源</h3><p>库存、报告和运行状态分别读取；未知值保留为 —。</p><p>${ui.mode==='sample'?'当前是展示样例，适合先看信息组织。':'当前接入总览、知识、审核、作业、质量、观测、主题与分类器的只读数据。'}</p></section></aside></div>`;
  }
  function renderPage(page) {
    if(ui.mode==='sample'&&!scenarioOptions().some(([value])=>value===ui.scenario))ui.scenario='normal';
    let body, time;
    if(page==='overview') {body=overviewPage();time=ui.cache.admin?.time;}
    else if(page==='review') {body=workflows.reviewPage();time=workflows.reviewTime();}
    else if(page==='jobs') {body=workflows.jobPage();time=ui.cache.jobs?.time;}
    else if(page==='quality') {body=reports.qualityPage();time=reports.qualityTime();}
    else if(page==='observability') {body=reports.observationPage();time=ui.cache.observation?.time;}
    else if(classification.hasPage(page)){body=page==='topics'?classification.topicsPage():classification.modelsPage();time=classification.time(page);}
    else {
      const value=resource('kb');time=value.time;
      body=ui.tab==='mining'?miningPage():ui.tab==='search'?searchPage():ui.tab==='content'?contentPage(value.data||{}):loadingOrError(value)||({materials:materialsPage,import:importPage,index:indexPage})[ui.tab](value.data);
      if(ui.tab==='content')time=inventoryResource().time||time;
      if(ui.tab==='mining')time=ui.cache.staging?.time;
      body=`<nav class="section-tabs" aria-label="知识中心子页面">${tabs.map(([key,label])=>`<button data-data-tab="${key}" class="${ui.tab===key?'active':''}" aria-current="${ui.tab===key?'page':'false'}">${label}</button>`).join('')}</nav>${body}`;
    }
    return `<div class="page admin-page data-page">${header(page)}${sourceBar()}${ui.mode==='live'&&ui.actionNotice?`<div class="notice data-alert" role="status">${esc(ui.actionNotice)}</div>`:''}${body}<p class="source-line">${icon('file')}${ui.mode==='sample'?'V2 数据展示稿 · 样例不代表真实记录或报告':'当前项目接口 · '+(time?'本次读取 '+esc(time):'等待读取')}${page==='knowledge'?' · 文档版本与发布生命周期尚无对应数据':''}</p></div>`;
  }
  function refresh() {if(operationBusy())return;stopVectorPoll();confirmedVector=false;actions.reset();ui.epoch++;ui.cache={};invalidatePreview();ui.hits=null;ui.searchError='';ui.searchBusy=false;workflows.reset();classification.reset();render();}
  function onClick(el) {
    if(el.dataset.action==='modal-close'){actions.reset();return false;}
    if(actions.onClick(el))return true;
    if(operationBusy()&&(el.dataset.dataMode||el.dataset.wfAction||el.dataset.reportAction||el.dataset.candidateAction))return true;
    if(el.dataset.candidateAction){if(candidateRow)actions.candidate(candidateRow,el.dataset.candidateAction,()=>showKnowledgeDetail('candidate',String(candidateRow.id)));return true;}
    if(classification.onClick(el))return true;
    if(reports.onClick(el))return true;
    if(workflows.onClick(el))return true;
    if(el.dataset.dataMode){if(operationBusy())return true;ui.mode=el.dataset.dataMode;if(ui.mode==='live'&&ui.text===exampleText)ui.text='';ui.ingestResult=null;ui.ingestError=null;refresh();return true;}
    if(el.dataset.dataTab){ui.tab=el.dataset.dataTab;render();return true;}
    if(el.dataset.dataFilter){ui.filter=el.dataset.dataFilter;ui.page=1;render();return true;}
    if(el.dataset.dataCandidate){ui.candidate=el.dataset.dataCandidate;render();return true;}
    if(!el.dataset.dataAction)return false;
    const action=el.dataset.dataAction;
    if(action==='refresh')refresh();
    else if(action==='knowledge')go('knowledge');
    else if(['materials','import','index','search'].includes(action)){ui.tab=action;render();}
    else if(action==='source-preview')previewMaterial(el.dataset.file);
    else if(action==='source-jobs')go('jobs');
    else if(action==='reset-text'){if(operationBusy())return true;ui.text=exampleText;ui.importType='policy';invalidatePreview();render();}
    else if(action==='confirm-ingest')confirmIngest();
    else if(action==='ingest-inventory'){ui.tab='content';ui.filter=ui.type='all';ui.query=ui.queryDraft='';ui.page=1;refresh();}
    else if(action==='ingest-next'){if(operationBusy())return true;ui.text='';ui.ingestResult=null;ui.ingestError=null;invalidatePreview();render();}
    else if(action==='vector-index'){ui.tab='index';go('knowledge');}
    else if(action==='vector-pending'){ui.tab='content';ui.filter='pending';ui.type='all';ui.query=ui.queryDraft='';ui.page=1;render();}
    else if(action==='vector-refresh')readVectorJob();
    else if(action==='vector-jobs'){stopVectorPoll();go('jobs');}
    else if(action==='chunk-page'){ui.page=Number(el.dataset.page);render();}
    else if(action==='clear-query'){ui.query=ui.queryDraft='';ui.page=1;render();}
    else if(['chunk','candidate'].includes(action))showKnowledgeDetail(action,el.dataset.id);
    else if(action==='vectorize')prepareVector();
    return true;
  }
  function onInput(el) {
    classification.onInput(el);
    reports.onInput(el);
    workflows.onInput(el);
    if(el.id==='data-query')ui.queryDraft=el.value;
    if(el.id==='data-import-text'&&!operationBusy()){ui.text=el.value;invalidatePreview();}
    if(el.id==='data-search-query'){ui.searchQuery=el.value;ui.hits=null;ui.searchError='';document.getElementById('data-search-result').innerHTML='<div class="empty">问法已修改，请重新检索。</div>';}
  }
  function onChange(el) {
    if(classification.onChange(el))return true;
    if(reports.onChange(el))return true;
    if(workflows.onChange(el))return true;
    if(el.id==='data-scenario'){ui.scenario=el.value;invalidatePreview();ui.hits=null;workflows.reset();classification.reset();render();return true;}
    if(el.id==='data-type'){ui.type=el.value;ui.page=1;render();return true;}
    if(el.id==='data-size'){ui.size=Number(el.value);ui.page=1;render();return true;}
    if(el.id==='data-import-type'){if(operationBusy())return true;ui.importType=el.value;invalidatePreview();return true;}
    if(el.id==='data-search-strategy'){ui.strategy=el.value;ui.hits=null;ui.searchError='';render();return true;}
    return false;
  }
  function detailFields(fields) {
    return `<dl class="data-record-fields">${fields.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${value}</dd></div>`).join('')}</dl>`;
  }
  function chunkDetailView(row) {
    return `<div class="data-detail-meta">${pill('#'+row.id,'neutral')}${pill(type(row.content_type),'neutral')}${vectorState(row.status)}${row.is_key_clause?pill('关键条款'):''}</div><h3>${esc(row.questions||'未标注问法')}</h3>${detailFields([['章节',esc(row.section_path||'未标注')],['分类',esc(row.category||'未标注')],['录入时间',stamp(row.created_at)],['向量记录',esc(row.vector_id||'未返回')],['关联审核',row.review_id?esc('#'+row.review_id):'未关联'],['相邻知识块',[row.prev_chunk_id?`前 #${esc(row.prev_chunk_id)}`:'',row.next_chunk_id?`后 #${esc(row.next_chunk_id)}`:''].filter(Boolean).join(' · ')||'未关联']])}<section class="data-full-answer"><div class="between"><h3>完整正文</h3><span class="small muted">${esc(row.answer.length)} 字</span></div><div class="data-detail-text">${esc(row.answer)}</div></section><p class="field-hint section-gap">${ui.mode==='sample'?'当前内容为展示样例。':'正文来自知识块详情接口。'}文档版本与发布生命周期尚无对应字段。</p>`;
  }
  function candidateDetailView(row) {
    const labels={kept:'待审核',extracted:'已抽取',discarded:'去重已丢弃',approved:'已采纳',rejected:'人工已弃用'},m=row.material||{};
    const stateLabels={available:'可信材料可读',missing:'材料缺失',untrusted:'来源不可信',read_error:'材料读取失败'};
    const conclusion=m.valid===true?'当前校验通过':m.valid===false?'当前校验未通过':'暂无法核对';
    return `<div class="data-detail-meta">${pill('#'+row.id,'neutral')}${pill(labels[row.status]||row.status||'未知','neutral')}${pill(ui.mode==='sample'?'展示样例':'核对后操作','neutral')}</div><h3>${esc(row.question)}</h3>${detailFields([['来源标记',esc(row.source_ref||'未标注')],['抽取批次',esc(row.batch_no||'未标注')],['抽取时间',stamp(row.created_at)],['当前状态',esc(labels[row.status]||row.status||'未知')]])}<div class="data-candidate-evidence"><section class="data-full-answer"><div class="between"><h3>候选完整答案</h3><span class="small muted">${esc(row.answer.length)} 字</span></div><div class="data-detail-text">${esc(row.answer)}</div></section><section class="data-full-answer"><div class="between"><h3>当前材料依据</h3>${pill(stateLabels[m.status]||'未提供',m.status==='available'?'':'amber')}</div><div class="data-validation ${m.valid===false?'attention':''}"><strong>${conclusion}</strong><p>${esc(m.reason||(m.valid===true?'问题与答案符合现有可信来源校验。仍需人工判断适用范围与内容质量。':'尚无可读取的可信材料。'))}</p></div>${m.text!=null?`<details class="data-source-excerpt" ${m.valid===false?'open':''}><summary>阅读完整材料 · ${esc(m.file||'未标注')}<span>${esc(m.text.length)} 字</span></summary><div class="data-detail-text">${esc(m.text)}</div></details>`:''}${m.sha256?`<p class="field-hint section-gap">材料 SHA-256 <span class="mono">${esc(m.sha256)}</span></p>`:''}</section></div><p class="field-hint section-gap">核对使用当前材料，不代表抽取时的历史快照或人工审核结果。现有记录没有审核理由、操作人及入库知识块关联字段；这些信息保留为未提供。</p>`;
  }
  let detailSequence=0,candidateRow=null;
  async function showKnowledgeDetail(kind,id) {
    const epoch=ui.epoch,key=String(++detailSequence),dialog=document.getElementById('modal'),title=kind==='chunk'?'知识块详情':'候选问答详情';
    const draw=body=>{const footer=candidateRow&&kind==='candidate'&&ui.mode==='live'&&candidateRow.status==='kept'?`<button class="btn" data-action="modal-close">关闭</button><button class="btn" data-candidate-action="reject">核对并弃用</button><button class="btn primary" data-candidate-action="approve" ${candidateRow.material?.valid===true?'':'disabled'}>核对并采纳</button>`:undefined;modal(title,body,footer);dialog.classList.add('knowledge-dialog');dialog.dataset.knowledgeKey=key;};
    candidateRow=null;
    draw('<div class="empty" role="status">正在读取完整内容…</div>');
    try {
      let row;
      if(ui.mode==='sample') {
        if(kind==='chunk')row=sampleKnowledge().recent.find(item=>String(item.id)===id);
        else {
          const materials={
            'returns-policy.md':'# 退换货展示材料\n\n签收后 7 天内可申请退货。商品需未使用，配件齐全。\n\n保留全部配件，核对退货材料要求。',
            'after-sales-manual.md':'# 物流异常展示材料\n\n联系人工客服核查最近一次物流记录和承运状态。',
            'product-faq.md':'# 商品使用展示材料\n\n首次使用前请阅读说明书，核对电源与水位，确认摆放平稳。',
            'billing-shipping.md':'# 发货展示材料\n\n常规现货商品付款后 48 小时内发出，预售以商品说明为准。'
          };
          for(const [status,rows] of Object.entries(sampleCandidates.rows)) {
            const found=rows.find(item=>String(item.id)===id);
            if(found) {
              const text=materials[found.source_ref],valid=Boolean(text?.includes(found.answer));
              row={...found,status,created_at:null,material:found.source_ref?{status:text?'available':'untrusted',file:found.source_ref,text:text||null,valid:text?valid:null,reason:valid?'展示样例：候选答案在材料连续原文中。仍需人工核对适用范围。':'展示样例：候选答案并非材料中的连续原文，采纳前需人工核对。'}:{status:'missing',valid:null,reason:'展示样例：未标注材料来源。'}};
            }
          }
        }
        if(!row)throw new Error('记录不存在，请刷新列表。');
      } else row=await request(`/api/kb/${kind==='chunk'?'chunks':'staging'}/${encodeURIComponent(id)}`);
      if(epoch===ui.epoch&&dialog.open&&dialog.dataset.knowledgeKey===key){if(kind==='candidate')candidateRow=row;draw(kind==='chunk'?chunkDetailView(row):candidateDetailView(row));}
    } catch(error) {
      if(epoch===ui.epoch&&dialog.open&&dialog.dataset.knowledgeKey===key)draw(`<div class="data-empty-state compact"><h2>详情暂时无法读取</h2><p>${esc(error.message)}</p>${button('重新读取',kind,`data-id="${esc(id)}"`)}</div>`);
    }
  }
  async function previewMaterial(file) {
    const source=resource('kb').data?.sources?.find(row=>row.file===file);
    if(ui.mode!=='live'||!source?.present||operationBusy())return;
    const epoch=ui.epoch,key=String(++detailSequence),dialog=document.getElementById('modal');
    const draw=body=>{modal('建库材料 · '+file,body,'<button class="btn" data-action="modal-close">关闭</button>');dialog.classList.add('knowledge-dialog');dialog.dataset.knowledgeKey=key;};
    candidateRow=null;
    draw('<div class="empty" role="status">正在读取文件并预览切块…</div>');
    try {
      const data=await request('/api/kb/preview',{file});
      if(!Array.isArray(data.chunks)||!Number.isInteger(data.total)||data.total!==data.chunks.length)throw new Error('切块结果不完整，请重新预览。');
      if(epoch!==ui.epoch||!dialog.open||dialog.dataset.knowledgeKey!==key)return;
      const summary=`<div class="stat-strip data-metrics">${metric('原文字符',data.chars,'字','当前文件内容')}${metric('切出块数',data.total,'块','预览尚未写入')}${metric('关键条款',data.key_clause,'块','完整保留的约束')}${metric('重复块',data.dedup_known===true?data.duplicates:'未知',data.dedup_known===true?'块':'','与现有库存核对')}</div>`;
      const chunks=data.chunks.map(row=>`<article class="data-preview-chunk"><div class="between"><strong>${number(row.seq)}. ${esc(row.section_path)}</strong>${row.duplicate==null?pill('未查重','neutral'):row.duplicate?pill('重复','amber'):pill('未发现重复')}</div>${row.questions?`<p><strong>问法</strong> ${esc(row.questions)}</p>`:''}<p>${esc(row.answer)}</p><div class="small muted">${number(row.chars)} 字${row.category?' · '+esc(row.category):''}${row.is_key_clause?' · 关键条款':''}${row.is_table?' · 表格':''}</div></article>`).join('')||'<div class="empty">材料中没有可切块的正文。</div>';
      draw(`<p class="mono muted">${esc(data.source)} · ${esc(type(data.content_type))}</p><p class="field-hint">本次仅预览与查重，不写入知识库、不执行向量化。</p>${summary}${sourceFeatures(data.features)}${chunks}`);
    } catch(error) {
      if(epoch===ui.epoch&&dialog.open&&dialog.dataset.knowledgeKey===key)draw(`<div class="data-empty-state compact"><h2>材料预览暂时不可用</h2><p>${esc(error.message)}</p>${button('重新预览','source-preview',`data-file="${esc(file)}"`)}</div>`);
    }
  }
  async function preview() {
    const epoch=ui.epoch,text=ui.text,contentType=ui.importType,version=++ui.previewVersion;ui.previewBusy=true;ui.preview=null;ui.previewError='';confirmedInput=null;render();
    try {
      let data;
      if(ui.mode==='sample') {
        if(ui.text!==exampleText||ui.importType!=='policy')throw new Error('展示模式使用内置样例，请恢复示例材料；手工文本可从实时接口预览。');
        const rows=[['退换货政策 / 申请条件','签收后 7 天内可申请退货。商品需未使用，配件齐全。'],['退换货政策 / 包装要求','拆开外包装不直接等同于商品已使用，应由客服核对包装现状。']].map(([section_path,answer],index)=>({seq:index+1,section_path,answer,chars:answer.length,is_key_clause:true,duplicate:ui.scenario==='error'?null:false}));
        data={total:rows.length,key_clause:2,duplicates:0,dedup_known:ui.scenario!=='error',chunks:rows};
      } else data=await request('/api/kb/preview',{text,content_type:contentType});
      if(!Array.isArray(data.chunks)||!Number.isInteger(data.total)||data.total!==data.chunks.length||!Number.isInteger(data.duplicates)||data.duplicates<0||data.duplicates>data.total)throw new Error('切块结果不完整，请重新预览。');
      if(epoch===ui.epoch&&version===ui.previewVersion){ui.preview=data;ui.ingestResult=null;if(data.dedup_known)ui.ingestError=null;}
    } catch(error){if(epoch===ui.epoch&&version===ui.previewVersion)ui.previewError=error.message;}
    finally {if(epoch===ui.epoch&&version===ui.previewVersion){ui.previewBusy=false;render();}}
  }
  async function ingest() {
    const input=confirmedInput;
    if(!canIngest()||!input||input.version!==ui.previewVersion||input.text!==ui.text||input.content_type!==ui.importType)return;
    confirmedInput=null;ui.ingestBusy=true;ui.ingestError=null;ui.ingestResult=null;
    document.getElementById('modal').close();render();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
    try {
      const response=await fetch('/api/kb/ingest',{method:'POST',signal:controller.signal,headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({text:input.text,content_type:input.content_type,vectorize:false})});
      if(!response.ok){
        let detail;try{detail=(await response.json()).detail;}catch{}
        throw Object.assign(new Error(response.status>=500?`服务未返回完整录入结果（HTTP ${response.status}）。`:typeof detail==='string'?detail:`录入请求未通过（HTTP ${response.status}），请检查内容。`),{uncertain:response.status>=500});
      }
      const data=await response.json();
      if(!Number.isInteger(data.chunks)||!Number.isInteger(data.inserted)||!Number.isInteger(data.skipped)||data.inserted<0||data.skipped<0||data.inserted+data.skipped!==data.chunks||!Array.isArray(data.ids)||data.ids.length!==data.inserted||new Set(data.ids).size!==data.ids.length||data.ids.some(id=>!Number.isInteger(id)||id<1)||data.vectorized!==null)throw new Error('服务返回的录入结果不完整，暂不能确认新增数量。');
      ui.ingestResult=data;
    } catch(error) {
      ui.ingestError={uncertain:error.uncertain!==false,message:error.name==='AbortError'?'录入请求超时，尚未确认保存结果。':error instanceof TypeError?'连接中断，尚未收到录入结果。':error.message};
    } finally {
      clearTimeout(timer);ui.ingestBusy=false;ui.epoch++;ui.cache={};render();
    }
  }
  async function search() {
    const epoch=ui.epoch,query=ui.searchQuery,strategy=ui.strategy;ui.searchBusy=true;ui.hits=null;ui.searchError='';render();
    try {
      const data=ui.mode==='sample'?{hits:ui.searchQuery.includes('包装')?[sampleChunks.find(row=>row.id===104)].map(row=>({...row,question:row.questions,score:null,rerank_score:null})):[]}:await request('/api/kb/search',{q:ui.searchQuery,strategy:ui.strategy,top_k:5});
      if(epoch===ui.epoch&&query===ui.searchQuery&&strategy===ui.strategy)ui.hits=data.hits;
    } catch(error){if(epoch===ui.epoch&&query===ui.searchQuery&&strategy===ui.strategy)ui.searchError=error.message;}
    finally {if(epoch===ui.epoch){ui.searchBusy=false;render();}}
  }
  function onSubmit(event) {
    if(actions.onSubmit(event)||reports.onSubmit(event)||classification.onSubmit(event))return true;
    if(workflows.onSubmit(event))return true;
    if(!['data-preview-form','data-ingest-form','data-vector-form','data-search-form','data-inventory-form'].includes(event.target.id))return false;
    event.preventDefault();
    if(event.target.id==='data-inventory-form'){ui.query=ui.queryDraft.trim();ui.queryDraft=ui.query;ui.page=1;render();}
    else if(event.target.id==='data-preview-form'){if(!ui.previewBusy&&!operationBusy())preview();}
    else if(event.target.id==='data-ingest-form')ingest();
    else if(event.target.id==='data-vector-form')startVector();
    else if(!ui.searchBusy)search();
    return true;
  }
  const actions=window.createMinihelpActions({...h,ui,request,resource});
  const workflows=window.createMinihelpWorkflows({...h,ui,actions,request,resource,loadingOrError,pill,metric,button,panel,table,stamp,listStamp});
  const reports=window.createMinihelpReports({...h,ui,actions,request,resource,loadingOrError,pill,metric,button,panel,table,stamp,listStamp});
  const classification=window.createMinihelpClassification({...h,ui,actions,request,resource,loadingOrError,pill,metric,button,panel,table,stamp,listStamp});
  const pagePlans={overview:{name:'管理总览',icon:'chart',stage:'本轮可体验',text:'按模块展示业务状态、真实读数和需关注事项；样例与实时只读分别标注。'},knowledge:{name:'知识中心',icon:'book',stage:'本轮可体验',text:'全库筛选与分页、完整正文、候选状态与材料核对；原文核对后入库，向量补齐单独确认，读取真实作业状态和库存。'},review:{name:'知识缺口',icon:'search',stage:'本轮可体验',text:'查看原始问题与检索快照，区分 AI 建议、人工确认答案、核准与发布结果。实时审核队列支持分页搜索、可信材料核对、核准发布、驳回与发布重试。'},jobs:{name:'作业中心',icon:'clock',stage:'本轮可体验',text:'登记作业与执行条件、本次状态、既有日志与业务结果入口。展示状态手动切换；实时模式核对后启动或停止登记作业，运行中查询真实状态和日志。'}};
  Object.assign(pagePlans,reports.pagePlans,classification.pagePlans);
  return {hasPage:page=>Object.hasOwn(pageNames,page),title:page=>pageNames[page],label:()=>ui.mode==='sample'?'展示样例':h.state.page==='observability'?'实时数据 · 只读':'实时数据',pagePlans,renderPage,onClick,onInput,onChange,onSubmit,pendingReviews:()=>workflows.reviewCounts().pending??''};
};
