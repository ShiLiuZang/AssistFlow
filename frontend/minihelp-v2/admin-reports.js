/* Saved reports and confirmed RAG evaluation. Sample fixtures remain separate from live responses. */
window.createMinihelpReports = function(h) {
  'use strict';
  const {esc,icon,pill,metric,panel,table,stamp,listStamp,modal,render,go,ui,resource,loadingOrError}=h;
  const strategyNames={vector:'纯向量',bm25:'BM25',hybrid:'混合检索',hybrid_rerank:'混合 + 重排'};
  const reportUI={qualityTab:'comparison',observationTab:'cost',metric:'mrr',generationStrategy:'hybrid_rerank',strategy:'all',outcome:'all',query:'',trendMetric:'mrr'};
  const trial={query:'',strategy:'vector',topK:5,rewrite:false,split:false,busy:false,result:null,time:null,error:'',version:0,controller:null,epoch:ui.epoch};
  const sampleCases=[
    {id:'oral_shipping',query:'退货寄回去谁出钱',groups:[['退货退款政策 / 退换货运费承担']],should_refuse:false,expected_terms:['买家','质量']},
    {id:'multi_return',query:'无理由退货有什么条件，寄回去运费谁出',groups:[['退货退款政策 / 无理由退货 / 适用范围'],['退货退款政策 / 退换货运费承担']],should_refuse:false,expected_terms:['7','买家']},
    {id:'refund_timing',query:'退款是不是一定三天到账',groups:[['退货退款政策 / 无理由退货 / 退款时效']],should_refuse:false,expected_terms:['支付渠道','不']},
    {id:'sample_absent',query:'能替我承诺这笔退款今天到账吗？',groups:[],should_refuse:true,expected_terms:[]}
  ];
  const sampleAnswers=['非质量问题由买家承担寄回运费，质量问题按售后政策核对。','签收后 7 天内需满足商品完好等条件；非质量问题寄回运费由买家承担。','退款到账时间取决于支付渠道，不承诺一定三天到账。','现有通用知识不足以承诺单笔退款到账时间，请联系人工查询。'];
  const finite=value=>typeof value==='number'&&Number.isFinite(value);
  const decimal=(value,missing='—')=>finite(value)?value.toFixed(3):missing;
  const percent=(value,missing='—')=>finite(value)?(value*100).toFixed(1)+'%':missing;
  const name=value=>strategyNames[value]||value||'未标注';
  const reportAction=(label,action,extra='',cls='')=>`<button class="btn ${cls}" data-report-action="${action}" ${extra}>${label}</button>`;
  const note=(text,alert=false)=>`<div class="notice report-note ${alert?'amber':''}" ${alert?'role="alert"':''}>${esc(text)}</div>`;
  const subnav=(kind,tabs,active)=>`<nav class="section-tabs" aria-label="${kind==='quality'?'RAG 质量':'观测与成本'}子页面">${tabs.map(([key,label])=>`<button data-report-tab="${kind}:${key}" class="${active===key?'active':''}" aria-current="${active===key?'page':'false'}">${label}</button>`).join('')}</nav>`;
  function empty(title,description) {
    return `<div class="data-empty-state"><span>${icon('file')}</span><h2>${esc(title)}</h2><p>${esc(description)}</p>${reportAction('查看运行说明','guide')}</div>`;
  }
  function reportMeta(items) {
    return `<div class="report-meta">${items.map(([label,value])=>`<span>${esc(label)}<strong>${esc(value==null?'—':value)}</strong></span>`).join('')}</div>`;
  }
  function makeSampleReport(generation=true,partial=false) {
    const details=[];
    const ranks={vector:[2,3,0],bm25:[1,1,2],hybrid:[1,2,1],hybrid_rerank:[1,1,1]};
    Object.keys(strategyNames).forEach(strategy=>sampleCases.forEach((item,index)=>{
      const hits=[], rank=ranks[strategy][index]||0;
      if(rank) {
        for(let i=1;i<rank;i++)hits.push({section_path:'配送说明 / 一般说明',question:'一般配送说明',answer:'请核对订单状态与商品说明。',score:0.45});
        hits.push({section_path:item.groups[0][0],question:item.query,answer:sampleAnswers[index],score:0.82});
        if(index===1&&['hybrid','hybrid_rerank'].includes(strategy))hits.push({section_path:item.groups[1][0],question:'退换货运费承担',answer:sampleAnswers[0],score:0.76});
      }
      const covered=item.groups.filter(group=>hits.some(hit=>group.includes(hit.section_path))).length;
      const first=hits.findIndex(hit=>item.groups.some(group=>group.includes(hit.section_path)));
      const row={id:item.id,query:item.query,strategy,should_refuse:item.should_refuse,error:null,hits,recall:item.groups.length?covered/item.groups.length:null,rr:item.groups.length?(first<0?0:1/(first+1)):null};
      if(generation) {
        row.refused=item.should_refuse?strategy!=='vector':index===2&&strategy==='vector';
        row.answer=row.refused?(item.should_refuse?sampleAnswers[index]:'现有依据不足，请人工核对退款时效。'):sampleAnswers[index];
        row.refusal_correct=row.refused===item.should_refuse;
        row.coverage=item.expected_terms.length?item.expected_terms.filter(term=>row.answer.includes(term)).length/item.expected_terms.length:null;
      }
      if(partial&&strategy==='hybrid_rerank'&&index===2) {
        row.error='ConnectionError';delete row.hits;row.recall=0;row.rr=0;
        if(generation){delete row.answer;delete row.refused;row.refusal_correct=false;row.coverage=0;}
      }
      details.push(row);
    }));
    const summary=Object.fromEntries(Object.keys(strategyNames).map(strategy=>[strategy,summarize(details.filter(row=>row.strategy===strategy),generation)]));
    return {status:'evaluated',created_at:'2026-09-30T10:05:00+08:00',k:5,generation,rewrite:false,split:false,summary,details,dataset:sampleCases};
  }
  function summarize(rows,generation) {
    const relevant=rows.filter(row=>finite(row.recall)), coverage=rows.filter(row=>!row.should_refuse&&finite(row.coverage));
    const average=(list,key)=>list.length?list.reduce((sum,row)=>sum+row[key],0)/list.length:null;
    return {cases:rows.length,answerable_cases:relevant.length,failures:rows.filter(row=>row.error).length,recall_at_k:average(relevant,'recall'),mrr:average(relevant,'rr'),...(generation?{refusal_accuracy:rows.length?rows.filter(row=>row.refusal_correct===true).length/rows.length:null,keyword_coverage:average(coverage,'coverage')}:{})};
  }
  function makeSampleObservation() {
    const rows=[
      {intent:'售后咨询',requests:6,generations:8,input_tokens:8200,output_tokens:1200,unknown_usage:0,unpriced:0,priced_subtotals:{CNY:'0.011200',USD:'0.006300'},price_versions:['样例价格 v1'],estimate_complete:true,duration_samples:8,p95_generation_ms:1820},
      {intent:'商品咨询',requests:4,generations:5,input_tokens:5400,output_tokens:900,unknown_usage:0,unpriced:0,priced_subtotals:{USD:'0.005100'},price_versions:['样例价格 v1'],estimate_complete:true,duration_samples:5,p95_generation_ms:1460},
      {intent:'物流查询',requests:3,generations:2,input_tokens:800,output_tokens:180,unknown_usage:0,unpriced:0,priced_subtotals:{CNY:'0.001800'},price_versions:['样例价格 v1'],estimate_complete:true,duration_samples:2,p95_generation_ms:940}
    ];
    if(ui.scenario==='unpriced')Object.assign(rows[1],{unknown_usage:1,unpriced:2,estimate_complete:false,priced_subtotals:{USD:'0.002600'},duration_samples:4});
    const actualRows=ui.scenario==='empty'?[]:rows;
    const sum=key=>actualRows.reduce((total,row)=>total+row[key],0);
    const cost={status:actualRows.length?'ok':'missing',present:!!actualRows.length,hint:actualRows.length?null:'报表已生成，但输入数据中没有模型调用记录。',schema_version:1,meta:{source:'展示用调用记录（非真实 trace）',generated_at:'2026-09-30T10:10:00+08:00',scope:'provided_generations',pricing_basis:'input_output_only'},rows:actualRows,summary:{requests:sum('requests'),generations:sum('generations'),known_input_tokens:sum('input_tokens'),known_output_tokens:sum('output_tokens'),unknown_usage:sum('unknown_usage'),unpriced:sum('unpriced'),usage_complete:!sum('unknown_usage'),estimate_complete:actualRows.every(row=>row.estimate_complete)}};
    const report=makeSampleReport();
    const runs=['vector','bm25','hybrid_rerank'].map((source,index)=>({id:901+index,dataset_version:'展示固定集 v1',case_ids:sampleCases.map(row=>row.id),config_version:'展示配置 v1',kb_revision:`展示知识修订 ${index+1}`,strategy:'hybrid_rerank',top_k:5,triggered_by:'展示样例',status:'completed',metrics:{...report.summary[source],faithfulness:null,judged_cases:0},details:report.details.filter(row=>row.strategy===source).map(row=>({...row,strategy:'hybrid_rerank'})),created_at:`2026-09-${28+index}T10:00:00+08:00`})).reverse();
    const trend=ui.scenario==='empty'?{status:'missing',present:false,hint:'尚未运行固定集复评。'}:ui.scenario==='partial'?{status:'error',present:false,hint:'展示状态：评测运行记录读取失败，成本和校准报告仍可查看。'}:{status:'ok',present:true,runs:ui.scenario==='single'?[runs[0]]:runs,metric_names:['recall_at_k','mrr','refusal_accuracy','keyword_coverage','faithfulness'],omitted_incomparable:2,hint:'仅比较数据集、题目、策略、配置版本和 K 相同的运行。'};
    const scored=[.71,.78,.84,.9,.22,.35,.45,.62].map((score,index)=>({id:'cal-'+(index+1),split:'calibration',answerable:index<4,score}));
    const scan=[.5,.6,.65,.7,.8].map(threshold=>{const pass_rate=scored.filter(row=>row.answerable&&row.score>=threshold).length/4,leak_rate=scored.filter(row=>!row.answerable&&row.score>=threshold).length/4;return {threshold,pass_rate,leak_rate,youden_j:pass_rate-leak_rate};});
    const distribution=answerable=>{const values=scored.filter(row=>row.answerable===answerable).map(row=>row.score).sort((a,b)=>a-b);return {n:values.length,min:values[0],p25:values[1],p50:values[2],p75:values[2],max:values[3]};};
    const calibration=ui.scenario==='empty'?{status:'missing',present:false,hint:'尚未运行真实校准脚本。'}:{status:'ok',present:true,created_at:'2026-09-30T09:55:00+08:00',dataset_version:'展示独立校准集 v1',in_use:.65,in_sync:false,recommended:scan[3],scan,scored,distribution:{answerable:distribution(true),absent:distribution(false)}};
    return {cost,trend,calibration};
  }
  function sampleResource(key) {
    if(ui.scenario==='error')return {status:'error',error:'展示状态：报告读取失败。读数不可用，不显示为零。'};
    const data=key==='rag'?ui.scenario==='empty'?{status:'not_evaluated',message:'尚未评估'}:makeSampleReport(ui.scenario!=='retrieval',ui.scenario==='partial'):key==='cases'?{cases:sampleCases}:makeSampleObservation();
    return {status:'ready',data,time:null};
  }
  function outcome(row,report) {
    if(row.error)return ['error','调用失败','red'];
    if(report.generation===false)return ['retrieval','仅检索','neutral'];
    if(row.refusal_correct===true)return ['correct','拒答判断符合',''];
    if(row.refusal_correct===false)return ['incorrect','拒答判断不符','amber'];
    return ['unknown','生成未评估','neutral'];
  }
  function reportReady(value) {
    if(value.status==='not_evaluated')return empty('尚未评估','没有已保存的评估报告。固定题集仍可查看；本页不会自动运行评估。');
    if(value.status!=='evaluated'||!value.summary||!Array.isArray(value.details))return empty('报告内容待核对','报告缺少完整的策略汇总或逐题结果，请检查保存报告后重新读取。');
    return null;
  }
  let evaluationTimer=null;
  function evaluationControls() {
    if(ui.mode!=='live')return '';
    const v=resource('evaluationState'),d=v.data;
    if(evaluationTimer===null&&v.status==='ready'&&d.running===true) {
      const epoch=ui.epoch;
      evaluationTimer=setTimeout(async()=>{evaluationTimer=null;if(epoch!==ui.epoch||ui.mode!=='live'||h.state.page!=='quality')return;try{const latest=await h.request('/api/knowledge/evaluation-state');if(epoch!==ui.epoch)return;if(latest.running===false){delete ui.cache.rag;delete ui.cache.admin;}ui.cache.evaluationState={status:'ready',data:latest};}catch(error){if(epoch===ui.epoch)ui.cache.evaluationState={status:'error',error:error.message};}if(epoch===ui.epoch)render();},3000);
    }
    return panel('运行固定题集评估',`<div class="panel-pad"><p class="small muted">${v.status==='ready'?d.running?'评估正在运行；等待真实报告，不推测进度。':'当前没有评估运行。':v.status==='error'?'评估状态暂不可读取；恢复查询后再启动。':'正在读取评估状态…'}旧报告与本次执行分别核对。</p><form id="report-evaluate-form" class="data-table-tools section-gap"><label>top_k <input name="top_k" type="number" min="1" max="50" value="5" required aria-label="评估 top_k"></label><label><input name="generate" type="checkbox">同时生成回答（调用聊天模型）</label><button class="btn primary" type="submit" ${v.status!=='ready'||d.running||ui.actionBusy?'disabled':''}>核对并运行评估</button></form></div>`);
  }
  function qualityPage() {
    const nav=subnav('quality',[['comparison','检索与生成评估'],['results','逐题评估结果'],['dataset','固定题集'],['trial','单题体验']],reportUI.qualityTab)+(reportUI.qualityTab==='trial'?'':evaluationControls());
    if(reportUI.qualityTab==='trial')return nav+trialPage();
    if(reportUI.qualityTab==='dataset')return nav+datasetPage();
    const value=resource('rag'), pending=loadingOrError(value);if(pending)return nav+pending;
    const report=value.data, missing=reportReady(report);if(missing)return nav+missing;
    const summaries=Object.entries(report.summary).filter(([,s])=>s&&typeof s==='object'), best=summaries.filter(([,s])=>finite(s.mrr)).sort((a,b)=>b[1].mrr-a[1].mrr)[0];
    const countValues=[...new Set(summaries.map(([,s])=>s.cases))], caseCount=countValues.length===1?countValues[0]:null;
    const info=reportMeta([['报告生成',report.created_at?.replace('T',' ')],['Top K',report.k],['评估范围',report.generation===true?'检索 + 生成':report.generation===false?'仅检索':'未标注'],['查询改写',report.rewrite==null?'未标注':report.rewrite?'开启':'关闭'],['分句检索',report.split==null?'未标注':report.split?'开启':'关闭']]);
    const totalFailures=report.details.filter(row=>row.error).length;
    const stats=`<div class="stat-strip data-metrics">${metric('评估策略',summaries.length,'种','本报告策略数')}${metric('每策略题数',caseCount,'题',caseCount==null?'各策略题数不同或未标注':'同一报告内的评估题数')}${metric('最佳 MRR',best?decimal(best[1].mrr):null,'',best?name(best[0]):'尚无有效 MRR')}${metric('调用失败记录',totalFailures,'条','按题目 × 策略分别计数')}</div>`;
    return nav+info+stats+(totalFailures?note('存在服务调用失败。失败记录保留在报告汇总中；请结合逐题错误判断读数，不能视为普通零分题目。',true):'')+(reportUI.qualityTab==='results'?resultsPage(report):comparisonPage(report,summaries));
  }
  function comparisonPage(report,summaries) {
    const choices=[['mrr','MRR'],['recall_at_k',`Recall@${report.k??'K'}`]];
    if(!choices.some(([key])=>key===reportUI.metric))reportUI.metric='mrr';
    if(!report.summary[reportUI.generationStrategy])reportUI.generationStrategy=summaries[0]?.[0];
    const selected=report.summary[reportUI.generationStrategy]||{};
    const bars=`<div class="bar-chart" aria-label="策略检索指标">${summaries.map(([strategy,s])=>`<div class="bar-row"><span>${esc(name(strategy))}</span><div class="bar-track">${finite(s[reportUI.metric])?`<span style="width:${Math.max(0,Math.min(100,s[reportUI.metric]*100))}%"></span>`:''}</div><b>${decimal(s[reportUI.metric])}</b></div>`).join('')}<div class="chart-foot">范围 0–1 · 未提供的指标显示 —</div></div>`;
    const chart=panel('策略检索对照',`<div class="panel-toolbar">${choices.map(([key,label])=>`<button class="filter-chip ${reportUI.metric===key?'active':''}" data-report-metric="${key}" aria-pressed="${reportUI.metric===key}">${esc(label)}</button>`).join('')}</div>${bars}`,pill(ui.mode==='sample'?'样例报告':'已保存报告','neutral'));
    const generation=panel('生成与拒答',`<div class="panel-pad"><label class="report-select">查看策略<select id="report-generation-strategy" aria-label="生成指标策略">${summaries.map(([key])=>`<option value="${esc(key)}" ${key===reportUI.generationStrategy?'selected':''}>${esc(name(key))}</option>`).join('')}</select></label><div class="score-row"><span>拒答准确率</span><strong>${percent(selected.refusal_accuracy,'未评估')}</strong></div><div class="score-row"><span>关键词覆盖率</span><strong>${percent(selected.keyword_coverage,'未评估')}</strong></div><p class="field-hint">拒答准确率包含可答与应拒两类题。关键词覆盖仅检查预期词是否出现，不代表忠实度或确认编造率。</p>${report.generation===false?'<p class="field-hint section-gap">本报告仅评估检索，未运行答案生成。</p>':''}</div>`);
    const rows=summaries.map(([strategy,s])=>`<tr><td><strong>${esc(name(strategy))}</strong><span class="table-sub mono">${esc(strategy)}</span></td><td>${percent(s.recall_at_k)}</td><td class="mono">${decimal(s.mrr)}</td><td>${esc(s.answerable_cases??'—')} / ${esc(s.cases??'—')}</td><td>${percent(s.refusal_accuracy,'未评估')}</td><td>${percent(s.keyword_coverage,'未评估')}</td><td>${s.failures?pill(s.failures+' 条','red'):esc(s.failures??'—')}</td><td>${reportAction('逐题查看','strategy-results',`data-strategy="${esc(strategy)}"`)}</td></tr>`);
    return `<div class="report-two-col">${chart}${generation}</div>${panel('策略汇总',table(['检索策略',`Recall@${esc(report.k??'K')}`,'MRR','可答 / 总题数','拒答准确率','关键词覆盖率','调用失败','操作'],rows)+`<p class="data-table-footer">召回率与 MRR 按有标准证据组的可答题平均；库外应拒题不进入召回分母。</p>`)}`;
  }
  function filteredResults(report) {
    return report.details.map((row,index)=>({row,index})).filter(({row})=>(reportUI.strategy==='all'||row.strategy===reportUI.strategy)&&(reportUI.outcome==='all'||outcome(row,report)[0]===reportUI.outcome)&&`${row.query||''} ${row.id||''}`.toLowerCase().includes(reportUI.query.toLowerCase()));
  }
  function resultRows(report) {
    return filteredResults(report).map(({row,index})=>{const result=outcome(row,report);return `<tr><td class="data-content-cell"><strong>${esc(row.query||'未标注问题')}</strong><span class="table-sub mono">${esc(row.id)}</span></td><td>${esc(name(row.strategy))}</td><td>${row.error?'—':percent(row.recall)}<span class="table-sub">RR ${row.error?'—':decimal(row.rr)}</span></td><td>${row.should_refuse===true?'应拒答':row.should_refuse===false?'可回答':'未标注'}</td><td>${pill(result[1],result[2])}${row.error?`<span class="table-sub mono">${esc(row.error)}</span>`:''}</td><td>${reportAction('查看依据','result',`data-index="${index}"`)}</td></tr>`;}).join('')||'<tr><td colspan="6"><div class="empty">本报告内没有符合条件的结果</div></td></tr>';
  }
  function resultsPage(report) {
    const strategies=Object.keys(report.summary);
    const filters=`<div class="panel-toolbar data-toolbar"><div class="data-table-tools"><select id="report-strategy" aria-label="筛选评估策略"><option value="all">全部策略</option>${strategies.map(key=>`<option value="${esc(key)}" ${reportUI.strategy===key?'selected':''}>${esc(name(key))}</option>`).join('')}</select><select id="report-outcome" aria-label="筛选评估结果">${[['all','全部结果'],['error','调用失败'],['incorrect','拒答判断不符'],['correct','拒答判断符合'],['retrieval','仅检索'],['unknown','生成未评估']].map(([key,label])=>`<option value="${key}" ${reportUI.outcome===key?'selected':''}>${label}</option>`).join('')}</select></div><label class="search">${icon('search')}<input id="report-query" aria-label="筛选报告内题目" placeholder="筛选本报告题目" value="${esc(reportUI.query)}"></label></div>`;
    return panel('逐题评估结果',`${filters}<div class="table-wrap"><table class="report-results-table"><thead><tr>${['问题','策略','召回 / 倒数排名','标准判断','执行与生成结果','操作'].map(label=>`<th>${label}</th>`).join('')}</tr></thead><tbody id="report-result-rows">${resultRows(report)}</tbody></table></div><p class="data-table-footer"><span id="report-result-count">当前匹配 ${filteredResults(report).length} / ${report.details.length} 条</span><span>每条记录对应一个题目与一种策略；不是累计问题台账。</span></p>`);
  }
  function datasetPage() {
    const value=resource('cases'),pending=loadingOrError(value);if(pending)return pending;
    const cases=value.data.cases;if(!Array.isArray(cases))return empty('固定题集不可读取','接口未返回题目列表，请检查数据文件后重新读取。');
    const rows=cases.map((row,index)=>`<tr><td class="data-content-cell"><strong>${esc(row.query||'未标注问题')}</strong><span class="table-sub mono">${esc(row.id)}</span></td><td>${row.should_refuse===true?pill('应拒答','amber'):row.should_refuse===false?pill('可回答'):pill('未标注','neutral')}</td><td>${Array.isArray(row.groups)?row.groups.length:'—'} 组</td><td>${esc((row.expected_terms||[]).join('、')||'无预期关键词')}</td><td><div class="form-actions">${reportAction('试问','try-case',`data-index="${index}"`,'soft')}${reportAction('查看标准','case',`data-index="${index}"`)}</div></td></tr>`);
    return note('这里是当前固定题集，可能与旧报告不同。逐题结果中的标准依据仅使用报告保存的题集快照；未保存时显示“未提供”。')+panel('当前固定题集',table(['题目','应答标准','证据组','预期关键词','操作'],rows),pill(cases.length+' 题','neutral'));
  }
  function invalidateTrial() {trial.version++;trial.result=null;trial.time=null;trial.error='';}
  function resetTrial() {invalidateTrial();trial.controller?.abort();trial.controller=null;trial.busy=false;trial.epoch=ui.epoch;}
  function trialPage() {
    if(trial.epoch!==ui.epoch)resetTrial();
    const disabled=trial.busy?'disabled':'';
    return panel('单题体验',`<form id="report-trial-form" class="panel-pad"><label class="field">输入完整问题<textarea id="report-trial-query" required maxlength="2000" rows="3" placeholder="例如：无理由退货有什么条件，寄回去运费谁出？" ${disabled}>${esc(trial.query)}</textarea></label><div class="report-trial-controls"><label>检索策略<select id="report-trial-strategy" ${disabled}>${Object.entries(strategyNames).map(([key,title])=>`<option value="${key}" ${trial.strategy===key?'selected':''}>${title}</option>`).join('')}</select></label><label>Top K<input id="report-trial-k" type="number" min="1" max="50" value="${trial.topK}" required ${disabled}></label><label><input id="report-trial-rewrite" type="checkbox" ${trial.rewrite?'checked':''} ${disabled}>问题改写</label><label><input id="report-trial-split" type="checkbox" ${trial.split?'checked':''} ${disabled}>多诉求拆分</label><button class="btn primary" type="submit" ${disabled}>${trial.busy?'正在检索和生成…':'生成有据回答'}</button></div><p class="field-hint section-gap">${ui.mode==='live'?'点击后使用当前知识库及模型配置；可能调用嵌入、重排和聊天服务。单题结果不改写固定题集评估报告。':'展示模式只提供固定题目的预设答案，不请求真实模型。'}</p><p class="field-hint">可到“固定题集”点击“试问”，载入问题后再生成。</p></form><div id="report-trial-result" class="panel-pad report-trial-output" aria-live="polite">${trialResultView()}</div>`);
  }
  function trialResultView() {
    if(trial.busy)return '<div class="empty" role="status">正在检索和生成，等待真实返回结果…</div>';
    if(trial.error)return `<div class="notice data-alert" role="alert">${esc(trial.error)}</div>`;
    if(!trial.result)return '<div class="empty">等待提问 · 答案与引用会显示在这里</div>';
    const r=trial.result;
    return `<div class="between report-answer-heading"><h3>${r.refused?'证据不足 · 拒答':'生成回答'}</h3>${pill(r.demo?'预设展示样例':r.refused?'已拒答':'实时单题结果',r.refused?'amber':r.demo?'neutral':'')}</div><p class="report-trial-answer">${esc(r.answer)}</p><div class="report-citations">${r.citations.map(hit=>`<details><summary>[${esc(hit.n)}] ${esc(hit.section_path||hit.question||'引用资料')}</summary><div class="preview-text">${esc(hit.answer)}</div></details>`).join('')||'<p class="field-hint">本次未返回引用。请结合拒答状态判断，回答文本本身不代表证据充分。</p>'}</div>`;
  }
  function syncTrial() {const target=document.getElementById('report-trial-result');if(target)target.innerHTML=trialResultView();}
  async function answerTrial() {
    if(trial.busy||ui.actionBusy)return;
    const query=trial.query.trim(),topK=Number(trial.topK);
    if(!query||!Number.isInteger(topK)||topK<1||topK>50){trial.error='请填写完整问题，Top K 必须是 1–50 的整数。';syncTrial();return;}
    invalidateTrial();const version=trial.version,epoch=ui.epoch,mode=ui.mode;
    if(mode==='sample') {
      const index=sampleCases.findIndex(row=>row.query===query);
      if(index<0){trial.error='当前问法没有预设样例。请从固定题集选“试问”，或在实时模式查询。';syncTrial();return;}
      trial.result={answer:sampleAnswers[index],refused:sampleCases[index].should_refuse,citations:[],demo:true};render();return;
    }
    trial.busy=true;const controller=new AbortController();trial.controller=controller;const timer=setTimeout(()=>controller.abort(),90000);render();
    try {
      const response=await fetch('/api/knowledge/answer',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify({query,strategy:trial.strategy,top_k:topK,rewrite:trial.rewrite,split:trial.split})});
      if(!response.ok)throw new Error('单题回答调用失败（HTTP '+response.status+'），请核对数据和模型服务后重试。');
      const result=await response.json();
      if(typeof result.answer!=='string'||typeof result.refused!=='boolean'||!Array.isArray(result.citations)||result.citations.some(hit=>!hit||typeof hit.answer!=='string'))throw new Error('回答或引用数据不完整，请核对接口返回。');
      if(version===trial.version&&epoch===ui.epoch&&mode===ui.mode){trial.result=result;trial.time=new Date().toLocaleTimeString('zh-CN');}
    } catch(error) {if(version===trial.version&&epoch===ui.epoch&&mode===ui.mode)trial.error=error.name==='AbortError'?'等待回答超时，请核对服务后再试；页面没有自动重试。':error.message||'回答请求失败。';}
    finally {clearTimeout(timer);if(trial.controller===controller){trial.busy=false;trial.controller=null;}if(epoch===ui.epoch)render();}
  }
  function evidenceGroups(item) {
    if(!item)return '<p class="field-hint">报告未保存该题的标准证据与预期关键词。</p>';
    return (item.groups||[]).length?`<ol class="report-groups">${item.groups.map(group=>`<li>${group.map(path=>esc(path)).join('<br>')}</li>`).join('')}</ol><p class="field-hint">组内任一路径命中即可覆盖该组；不同组分别计算。</p>`:'<p class="field-hint">没有标准证据组，该题不进入召回率与 MRR 的分母。</p>';
  }
  function showResult(index) {
    const report=resource('rag').data,row=report?.details?.[index];if(!row)return;
    const item=report.dataset?.find(item=>item.id===row.id), result=outcome(row,report);
    const hits=Array.isArray(row.hits)?row.hits.map((hit,i)=>`<article class="report-hit"><div class="between"><strong>${i+1}. ${esc(hit.section_path||'未标注章节')}</strong><span class="mono muted">${finite(hit.score)?decimal(hit.score):'—'}</span></div><p>${esc(hit.question||hit.questions||'')}</p><div class="preview-text">${esc(hit.answer||hit.text||'未提供正文')}</div>${hit.rerank_score!=null?`<p class="field-hint">重排分数 ${decimal(hit.rerank_score)}</p>`:''}</article>`).join('')||'<p class="field-hint">检索执行完成，没有召回内容。</p>':'<p class="field-hint">报告没有保存召回内容，不能视为检索无命中。</p>';
    modal('逐题评估依据',`<div class="data-detail-meta">${pill(name(row.strategy),'neutral')}${pill(result[1],result[2])}${pill(ui.mode==='sample'?'展示样例':'已保存报告','neutral')}</div><h3>${esc(row.query)}</h3>${reportMeta([['题目 ID',row.id],['标准判断',row.should_refuse===true?'应拒答':row.should_refuse===false?'可回答':'未标注'],['召回率',row.error?'调用失败':percent(row.recall)],['RR',row.error?'调用失败':decimal(row.rr)]])}${row.error?note('本次调用失败：'+row.error+'。报告中的默认零分保留，但这里单独标明调用失败。',true):''}<div class="report-detail-grid"><section><h3>标准证据组</h3>${evidenceGroups(item)}<p class="field-hint section-gap">预期关键词：${esc(item?.expected_terms?.join('、')||'未提供')}</p><h3 class="section-gap">本次召回内容</h3>${hits}</section><section><h3>生成回答</h3><div class="preview-text section-gap">${esc(row.answer??(report.generation===false?'本报告仅评估检索，未生成回答。':row.error?'调用失败，未取得生成结果。':'报告未提供生成回答。'))}</div><div class="detail-row"><span>实际拒答</span><span>${row.refused===true?'是':row.refused===false?'否':'未提供'}</span></div><div class="detail-row"><span>拒答判断正确</span><span>${row.error?'调用失败':row.refusal_correct===true?'是':row.refusal_correct===false?'否':'未评估'}</span></div><div class="detail-row"><span>关键词覆盖</span><span>${row.error?'调用失败':percent(row.coverage,'未评估')}</span></div><p class="field-hint section-gap">生成结果与标准判断分开显示。当前只读报告，未创建人工确认或解决记录。</p></section></div>`);
    document.getElementById('modal').classList.add('report-dialog');
  }
  function observationPage() {
    const nav=subnav('observation',[['cost','意图消耗'],['trend','评估趋势'],['calibration','置信度校准']],reportUI.observationTab);
    const value=resource('observation'),pending=loadingOrError(value);if(pending)return nav+pending;
    const data=value.data[reportUI.observationTab];
    if(!data||data.status==='error')return nav+empty('当前报表读取失败',data?.hint||'服务未返回该报表，其他子页可独立查看。');
    if(data.status!=='ok'&&!(reportUI.observationTab==='cost'&&data.meta&&data.summary))return nav+empty(({cost:'尚无成本报表',trend:'尚无可比较评测',calibration:'尚无校准报告'})[reportUI.observationTab],data.hint||'尚未生成对应报告，读数保留为未知。');
    return nav+({cost:costPage,trend:trendPage,calibration:calibrationPage})[reportUI.observationTab](data);
  }
  function prices(row) {
    const entries=Object.entries(row.priced_subtotals||{});
    return entries.length?`<div class="report-prices">${entries.map(([currency,amount])=>`<span class="mono">${esc(currency)} ${esc(amount)}</span>`).join('')}</div>`:'<span class="muted">无已定价小计</span>';
  }
  const count=v=>finite(v)?v.toLocaleString('zh-CN'):'—';
  const reportTime=value=>{if(typeof value!=='string')return '生成时间未标注';if(!/(Z|[+-]\d{2}:\d{2})$/.test(value))return value.replace('T',' ').slice(0,19);const date=new Date(value);return Number.isNaN(date.getTime())?value:new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Singapore',dateStyle:'short',timeStyle:'medium',hour12:false}).format(date)+' (UTC+8)';};
  const tokens=row=>finite(row.input_tokens)&&finite(row.output_tokens)?row.input_tokens+row.output_tokens:null;
  function costPage(data) {
    const summary=data.summary||{},meta=data.meta||{},items=data.rows||[];
    const total=finite(summary.known_input_tokens)&&finite(summary.known_output_tokens)?summary.known_input_tokens+summary.known_output_tokens:null;
    const stats=`<div class="stat-strip data-metrics report-cost-metrics">${metric('请求数',count(summary.requests),'次','按 trace 去重')}${metric('模型生成',count(summary.generations),'次','同一请求可多次调用')}${metric('已知 Token',count(total),'',`输入 ${count(summary.known_input_tokens)} · 输出 ${count(summary.known_output_tokens)}`)}${metric('未定价调用',count(summary.unpriced),'次',`用量未知 ${count(summary.unknown_usage)} 次`)}</div>`;
    const bars=items.map(row=>{const known=tokens(row),share=finite(total)&&total>0&&finite(known)?known/total:null;return `<div class="report-intent-bar"><div class="between"><span><strong>${esc(row.intent)}</strong><small>${count(row.requests)} 次请求 · ${count(row.generations)} 次生成</small></span><b>${share==null?'—':percent(share)} · ${count(known)} Token</b></div><div class="report-token-track" aria-hidden="true"><i style="width:${share==null?0:Math.max(0,Math.min(100,100*share))}%"></i></div></div>`;}).join('')||'<div class="empty">尚无意图用量记录</div>';
    const rows=items.map((row,index)=>`<tr><td><strong>${esc(row.intent)}</strong></td><td>${count(row.requests)}</td><td>${count(row.generations)}</td><td>${count(row.input_tokens)}</td><td>${count(row.output_tokens)}</td><td>${count(row.unknown_usage)} / ${count(row.unpriced)}</td><td>${prices(row)}${row.estimate_complete===false?pill('估算不完整','amber'):''}</td><td>${finite(row.p95_generation_ms)?count(Math.round(row.p95_generation_ms))+' ms':'—'}</td><td>${reportAction('口径','cost',`data-index="${index}"`)}</td></tr>`);
    const info=`<details class="report-cost-notes"><summary>数据来源与估算口径 · ${esc(meta.source||'未标注')} · ${esc(reportTime(meta.generated_at))}</summary><p>范围为报表输入中的已保存生成记录。柱条表示各意图已知输入与输出 Token 之和占已知总量的比例，不含未知用量。</p><p>费用按币种分别展示，不跨币种相加；只按已知用量与配置价格估算，不代表实际账单或缓存计费。</p><p>${esc(data.hint||'生成 P95 仅表示有耗时记录的模型生成时间，不是整轮响应时间。')}缺失读数显示 —。</p></details>`;
    return '<div class="report-cost-view">'+stats+panel('按意图的已知 Token 分布',`<div class="panel-pad">${bars}</div>`,pill(summary.usage_complete===false?'部分用量未知':'已知用量分布',summary.usage_complete===false?'amber':'neutral'))+panel('调用消耗明细',`<div class="report-cost-table">${table(['意图','请求','生成','输入 Token','输出 Token','未知 / 未定价','费用估算','生成 P95','操作'],rows)}</div>${info}`,summary.estimate_complete===true?pill('估算完整'):summary.estimate_complete===false?pill('估算不完整','amber'):pill('完整性未知','neutral'))+'</div>';
  }
  function trendMetricOptions(runs) {
    const options=[['mrr','MRR'],['recall_at_k','召回率'],['refusal_accuracy','拒答准确率'],['keyword_coverage','关键词覆盖率']];
    if(runs.some(row=>finite(row.metrics?.faithfulness)))options.push(['faithfulness','忠实度']);
    return options;
  }
  function trendChart(runs,key) {
    const rows=[...runs].sort((a,b)=>String(a.created_at).localeCompare(String(b.created_at))),left=48,right=612,top=20,bottom=145;
    const x=i=>rows.length===1?(left+right)/2:left+(right-left)*i/(rows.length-1), y=value=>bottom-Math.max(0,Math.min(1,value))*(bottom-top);
    const segments=[];let segment=[];
    rows.forEach((row,i)=>{const value=row.metrics?.[key];if(finite(value))segment.push(`${x(i)},${y(value)}`);else {if(segment.length>1)segments.push(segment.join(' '));segment=[];}});if(segment.length>1)segments.push(segment.join(' '));
    const points=rows.map((row,i)=>{const value=row.metrics?.[key];return finite(value)?`<circle cx="${x(i)}" cy="${y(value)}" r="4"><title>${esc('RUN-'+row.id+'：'+decimal(value))}</title></circle><text class="report-point-label" x="${x(i)}" y="${y(value)-10}" text-anchor="middle">${decimal(value)}</text>`:'';}).join('');
    return `<div class="report-trend-chart"><svg viewBox="0 0 660 183" role="img" aria-label="${esc(trendMetricOptions(runs).find(([id])=>id===key)?.[1]||key)} 可比较运行记录，范围零到一">${[0,.5,1].map(value=>`<line x1="${left}" x2="${right}" y1="${y(value)}" y2="${y(value)}"/><text x="34" y="${y(value)+4}" text-anchor="end">${value.toFixed(1)}</text>`).join('')}${segments.map(points=>`<polyline points="${points}"/>`).join('')}${points}${rows.map((row,i)=>`<text x="${x(i)}" y="171" text-anchor="middle">${esc('RUN-'+row.id)}</text>`).join('')}</svg><p class="field-hint">${rows.length===1?'只有一次可比较运行，仅展示单点读数。':`当前 ${rows.length} 次可比较运行，按记录时间排列。缺失指标不补零，也不连接缺口。`}</p></div>`;
  }
  function trendPage(data) {
    const runs=data.runs||[],options=trendMetricOptions(runs);if(!runs.length)return empty('尚无可比较运行','本次响应没有提供可比较的评测记录。');
    if(!options.some(([key])=>key===reportUI.trendMetric))reportUI.trendMetric='mrr';
    const latest=runs[0],info=reportMeta([['数据集',latest.dataset_version],['配置版本',latest.config_version],['策略',name(latest.strategy)],['Top K',latest.top_k],['可比较运行',runs.length],['本次省略不可比',data.omitted_incomparable]]);
    const chart=panel('可比较评测记录',`<div class="panel-toolbar">${options.map(([key,label])=>`<button class="filter-chip ${reportUI.trendMetric===key?'active':''}" data-report-trend="${key}" aria-pressed="${reportUI.trendMetric===key}">${label}</button>`).join('')}</div>${trendChart(runs,reportUI.trendMetric)}`,pill(runs.length===1?'单次读数':'可比较记录','neutral'));
    const rows=runs.map((run,index)=>`<tr><td><strong class="mono">RUN-${esc(run.id)}</strong><span class="table-sub">${listStamp(run.created_at)}</span></td><td>${esc(run.kb_revision??'未标注')}</td><td>${pill(run.status==='completed'?'评测完成':run.status==='partial'?'部分完成':run.status||'未知',run.status==='partial'?'amber':'neutral')}</td><td>${percent(run.metrics?.recall_at_k)}</td><td class="mono">${decimal(run.metrics?.mrr)}</td><td>${percent(run.metrics?.refusal_accuracy,'未评估')}</td><td>${percent(run.metrics?.keyword_coverage,'未评估')}</td><td>${esc(run.metrics?.failures??'—')}</td><td>${reportAction('查看运行','run',`data-index="${index}"`)}</td></tr>`);
    return info+note((data.hint||'仅展示服务端判定可比较的运行。')+' 当前接口最多读取最近 10 次运行后筛选，不代表全部历史。')+chart+`<div class="section-gap">${panel('运行明细',table(['运行与时间','知识修订','状态','召回率','MRR','拒答准确率','关键词覆盖','调用失败','操作'],rows))}</div>`;
  }
  function calibrationPage(data) {
    const current=data.in_use,recommended=data.recommended?.threshold;
    const sync=data.in_sync===true?'一致':data.in_sync===false?'不一致':'未核对';
    const stats=`<div class="stat-strip data-metrics">${metric('当前运行阈值',finite(current)?current.toFixed(2):null,'','当前服务配置')}${metric('报告推荐阈值',finite(recommended)?recommended.toFixed(2):null,'','独立校准集扫描结果')}${metric('扫描候选',Array.isArray(data.scan)?data.scan.length:null,'个','报告保存的候选值')}${metric('配置核对',sync,'','查看报告不会修改配置')}</div>`;
    const rows=(data.scan||[]).map(row=>`<tr class="${row.threshold===recommended?'report-recommended':''}"><td class="mono">${finite(row.threshold)?row.threshold.toFixed(2):'—'}</td><td>${percent(row.pass_rate)}</td><td>${percent(row.leak_rate)}</td><td class="mono">${decimal(row.youden_j)}</td><td>${row.threshold===recommended?pill('报告推荐'):''}${row.threshold===current?pill('当前值','neutral'):''}</td></tr>`);
    const distributions=['answerable','absent'].map(key=>{const d=data.distribution?.[key]||{};return `<tr><td>${key==='answerable'?'可回答题':'应拒答题'}</td><td>${esc(d.n??'—')}</td>${['min','p25','p50','p75','max'].map(field=>`<td class="mono">${decimal(d[field])}</td>`).join('')}</tr>`;});
    return reportMeta([['报告生成',data.created_at?.replace('T',' ')],['校准数据集',data.dataset_version]])+stats+note('可答题放行率衡量可答题达到阈值的比例；应拒题放行率衡量应拒题达到阈值的比例。放行不等于回答正确。推荐值与当前配置分别显示，页面不应用阈值。',data.in_sync===false)+panel('证据置信度阈值扫描',table(['候选阈值','可答题放行率','应拒题放行率','Youden J','说明'],rows)+`<p class="data-table-footer">Youden J = 可答题放行率 − 应拒题放行率；此处是 RAG 证据阈值，分类器标签阈值另行管理。</p>`,reportAction('查看校准样本','calibration'))+`<div class="section-gap">${panel('两类题目的分数分布',table(['样本类别','数量','最小值','P25','P50','P75','最大值'],distributions))}</div>`;
  }
  function overviewModules() {
    const ragValue=sampleResource('rag'),obsValue=sampleResource('observation'),report=ragValue.data,observation=obsValue.data;
    const base={key:'rageval',title:'RAG 质量',note:'同一份样例报告，按题目与策略保留明细。'};
    let rag;
    if(ragValue.status==='error')rag={...base,status:'error',headline:'评估报告读取失败',metrics:[]};
    else if(report.status!=='evaluated')rag={...base,status:'missing',headline:'尚未生成评估报告',metrics:[]};
    else {
      const summaries=Object.entries(report.summary),best=summaries.sort((a,b)=>b[1].mrr-a[1].mrr)[0];
      rag={...base,status:report.details.some(row=>row.error)?'attention':'ok',headline:`${name(best[0])} 的 MRR 最高：${decimal(best[1].mrr)}`,metrics:[{label:'策略数',value:summaries.length},{label:'每策略题数',value:best[1].cases},{label:'最佳 MRR',value:decimal(best[1].mrr)}]};
    }
    const ready=observation?['cost','trend','calibration'].filter(key=>observation[key].status==='ok').length:null;
    const observability={key:'observability',title:'观测与成本',status:ready==null?'error':ready===0?'missing':ready<3||observation.cost.summary.estimate_complete===false?'attention':'ok',headline:ready==null?'观测报告读取失败':ready===0?'尚无可用报告':`${ready} / 3 类报表可查看`,metrics:ready==null?[]:[{label:'报表可用',value:ready+' / 3'},{label:'生成调用',value:observation.cost.summary.generations}],note:'成本、可比较评测与置信度校准分别判断。'};
    return [rag,observability];
  }
  function onClick(el) {
    if(el.dataset.reportTab){const [kind,key]=el.dataset.reportTab.split(':');if(kind==='quality')reportUI.qualityTab=key;else reportUI.observationTab=key;render();return true;}
    if(el.dataset.reportMetric){reportUI.metric=el.dataset.reportMetric;render();return true;}
    if(el.dataset.reportTrend){reportUI.trendMetric=el.dataset.reportTrend;render();return true;}
    if(!el.dataset.reportAction)return false;
    const action=el.dataset.reportAction,index=Number(el.dataset.index);
    if(action==='strategy-results'){reportUI.qualityTab='results';reportUI.strategy=el.dataset.strategy;reportUI.outcome='all';reportUI.query='';render();}
    else if(action==='try-case'){if(!trial.busy){const item=resource('cases').data?.cases?.[index];if(item){trial.query=item.query;invalidateTrial();reportUI.qualityTab='trial';render();}}}
    else if(action==='result')showResult(index);
    else if(action==='case') {const item=resource('cases').data?.cases?.[index];if(item)modal('固定题目标准',`<h3>${esc(item.query)}</h3>${reportMeta([['题目 ID',item.id],['标准判断',item.should_refuse===true?'应拒答':item.should_refuse===false?'可回答':'未标注']])}<h3>期望证据组</h3>${evidenceGroups(item)}<p class="field-hint section-gap">预期关键词：${esc(item.expected_terms?.join('、')||'无')}</p>`);}
    else if(action==='cost') {const data=resource('observation').data?.cost,row=data?.rows?.[index];if(row)modal('调用与估算口径',`<h3>${esc(row.intent)}</h3>${reportMeta([['请求',row.requests],['生成调用',row.generations],['用量未知',row.unknown_usage],['未定价',row.unpriced],['耗时样本',row.duration_samples]])}<h3>已定价小计</h3><div class="section-gap">${prices(row)}</div><p class="field-hint section-gap">价格版本：${esc(row.price_versions?.join('、')||'未提供')}</p><p class="field-hint section-gap">只有已知用量且已定价的调用进入小计。未知用量不等于零，未定价不等于免费。P95 仅覆盖 ${esc(row.duration_samples??'未知数量的')} 条有耗时记录的生成调用。</p>`);}
    else if(action==='run') {const row=resource('observation').data?.trend?.runs?.[index];if(row){modal('固定集运行明细',`<h3 class="mono">RUN-${esc(row.id)}</h3>${reportMeta([['记录时间',row.created_at?.replace('T',' ')],['数据集',row.dataset_version],['配置版本',row.config_version],['知识修订',row.kb_revision],['触发来源',row.triggered_by]])}<p class="field-hint">题目 ID：${esc(row.case_ids?.join('、')||'未提供')}</p><div class="section-gap">${table(['问题','标准','召回率','RR','生成结果','错误'],(row.details||[]).map(item=>`<tr><td class="data-content-cell">${esc(item.query||item.id)}</td><td>${item.should_refuse?'应拒答':'可回答'}</td><td>${item.error?'调用失败':percent(item.recall)}</td><td>${item.error?'调用失败':decimal(item.rr)}</td><td class="report-answer-cell">${esc(item.answer??'未提供')}</td><td>${esc(item.error||'—')}</td></tr>`))}</div><p class="field-hint section-gap">缺失的忠实度指标未评估；关键词覆盖率不能替代忠实度。</p>`);document.getElementById('modal').classList.add('report-dialog');}}
    else if(action==='calibration') {const data=resource('observation').data?.calibration;if(data)modal('独立校准样本',table(['样本 ID','校准判断','检索置信度'],(data.scored||[]).map(row=>`<tr><td class="mono">${esc(row.id)}</td><td>${row.answerable===true?'可回答':row.answerable===false?'应拒答':'未标注'}</td><td class="mono">${decimal(row.score)}</td></tr>`))+'<p class="field-hint section-gap">分数来自校准报告，不是回答正确率。当前只读，未修改运行阈值。</p>');}
    else if(action==='guide')modal('报告读取与运行说明','<p>页面展示后端已保存的报告；RAG 质量页可核对题集、检索数量和是否生成回答，再确认运行评估。浏览页面不会自动启动评估。</p><p class="field-hint section-gap">观测报告生成与阈值改写没有对应操作接口，本页保持查询。没有报告时保留空状态，读取失败时保留未知读数；进程完成不代替报告中的质量结论。</p>',`<button class="btn" data-action="modal-close">关闭</button><button class="btn soft" data-report-action="jobs">查看作业中心 ${icon('arrow')}</button>`);
    else if(action==='jobs')go('jobs');
    return true;
  }
  function onInput(el) {
    if(el.id==='report-trial-query'){trial.query=el.value;invalidateTrial();syncTrial();return;}
    if(el.id!=='report-query')return;
    reportUI.query=el.value;const report=resource('rag').data;
    document.getElementById('report-result-rows').innerHTML=resultRows(report);
    document.getElementById('report-result-count').textContent=`当前匹配 ${filteredResults(report).length} / ${report.details.length} 条`;
  }
  function onChange(el) {
    const trialKeys={'report-trial-strategy':'strategy','report-trial-k':'topK','report-trial-rewrite':'rewrite','report-trial-split':'split'};
    if(trialKeys[el.id]){trial[trialKeys[el.id]]=el.type==='checkbox'?el.checked:el.value;invalidateTrial();syncTrial();return true;}
    const keys={'report-strategy':'strategy','report-outcome':'outcome','report-generation-strategy':'generationStrategy'};
    if(!keys[el.id])return false;reportUI[keys[el.id]]=el.value;render();return true;
  }
  function onSubmit(event) {
    if(event.target.id==='report-trial-form'){event.preventDefault();answerTrial();return true;}
    if(event.target.id!=='report-evaluate-form')return false;
    event.preventDefault();
    const data=new FormData(event.target);
    h.actions.evaluation(Number(data.get('top_k')),data.get('generate')==='on',()=>{document.getElementById('modal').close();go('quality');});return true;
  }
  function scenarioOptions(page) {
    return page==='quality'?[['normal','检索与生成报告'],['retrieval','仅检索报告'],['empty','尚未评估'],['partial','部分调用失败'],['error','报告读取失败']]:[['normal','完整观测样例'],['single','只有一次评测'],['empty','尚无记录与产物'],['unpriced','费用估算不完整'],['partial','趋势读取失败'],['error','全部读取失败']];
  }
  const pagePlans={quality:{name:'RAG 质量',icon:'shield',stage:'本轮可体验',text:'读取已保存报告，展示检索策略、生成与拒答指标、逐题依据及当前固定题集。区分未评估、仅检索与调用失败。'},observability:{name:'观测与成本',icon:'chart',stage:'本轮可体验',text:'按输入记录展示调用用量与分币种估算，查看可比较评测、当前阈值和报告推荐；三个报表分别处理空与失败状态。'}};
  return {hasPage:page=>page==='quality'||page==='observability',hasResource:key=>['rag','cases','observation'].includes(key),paths:{evaluationState:'/api/knowledge/evaluation-state',rag:'/api/rag-eval/report',cases:'/api/knowledge/cases',observation:'/api/observability/overview'},sampleResource,qualityPage,qualityTime:()=>reportUI.qualityTab==='trial'?trial.time:ui.cache[reportUI.qualityTab==='dataset'?'cases':'rag']?.time,observationPage,scenarioOptions,overviewModules,pagePlans,onClick,onInput,onChange,onSubmit,reset:resetTrial};
};
