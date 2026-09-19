
const names={vector:'向量',bm25:'BM25',hybrid:'混合检索',hybrid_rerank:'混合 + 重排'};
function node(tag,text){const e=document.createElement(tag);e.textContent=text;return e;}
async function currentApi(url,body){const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'参数无效，请检查输入');return data;}
function k(){const n=Number($('k').value);if(!Number.isInteger(n)||n<1||n>50)throw Error('Top K 必须为 1 到 50 的整数');return n;}
function render(report){$('scores').replaceChildren();$('records').replaceChildren();if(report.status==='not_evaluated'){$('status').textContent='尚未评测。题集已就绪，运行后查看真实成绩。';return;}
const total=Object.values(report.summary).reduce((a,s)=>a+s.failures,0);$('status').textContent=`真实服务运行记录 · ${report.created_at||''} · K=${report.k} · ${report.generation?'含生成':'仅检索'}\n${total?'存在 '+total+' 次失败，请展开逐题结果检查服务。':'所有调用完成。'}`;
const fmt=v=>v==null?'—':Number(v).toFixed(3);for(const [name,s] of Object.entries(report.summary)){const tr=document.createElement('tr');[names[name]||name,fmt(s.recall_at_k),fmt(s.mrr),`${s.failures} / ${s.cases}`,fmt(s.refusal_accuracy),fmt(s.keyword_coverage)].forEach(v=>tr.append(node('td',v)));$('scores').append(tr);}
for(const row of report.details){const d=document.createElement('details');d.append(node('summary',`${names[row.strategy]} · ${row.query} · ${row.error||'完成'}`));d.append(node('pre',JSON.stringify(row,null,2)));$('records').append(d);}}
async function refresh(){try{render(await currentApi('/api/rag-eval/report'));}catch(e){$('status').textContent=e.message;}}
$('refresh').onclick=refresh;
$('run').onclick=async()=>{try{const top_k=k();$('run').disabled=true;$('refresh').disabled=true;$('busy').hidden=false;$('status').textContent='正在调用真实服务评测，请等待；最多等待 10 分钟。';render(await currentApi('/api/knowledge/evaluate',{top_k,generate:$('generate').checked}));}catch(e){$('status').textContent='评测未完成：'+e.message;}finally{$('run').disabled=false;$('refresh').disabled=false;$('busy').hidden=true;}};
$('ask').onclick=async()=>{try{const query=$('query').value.trim();if(!query)throw Error('请先输入问题');const top_k=k();$('ask').disabled=true;$('answer').textContent='正在检索和生成…';$('citations').replaceChildren();const result=await currentApi('/api/knowledge/answer',{query,strategy:$('strategy').value,top_k,rewrite:$('rewrite').checked,split:$('split').checked});$('answer').textContent=(result.refused?'证据不足 · ':'')+result.answer;for(const hit of result.citations){const d=document.createElement('details');d.append(node('summary',`[${hit.n}] ${hit.section_path||hit.question||'引用资料'}`));d.append(node('pre',hit.answer));$('citations').append(d);}}catch(e){$('answer').textContent='请求失败：'+e.message;}finally{$('ask').disabled=false;}};
async function load(){try{const data=await currentApi('/api/knowledge/cases');$('count').textContent=`/ ${data.cases.length} 题`;for(const c of data.cases){const box=node('div','');box.className='case';box.append(node('strong',c.query));box.append(node('p',c.should_refuse?'应拒答':c.groups.map(g=>g.join(' 或 ')).join(' + ')));const b=node('button','试问');b.className='btn sm';b.onclick=()=>{$('query').value=c.query;$('query').focus();};box.append(b);$('cases').append(box);}}catch(e){$('cases').textContent='题集读取失败：'+e.message;}}
refresh();load();

mountAdminNav("/rag-eval");
$("refreshBtn").onclick=refresh;
