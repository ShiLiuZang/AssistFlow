/* Review and registered job operations. Sample actions never call write APIs. */
window.createMinihelpWorkflows = function (h) {
  'use strict';
  const {
    esc,
    icon,
    pill,
    metric,
    panel,
    stamp,
    listStamp,
    modal,
    toast,
    render,
    go,
    ui,
    actions,
    request,
    resource,
    loadingOrError,
  } = h;
  const reviewLabels = {
    pending: '待审',
    publishing: '发布中',
    approved: '已通过',
    rejected: '已驳回',
  };
  const jobLabels = {
    idle: '本次未运行',
    running: '运行中',
    ok: '进程执行完成',
    failed: '进程执行失败',
    stopped: '已停止',
  };
  const sourceLabels = {
    retrieval_low_conf: '检索置信度低',
    self_check: '模型自评不足',
    user_feedback: '用户反馈未解决',
  };
  const materialNames = [
    'returns-policy.md',
    'product-faq.md',
    'after-sales-manual.md',
    'product-specs.md',
    'member-benefits.md',
    'billing-shipping.md',
  ];
  const materialExcerpts = {
    'returns-policy.md':
      '拆开外包装不直接等同于商品已使用，应由客服核对包装现状。请保留产品主机、说明书及全部配件。',
    'product-faq.md': '饮水机滤芯更换需结合使用频率和水质，建议定期检查。',
    'after-sales-manual.md': '物流长时间未更新时，记录最近一次物流信息并联系人工客服核查。',
    'product-specs.md': '选购前核对机身尺寸、摆放空间及宠物体型。',
    'member-benefits.md': '会员权益需核对活动适用范围与订单约定。',
    'billing-shipping.md': '常规现货商品付款后 48 小时内发出，预售以商品说明为准。',
  };
  const reviewSeeds = [
    {
      id: 305,
      question: '拆开外包装后能否申请退货？',
      suggestion: '可能需要结合商品使用情况确认，建议人工核对退换货政策。',
      occurrence_count: 4,
      status: 'pending',
      reviewer: null,
      answer: null,
      source_ref: null,
      created_at: '2026-09-30T09:35:00',
      raws: [
        {
          raw_question: '我把外面的包装拆了，东西没用，还可以退吗？',
          source: 'user_feedback',
          reason: '用户反馈原回复未解决问题',
          created_at: '2026-09-30T09:30:00',
          retrieved_chunks: [
            { question: '退货申请条件', answer: '需核对申请期限、商品状态及配件。', score: 0.56 },
          ],
        },
        {
          raw_question: '拆封了但没用过，能不能退货？',
          source: 'retrieval_low_conf',
          reason: '检索证据不足',
          created_at: '2026-09-30T09:32:00',
          retrieved_chunks: [],
        },
      ],
    },
    {
      id: 304,
      question: '物流超过 48 小时未更新时如何处理？',
      suggestion: '先核对最新物流记录，转人工联系承运方核查。',
      occurrence_count: 2,
      status: 'pending',
      reviewer: null,
      answer: null,
      source_ref: null,
      created_at: '2026-09-30T09:20:00',
      raws: [
        {
          raw_question: '物流两天没动了，需要我找快递吗？',
          source: 'self_check',
          reason: '模型自评依据不充分',
          created_at: '2026-09-30T09:18:00',
          retrieved_chunks: null,
        },
      ],
    },
    {
      id: 303,
      question: '退货时需要寄回全部配件吗？',
      suggestion: '请保留并寄回产品及全部配件。',
      occurrence_count: 3,
      status: 'publishing',
      reviewer: '展示审核员',
      answer: '请保留产品主机、说明书及全部配件，寄回前由客服核对清单。',
      source_ref: 'returns-policy.md',
      publish_error: 'MilvusException',
      reviewed_at: '2026-09-30T09:12:00',
      created_at: '2026-09-30T09:00:00',
      raws: [
        {
          raw_question: '退货要把说明书也一起寄回吗？',
          source: 'retrieval_low_conf',
          reason: '配件要求未被完整召回',
          created_at: '2026-09-30T08:58:00',
          retrieved_chunks: [],
        },
      ],
    },
    {
      id: 302,
      question: '常规现货订单多久发出？',
      suggestion: '请结合商品说明核对发货时效。',
      occurrence_count: 2,
      status: 'approved',
      reviewer: '展示审核员',
      answer: '常规现货付款后 48 小时内发出，预售以商品说明为准。',
      source_ref: 'billing-shipping.md',
      reviewed_at: '2026-09-30T08:50:00',
      created_at: '2026-09-30T08:40:00',
      raws: [
        {
          raw_question: '今天买的现货什么时候寄？',
          source: 'user_feedback',
          reason: '需要明确发货依据',
          created_at: '2026-09-30T08:38:00',
          retrieved_chunks: [],
        },
      ],
    },
    {
      id: 301,
      question: '这个订单今天能否到账退款？',
      suggestion: '需要查询具体售后单与支付渠道。',
      occurrence_count: 1,
      status: 'rejected',
      reviewer: '展示审核员',
      answer: null,
      source_ref: null,
      reviewed_at: '2026-09-30T08:30:00',
      created_at: '2026-09-30T08:20:00',
      raws: [
        {
          raw_question: '我的退款今天会到账吗？',
          source: 'user_feedback',
          reason: '单笔订单问题，不宜直接转为通用知识',
          created_at: '2026-09-30T08:18:00',
          retrieved_chunks: null,
        },
      ],
    },
  ];
  // Registration metadata matches the current project's app/core/jobs.py.
  const jobSeeds = [
    ['kb-preview', '材料清单与切块预览', '本地运行，不写库', false],
    ['kb-build', '离线建库（文档切块 → pending）', '需要 MySQL', false],
    ['kb-vectorize', '向量化（嵌入 → Milvus → done）', '需要 MySQL、嵌入服务和 Milvus', false],
    ['finetune-golden', '黄金样例校验', '需要聊天模型', false],
    ['finetune-corpus', '构建主题语料', '需要 MySQL 与聊天模型', true],
    ['finetune-dataset', '划分与增强数据集', '需要主题语料与聊天模型', true],
    ['finetune-train', '训练分类器', '需要 ml 依赖和训练数据', true],
    ['finetune-eval', '测试集评测', '需要 ml 依赖和训练权重', true],
    ['finetune-export', '导出 ONNX', '需要 ml 依赖和训练权重', true],
    ['finetune-threshold-scan', '重演阈值扫描', '需要验证集与分类服务', true],
    ['classifier-up', '启动分类服务', '需要 ONNX 产物与 ml 依赖', false],
    ['classify-pool', '批量归类问题池', '需要 MySQL 与分类服务', true],
    ['classify-pool-force', '强制归类小批次', '需要 MySQL 与分类服务', true],
    ['classify-history', '归类历史用户提问（隔离库）', '需要历史会话与分类服务，不改业务表', true],
  ];
  let reviews = structuredClone(reviewSeeds),
    jobs = makeJobs(),
    detailToken = 0;
  const publishedSamples = [];
  const wf = {
    reviewFilter: 'pending',
    reviewQuery: '',
    reviewDraft: '',
    page: 1,
    size: 20,
    jobFilter: 'all',
    jobGroup: 'all',
    jobQuery: '',
    reviewId: null,
    jobName: null,
    answer: '',
    source: '',
    outcome: 'success',
    formError: '',
    draftId: null,
  };
  let jobTimer = null,
    materialToken = 0;
  function reviewResource() {
    const params = new URLSearchParams({ page: wf.page, size: wf.size, q: wf.reviewQuery });
    if (wf.reviewFilter !== 'all')
      params.set(
        'status',
        { pending: '待审', publishing: '发布中', approved: '通过', rejected: '驳回' }[
          wf.reviewFilter
        ],
      );
    if (ui.mode === 'live') return resource('reviews:' + params, '/api/review/queue?' + params);
    const value = resource('reviews');
    if (value.status !== 'ready') return value;
    const items = reviewRowsData(value.data),
      total = items.length,
      pages = Math.max(1, Math.ceil(total / wf.size));
    const page = Math.min(wf.page, pages);
    return {
      ...value,
      data: {
        items: items.slice((page - 1) * wf.size, page * wf.size),
        total,
        page,
        size: wf.size,
        pages,
      },
    };
  }
  function reviewRowsData(data) {
    return (data.items || []).filter(
      (row) =>
        (wf.reviewFilter === 'all' || row.status === wf.reviewFilter) &&
        `${row.question || row.normalized_question} ${row.answer || ''} ${row.source_ref || ''}`
          .toLowerCase()
          .includes(wf.reviewQuery.toLowerCase()),
    );
  }
  function makeJobs() {
    return jobSeeds.map(([name, title, needs, heavy]) => ({
      name,
      title,
      needs,
      heavy,
      status:
        name === 'kb-preview' || name === 'kb-build'
          ? 'ok'
          : name === 'kb-vectorize'
            ? 'failed'
            : name === 'finetune-corpus'
              ? 'running'
              : 'idle',
      pid: null,
      started_at: ['kb-preview', 'kb-build', 'kb-vectorize', 'finetune-corpus'].includes(name)
        ? '2026-09-30T09:00:00'
        : null,
      finished_at: ['kb-preview', 'kb-build', 'kb-vectorize'].includes(name)
        ? '2026-09-30T09:02:00'
        : null,
      returncode:
        name === 'kb-vectorize' ? 1 : name === 'kb-preview' || name === 'kb-build' ? 0 : null,
      log_mtime: ['kb-preview', 'kb-build', 'kb-vectorize', 'finetune-corpus'].includes(name)
        ? '2026-09-30T09:02:00'
        : name === 'finetune-eval'
          ? '2026-09-29T14:30:00'
          : null,
      log:
        name === 'kb-preview'
          ? '[展示日志] 读取材料清单\n[展示日志] 完成切块预览，未写入数据库。'
          : name === 'kb-build'
            ? '[展示日志] 原文已保存，等待向量化。'
            : name === 'kb-vectorize'
              ? '[展示日志] 原文已保留。\n[展示日志] 向量库不可连接，本次进程失败。\n[展示日志] 检查依赖后，可重新补齐向量。'
              : name === 'finetune-corpus'
                ? '[展示日志] 正在构建主题语料，等待结果。'
                : name === 'finetune-eval'
                  ? '[展示历史日志] 这是既有日志样例，不代表本次服务已执行评测。'
                  : '',
    }));
  }
  function sampleRows() {
    return ui.scenario === 'empty' ? [] : reviews;
  }
  function sampleJobs() {
    return ui.scenario === 'empty'
      ? jobs.map((row) => ({
          ...row,
          status: 'idle',
          pid: null,
          started_at: null,
          finished_at: null,
          returncode: null,
          log_mtime: null,
          log: '',
        }))
      : ui.scenario === 'offline'
        ? jobs.map((row) =>
            row.name === 'kb-vectorize' ? { ...row, status: 'failed', returncode: 1 } : row,
          )
        : jobs;
  }
  function counts() {
    if (ui.scenario === 'error')
      return { pending: null, publishing: null, approved: null, rejected: null };
    const out = { pending: 0, publishing: 0, approved: 0, rejected: 0 };
    sampleRows().forEach((row) => {
      if (row.status in out) out[row.status]++;
    });
    return out;
  }
  function sampleResource(key) {
    if (ui.scenario === 'error')
      return {
        status: 'error',
        error:
          key === 'reviews'
            ? '审核记录暂时无法读取，请检查数据服务后刷新。'
            : '作业状态暂时无法读取，请检查后台服务后刷新。',
      };
    return {
      status: 'ready',
      data: key === 'reviews' ? { items: sampleRows() } : { jobs: sampleJobs() },
      time: null,
    };
  }
  function reviewPill(status) {
    return pill(
      reviewLabels[status] || status || '未知',
      status === 'pending' || status === 'publishing'
        ? 'amber'
        : status === 'rejected'
          ? 'neutral'
          : '',
    );
  }
  function jobPill(status) {
    return pill(
      jobLabels[status] || status || '未知',
      status === 'failed'
        ? 'red'
        : status === 'running'
          ? 'blue'
          : status === 'idle' || status === 'stopped'
            ? 'neutral'
            : '',
    );
  }
  function group(row) {
    return row.name.startsWith('kb-')
      ? '知识处理'
      : row.name.startsWith('classif')
        ? '归类与服务'
        : '训练与评测';
  }
  function reviewCounts() {
    if (ui.mode === 'sample') return counts();
    const card = resource('admin').data?.modules?.find((row) => row.key === 'review');
    return Object.fromEntries(
      Object.entries(reviewLabels).map(([key, label]) => [
        key,
        card?.status === 'error'
          ? null
          : (card?.metrics?.find((row) => row.label === (key === 'pending' ? '待审' : label))
              ?.value ?? null),
      ]),
    );
  }
  function reviewMetrics() {
    const c = reviewCounts();
    return `<div class="stat-strip data-metrics">${metric('待审', c.pending, '条', '等待人工核对依据')}${metric('发布中', c.publishing, '条', '核准已保存，等待完成发布')}${metric('已通过', c.approved, '条', '审核及发布已完成')}${metric('已驳回', c.rejected, '条', '保留记录，不新增知识')}</div>`;
  }
  function reviewRows(data) {
    return (data.items || []).map(
      (row) =>
        `<tr><td class="data-content-cell"><strong>${esc(row.question || row.normalized_question)}</strong><span class="table-sub">#${esc(row.id)} · AI 建议需人工核对</span></td><td>${esc(row.occurrence_count ?? '—')} 次</td><td>${reviewPill(row.status)}</td><td>${esc(row.source_ref || '待核对可信材料')}</td><td class="data-time-cell">${listStamp(row.created_at)}</td><td>${esc(row.reviewer || '—')}</td><td><button class="table-actions" data-wf-action="review-detail" data-id="${esc(row.id)}">${row.status === 'pending' ? '查看与核对' : '查看结果'} ${icon('arrow')}</button></td></tr>`,
    );
  }
  function reviewPage() {
    const value = reviewResource(),
      stateView = loadingOrError(value);
    const tools = `<div class="panel-toolbar data-toolbar"><div class="data-filters">${Object.entries(
      { all: '全部', ...reviewLabels },
    )
      .map(
        ([key, label]) =>
          `<button class="filter-chip ${wf.reviewFilter === key ? 'active' : ''}" data-wf-review-filter="${key}" aria-pressed="${wf.reviewFilter === key}">${label}</button>`,
      )
      .join(
        '',
      )}</div><form id="wf-queue-form" class="data-table-tools"><label class="search"><input id="wf-review-query" aria-label="搜索完整审核队列" placeholder="搜索问题、答案或材料" maxlength="200" value="${esc(wf.reviewDraft)}"></label><button class="btn" type="submit">搜索</button></form></div>`;
    const d = value.data || {};
    return `${reviewMetrics()}${reviewGuide()}<div class="workflow-scope"><span>${icon('info')}知识缺口来自未解决的问题；候选问答是另一条材料审核队列。</span><button class="text-button" data-wf-action="candidates">查看候选问答 ${icon('arrow')}</button></div>${stateView || panel('完整审核队列', `${tools}<div class="table-wrap"><table class="workflow-review-table"><thead><tr>${['标准问题', '归并频次', '状态', '可信材料', '创建时间', '审核人', '操作'].map((label) => `<th>${label}</th>`).join('')}</tr></thead><tbody id="wf-review-rows">${reviewRows(d).join('') || reviewEmpty(d)}</tbody></table></div><div class="data-table-footer"><span>筛选结果 ${esc(d.total)} 条 · 第 ${esc(d.page)} / ${esc(d.pages)} 页<br>顶部计数为全量统计，搜索覆盖完整队列。</span><div class="data-table-tools"><select id="wf-review-size" aria-label="审核每页条数">${[10, 20, 50].map((n) => `<option ${wf.size === n ? 'selected' : ''}>${n}</option>`).join('')}</select><button class="btn" data-wf-action="review-page" data-page="${d.page - 1}" ${d.page <= 1 ? 'disabled' : ''}>上一页</button><button class="btn" data-wf-action="review-page" data-page="${d.page + 1}" ${d.page >= d.pages ? 'disabled' : ''}>下一页</button></div></div>`, pill(ui.mode === 'sample' ? '样例审核队列' : '核对后操作', 'neutral'))}`;
  }
  function reviewGuide() {
    const gates = [
      ['01', '垃圾过滤', '乱输入、测试或不当言论', '驳回无知识价值的内容'],
      ['02', '时效', '活动截止、单笔订单进度', '不沉淀易过期或仅适用当次的事实'],
      ['03', '频次', '低频冷门、重复已有知识', '先判断是否值得沉淀，再核对通用答案'],
    ];
    return (
      '<div class="wf-review-guide">' +
      panel(
        '飞轮待审 · 人工审核三道关',
        `<div class="wf-review-gates">${gates.map(([no, title, detail, tip]) => `<article><span class="wf-gate-no">${no}</span><h3>${title}</h3><p>${detail}</p><small>${tip}</small></article>`).join('')}</div><p class="field-hint panel-pad wf-review-guide-note">这是人工审核提示。剩余问题需核对可信依据、适用范围和完整答案，确认后再发布；提示不代表后端已自动执行这三项筛选。</p>`,
        pill('审核指引', 'neutral'),
      ) +
      '</div>'
    );
  }
  function reviewEmpty(data) {
    return `<tr><td colspan="7"><div class="empty">${data.items?.length ? '当前记录中没有匹配内容' : '尚无审核记录'}</div></td></tr>`;
  }
  function jobMetrics(value) {
    const rows = value.data?.jobs;
    return `<div class="stat-strip data-metrics">${metric('登记作业', rows?.length, '项', '当前后端登记的作业')}${metric('运行中', rows?.filter((row) => row.status === 'running').length, '项', '本次服务运行状态')}${metric('进程执行完成', rows?.filter((row) => row.status === 'ok').length, '项', '仍需核对业务报告')}${metric('进程执行失败', rows?.filter((row) => row.status === 'failed').length, '项', '按日志检查执行条件')}</div>`;
  }
  function jobRows(data) {
    return (data.jobs || [])
      .filter(
        (row) =>
          (wf.jobFilter === 'all' || row.status === wf.jobFilter) &&
          (wf.jobGroup === 'all' || group(row) === wf.jobGroup) &&
          `${row.name} ${row.title}`.toLowerCase().includes(wf.jobQuery.toLowerCase()),
      )
      .map(
        (row) =>
          `<tr><td class="data-content-cell"><strong>${esc(row.title)}</strong><span class="table-sub">${esc(row.name)} · ${group(row)}</span></td><td class="workflow-needs">${esc(row.needs)}${row.heavy ? '<span class="table-sub">重任务 · 需预留时间与资源</span>' : ''}</td><td>${jobPill(row.status)}${row.status === 'idle' && row.log_mtime ? '<span class="table-sub">有既存日志</span>' : ''}</td><td class="data-time-cell">${listStamp(row.started_at)}</td><td class="data-time-cell">${listStamp(row.finished_at)}</td><td><button class="table-actions" data-wf-action="job-detail" data-name="${esc(row.name)}">查看日志 ${icon('arrow')}</button></td></tr>`,
      );
  }
  function jobPage() {
    const value = resource('jobs'),
      stateView = loadingOrError(value);
    scheduleJobPoll(value);
    const tools = `<div class="panel-toolbar data-toolbar"><div class="data-filters">${Object.entries(
      { all: '全部', ...jobLabels },
    )
      .map(
        ([key, label]) =>
          `<button class="filter-chip ${wf.jobFilter === key ? 'active' : ''}" data-wf-job-filter="${key}" aria-pressed="${wf.jobFilter === key}">${label}</button>`,
      )
      .join(
        '',
      )}</div><div class="data-table-tools"><select id="wf-job-group" aria-label="作业分组">${['all', '知识处理', '训练与评测', '归类与服务'].map((key) => `<option value="${key}" ${wf.jobGroup === key ? 'selected' : ''}>${key === 'all' ? '全部分组' : key}</option>`).join('')}</select><label class="search"><input id="wf-job-query" aria-label="筛选登记作业" placeholder="筛选名称" value="${esc(wf.jobQuery)}"></label></div></div>`;
    return `${jobMetrics(value)}<div class="workflow-scope"><span>${icon('clock')}运行状态属于本次服务；既有日志时间不代表本次执行完成。</span><span>执行完成后，回业务页核对结果</span></div>${stateView || panel('登记作业与本次状态', `${tools}<div class="table-wrap"><table class="workflow-job-table"><thead><tr>${['作业名称', '执行条件', '本次状态', '开始时间', '结束时间', '操作'].map((label) => `<th>${label}</th>`).join('')}</tr></thead><tbody id="wf-job-rows">${jobRows(value.data).join('') || '<tr><td colspan="6"><div class="empty">当前筛选下没有作业</div></td></tr>'}</tbody></table></div><div class="data-table-footer"><span>${ui.mode === 'sample' ? '展示状态可在详情中手动切换；不会执行命令' : '状态与日志来自后台；打开详情核对后启动或停止'}</span><span>不根据耗时推测进度</span></div>`, pill(ui.mode === 'sample' ? '运行样例' : '核对后操作', 'neutral'))}`;
  }
  function show(title, body, footer, key) {
    modal(title, body, footer);
    const dialog = document.getElementById('modal');
    dialog.classList.add('workflow-dialog');
    dialog.dataset.workflowKey = key;
  }
  function stillOpen(key, token, epoch) {
    const dialog = document.getElementById('modal');
    return (
      dialog.open &&
      dialog.dataset.workflowKey === key &&
      detailToken === token &&
      epoch === ui.epoch
    );
  }
  function rawView(raw, index) {
    const chunks = raw.retrieved_chunks;
    return `<article class="workflow-evidence"><div class="between"><strong>原始提问 ${index + 1}</strong>${pill(sourceLabels[raw.source] || raw.source || '来源未标注', 'neutral')}</div><p class="workflow-quote">${esc(raw.raw_question)}</p><div class="small muted">${esc(raw.reason || '未提供原因')} · ${stamp(raw.created_at)}</div><details class="workflow-snapshot"><summary>当时检索快照 ${Array.isArray(chunks) ? `· ${chunks.length} 条` : '· 未记录'}</summary>${chunks == null ? '<p class="muted">未记录快照，无法据此判断当时检索结果。</p>' : !chunks.length ? '<p class="muted">快照为空，当时没有保留命中的知识块。</p>' : chunks.map((chunk) => `<div class="workflow-hit"><strong>${esc(chunk.question || chunk.section_path || '未标注问法')}</strong><p>${esc(chunk.answer || '未提供内容')}</p><span class="small muted">检索分数 ${esc(chunk.score ?? '—')}</span></div>`).join('')}</details></article>`;
  }
  function materialEvidence(source) {
    return `<div class="workflow-material"><span class="small muted">材料摘录 · 展示样例</span><p>${esc(materialExcerpts[source] || '选择材料后，查看对应摘录样例并核对答案。')}</p></div>`;
  }
  async function readMaterial(source) {
    const token = ++materialToken,
      key = 'review-' + wf.reviewId,
      epoch = ui.epoch;
    const target = document.getElementById('wf-material-evidence');
    if (!target) return;
    target.innerHTML = source
      ? '<p role="status">正在读取可信材料…</p>'
      : '<p class="field-hint">选择材料后查看完整原文。</p>';
    if (!source) return;
    try {
      const data = await request('/api/review/materials/' + encodeURIComponent(source));
      if (
        token === materialToken &&
        epoch === ui.epoch &&
        document.getElementById('modal').dataset.workflowKey === key &&
        wf.source === source
      ) {
        const node = document.getElementById('wf-material-evidence');
        if (node)
          node.innerHTML = `<details class="data-source-excerpt" open><summary>完整可信材料 · ${esc(data.file)}</summary><div class="data-detail-text">${esc(data.text)}</div></details><p class="field-hint section-gap">材料 SHA-256 <span class="mono">${esc(data.sha256)}</span></p>`;
      }
    } catch (error) {
      if (token === materialToken && epoch === ui.epoch) {
        const node = document.getElementById('wf-material-evidence');
        if (node)
          node.innerHTML = `<p role="alert">${esc(error.message)}；核准前需重新核对材料。</p>`;
      }
    }
  }
  function reviewBody(row) {
    const pending = row.status === 'pending',
      publishing = row.status === 'publishing',
      editable = pending && (ui.mode === 'sample' || location.pathname.startsWith('/v2/'));
    const checked = publishing || row.status === 'approved';
    const steps = [
      ['问题已归并', true],
      [
        row.status === 'rejected' ? '审核已驳回' : checked ? '人工核准已保存' : '待人工核准',
        checked || row.status === 'rejected',
      ],
      [
        row.status === 'rejected'
          ? '不发布知识'
          : row.status === 'approved'
            ? '知识发布已完成'
            : '待完成发布',
        row.status === 'approved',
      ],
    ];
    return `<div class="workflow-detail-top"><div><span class="mono muted">#${esc(row.id)}</span><h3>${esc(row.question || row.normalized_question)}</h3></div>${reviewPill(row.status)}</div><ol class="workflow-steps">${steps.map(([label, done]) => `<li class="${done ? 'done' : ''}">${icon(done ? 'check' : 'clock')}<span>${label}</span></li>`).join('')}</ol>${publishing ? `<div class="notice workflow-notice">审核记录已保存，发布尚未完成。${row.publish_error ? '发布异常：' + esc(row.publish_error) + '。' : ''}修复依赖后可重试发布，无需重新审核。</div>` : ''}${row.status === 'rejected' ? '<div class="notice workflow-notice">这条记录已驳回，保留审核记录，不新增通用知识。</div>' : ''}<div class="workflow-detail-grid"><section><div class="workflow-section-title"><h3>原始问题与检索依据</h3><span class="small muted">归并 ${esc(row.occurrence_count ?? '—')} 次</span></div>${(row.raws || []).map(rawView).join('') || '<div class="empty">未提供原始问题与检索快照</div>'}</section><section><h3 class="workflow-section-title">答案与可信材料</h3><div class="workflow-suggestion"><span class="small muted">AI 建议 · 尚不能作为核准依据</span><p>${esc(row.suggestion || row.ai_suggested_answer || '尚无 AI 建议')}</p></div>${
      pending
        ? `<form id="wf-review-form"><label class="field">人工确认答案<textarea id="wf-answer" required maxlength="4000" ${editable ? '' : 'readonly'} placeholder="核对可信材料后填写答案">${esc(wf.answer)}</textarea></label><label class="field">可信材料${editable ? `<select id="wf-source" required><option value="">请选择材料</option>${materialNames.map((name) => `<option value="${name}" ${wf.source === name ? 'selected' : ''}>${name}</option>`).join('')}</select>` : `<input readonly value="${esc(row.source_ref || '尚未填写')}">`}</label>${
            editable
              ? `<div id="wf-material-evidence">${ui.mode === 'sample' ? materialEvidence(wf.source) : '<p class="field-hint">选择材料后读取完整可信原文。</p>'}</div>${
                  ui.mode === 'sample'
                    ? `<label class="field small">展示审核结果<select id="wf-review-outcome">${[
                        ['success', '审核通过并完成发布'],
                        ['partial', '审核已保存，发布未完成'],
                        ['conflict', '状态冲突，保留填写内容'],
                      ]
                        .map(
                          ([key, label]) =>
                            `<option value="${key}" ${wf.outcome === key ? 'selected' : ''}>${label}</option>`,
                        )
                        .join('')}</select></label>`
                    : ''
                }`
              : ''
          }<p class="field-hint">${editable ? (ui.mode === 'sample' ? '展示模式仅改变样例；答案不会写入知识库。' : '核准答案必须取自可信材料的连续原文；核对后才提交，后端仍会再次校验。') : '当前页面无法提交，请从后端 /v2/ 入口打开。'}</p><div id="wf-review-error" role="alert" class="workflow-form-error">${esc(wf.formError)}</div></form>`
        : `<div class="workflow-confirmed"><span class="small muted">人工确认答案</span><p>${esc(row.answer || '没有已核准答案')}</p><dl class="workflow-meta"><dt>可信材料</dt><dd>${esc(row.source_ref || '未提供')}</dd><dt>审核人</dt><dd>${esc(row.reviewer || '—')}</dd><dt>审核时间</dt><dd>${stamp(row.reviewed_at)}</dd></dl></div>`
    }</section></div>`;
  }
  function reviewFooter(row) {
    const close = '<button class="btn" data-action="modal-close">关闭</button>';
    if (ui.mode === 'live' && row.status === 'pending')
      return `${close}<button class="btn" data-wf-action="reject-live">核对并驳回</button><button class="btn primary" type="submit" form="wf-review-form">核对并发布</button>`;
    if (ui.mode === 'sample' && row.status === 'pending')
      return `${close}<button class="btn" data-wf-action="reject-sample">演示驳回</button><button class="btn primary" type="submit" form="wf-review-form">演示核准</button>`;
    if (row.status === 'publishing')
      return `${close}<button class="btn soft" data-wf-action="publication-jobs">查看作业中心</button>${ui.mode === 'sample' ? '<button class="btn primary" data-wf-action="publish-sample">演示重试发布</button>' : '<button class="btn primary" data-wf-action="publish-live">核对并重试发布</button>'}`;
    return `${close}${row.status === 'approved' ? '<button class="btn primary" data-wf-action="knowledge">查看知识库存</button>' : ''}`;
  }
  async function openReview(id, preserve = false) {
    wf.reviewId = String(id);
    wf.formError = '';
    wf.outcome = 'success';
    const key = 'review-' + id,
      token = ++detailToken,
      epoch = ui.epoch;
    if (ui.mode === 'sample') {
      const row = sampleRows().find((item) => String(item.id) === String(id));
      if (!row) return;
      wf.answer = row.answer || '';
      wf.source = row.source_ref || '';
      show('审核依据与处理结果', reviewBody(row), reviewFooter(row), key);
      return;
    }
    show(
      '审核依据与处理结果',
      '<div class="empty" role="status">正在读取完整审核记录…</div>',
      '<button class="btn" data-action="modal-close">关闭</button>',
      key,
    );
    try {
      const row = await request('/api/review/' + encodeURIComponent(id));
      if (stillOpen(key, token, epoch)) {
        if (!preserve || wf.draftId !== String(id)) {
          wf.answer = row.answer || '';
          wf.source = row.source_ref || '';
        }
        wf.draftId = String(id);
        show('审核依据与处理结果', reviewBody(row), reviewFooter(row), key);
        if (row.status === 'pending' && wf.source) readMaterial(wf.source);
      }
    } catch (error) {
      if (stillOpen(key, token, epoch))
        show(
          '审核依据与处理结果',
          `<div class="notice" role="alert">${esc(error.message)}</div>`,
          '<button class="btn" data-action="modal-close">关闭</button><button class="btn primary" data-wf-action="reload-review">重新读取</button>',
          key,
        );
    }
  }
  function refreshSampleReview(row) {
    render();
    show('审核依据与处理结果', reviewBody(row), reviewFooter(row), 'review-' + row.id);
  }
  function recordPublished(row) {
    if (!publishedSamples.some((item) => item.id === row.id)) publishedSamples.unshift({ ...row });
  }
  function publishedChunks() {
    return publishedSamples.map((row, index) => ({
      id: 109 + publishedSamples.length - 1 - index,
      questions: row.question,
      answer: row.answer,
      content_type:
        row.source_ref === 'product-faq.md'
          ? 'faq'
          : row.source_ref === 'product-specs.md'
            ? 'spec'
            : row.source_ref === 'after-sales-manual.md'
              ? 'manual'
              : 'policy',
      category: '审核补充',
      section_path: row.source_ref,
      status: 'done',
      is_key_clause: false,
      created_at: row.reviewed_at,
    }));
  }
  function reviewError(message) {
    wf.formError = message;
    document.getElementById('wf-review-error').textContent = message;
  }
  function submitReview() {
    if (ui.mode !== 'sample') return;
    const row = reviews.find((item) => String(item.id) === wf.reviewId);
    if (!row || row.status !== 'pending') {
      reviewError('记录状态已变化，请重新查看，填写内容尚未提交。');
      return;
    }
    if (!wf.answer.trim() || !materialNames.includes(wf.source)) {
      reviewError('请填写人工确认答案，并选择可信材料。');
      return;
    }
    if (wf.outcome === 'conflict') {
      reviewError('展示状态冲突：本次请求未保存。填写内容已保留，请重新核对记录状态。');
      return;
    }
    Object.assign(row, {
      answer: wf.answer.trim(),
      source_ref: wf.source,
      reviewer: '展示审核员',
      reviewed_at: '2026-09-30T10:00:00',
      status: wf.outcome === 'partial' || ui.scenario === 'offline' ? 'publishing' : 'approved',
      publish_error:
        wf.outcome === 'partial' || ui.scenario === 'offline' ? 'MilvusException' : null,
    });
    if (row.status === 'approved') recordPublished(row);
    wf.formError = '';
    refreshSampleReview(row);
    toast(row.status === 'publishing' ? '展示：审核已保存，发布未完成' : '展示：审核与发布已完成');
  }
  function jobResultPage(row) {
    return row.name.startsWith('kb-')
      ? 'knowledge'
      : row.name.startsWith('classify')
        ? 'topics'
        : 'models';
  }
  function jobBody(row) {
    return `<div class="workflow-detail-top"><div><span class="mono muted">${esc(row.name)}</span><h3>${esc(row.title)}</h3></div>${jobPill(row.status)}</div><div class="workflow-job-detail"><section><h3>执行条件与本次状态</h3><p class="muted section-gap">${esc(row.needs)}</p>${row.heavy ? '<p class="small section-gap">重任务，需预留时间与运行资源。</p>' : ''}<dl class="workflow-meta"><dt>开始时间</dt><dd>${stamp(row.started_at)}</dd><dt>结束时间</dt><dd>${stamp(row.finished_at)}</dd><dt>进程 ID</dt><dd>${esc(row.pid ?? '—')}</dd><dt>退出码</dt><dd>${esc(row.returncode ?? '—')}</dd><dt>既有日志更新</dt><dd>${stamp(row.log_mtime)}</dd></dl>${row.status === 'idle' && row.log_mtime ? '<div class="notice section-gap">本次服务尚未运行此作业，但已有日志文件。日志时间不用于推断本次执行结果。</div>' : row.status === 'ok' ? '<div class="notice section-gap">进程已执行完成。请打开业务页，核对库存或报告是否符合预期。</div>' : row.status === 'failed' ? '<div class="notice section-gap">进程执行失败。已完成的业务步骤需单独核对，修复依赖后再决定是否重跑。</div>' : row.status === 'running' ? '<div class="notice section-gap">当前正在运行；后台未提供进度比例，请按日志确认实际执行情况。</div>' : ''}${
      ui.mode === 'sample'
        ? `<label class="field section-gap">切换展示状态<select id="wf-job-state">${Object.entries(
            jobLabels,
          )
            .map(
              ([key, label]) =>
                `<option value="${key}" ${row.status === key ? 'selected' : ''}>${label}</option>`,
            )
            .join(
              '',
            )}</select></label><p class="field-hint">手动切换只用于查看页面效果，不会启动、停止或执行作业。</p>`
        : '<p class="field-hint section-gap">启动和停止需单独核对；失败或停止可能保留部分产物，回结果页核对后再重跑。</p>'
    }</section><section><div class="workflow-section-title"><h3>日志末尾</h3><button class="text-button" data-wf-action="reload-job">刷新日志 ${icon('clock')}</button></div><pre class="workflow-log" tabindex="0" aria-label="作业日志">${esc(row.log || '暂无可读取的日志。')}</pre><p class="field-hint">日志末尾最多 400 行；旧日志与本次运行状态分别判断。</p></section></div>`;
  }
  async function openJob(name) {
    wf.jobName = name;
    const key = 'job-' + name,
      token = ++detailToken,
      epoch = ui.epoch;
    const footer =
      '<button class="btn" data-action="modal-close">关闭</button><button class="btn primary" data-wf-action="job-result">打开结果页</button>';
    if (ui.mode === 'sample') {
      const row = sampleJobs().find((item) => item.name === name);
      if (row) show('作业状态与日志', jobBody(row), footer, key);
      return;
    }
    show(
      '作业状态与日志',
      '<div class="empty" role="status">正在读取作业状态与日志…</div>',
      '<button class="btn" data-action="modal-close">关闭</button>',
      key,
    );
    try {
      const row = await request('/api/jobs/' + encodeURIComponent(name));
      if (stillOpen(key, token, epoch))
        show('作业状态与日志', jobBody(row), ui.mode === 'live' ? jobFooter(row) : footer, key);
    } catch (error) {
      if (stillOpen(key, token, epoch))
        show(
          '作业状态与日志',
          `<div class="notice" role="alert">${esc(error.message)}</div>`,
          '<button class="btn" data-action="modal-close">关闭</button><button class="btn primary" data-wf-action="reload-job">重新读取</button>',
          key,
        );
    }
  }
  async function nextReview() {
    const epoch = ui.epoch;
    try {
      const value =
        ui.mode === 'sample'
          ? { items: sampleRows().filter((row) => row.status === 'pending') }
          : await request(
              '/api/review/queue?status=' + encodeURIComponent('待审') + '&page=1&size=1',
            );
      if (epoch !== ui.epoch) return;
      const row = value.items?.[0];
      if (row) openReview(row.id);
      else toast('当前没有可读取的待审记录');
    } catch (error) {
      if (epoch === ui.epoch) toast(error.message);
    }
  }
  function jobFooter(row) {
    return `<button class="btn" data-action="modal-close">关闭</button><button class="btn soft" data-wf-action="job-result">打开结果页</button>${ui.mode === 'live' && ['idle', 'running', 'ok', 'failed', 'stopped'].includes(row.status) ? `<button class="btn primary" data-wf-action="${row.status === 'running' ? 'job-stop' : 'job-start'}">${row.status === 'running' ? '核对并停止' : '核对并启动'}</button>` : ''}`;
  }
  function stopJobPoll() {
    if (jobTimer !== null) {
      clearTimeout(jobTimer);
      jobTimer = null;
    }
  }
  function scheduleJobPoll(value) {
    if (
      ui.mode !== 'live' ||
      h.state.page !== 'jobs' ||
      value.status !== 'ready' ||
      !value.data.jobs?.some((row) => row.status === 'running')
    ) {
      stopJobPoll();
      return;
    }
    if (jobTimer !== null) return;
    const epoch = ui.epoch;
    jobTimer = setTimeout(async () => {
      jobTimer = null;
      if (epoch !== ui.epoch || ui.mode !== 'live' || h.state.page !== 'jobs' || ui.actionBusy)
        return;
      try {
        const data = await request('/api/jobs');
        if (epoch !== ui.epoch || ui.mode !== 'live' || h.state.page !== 'jobs') return;
        if (!Array.isArray(data.jobs)) throw new Error('作业状态返回不完整。');
        const ended = value.data.jobs.some(
          (row) =>
            row.status === 'running' &&
            data.jobs.find((item) => item.name === row.name)?.status !== 'running',
        );
        if (ended) ui.cache = {};
        ui.cache.jobs = { status: 'ready', data, time: new Date().toLocaleTimeString('zh-CN') };
        render();
        const dialog = document.getElementById('modal'),
          key = 'job-' + wf.jobName;
        if (dialog.open && dialog.dataset.workflowKey === key) {
          const row = await request('/api/jobs/' + encodeURIComponent(wf.jobName));
          if (epoch === ui.epoch && dialog.open && dialog.dataset.workflowKey === key)
            show('作业状态与日志', jobBody(row), jobFooter(row), key);
        }
      } catch (error) {
        if (epoch === ui.epoch) {
          ui.cache.jobs = { status: 'error', error: error.message };
          render();
        }
      }
    }, 3000);
  }
  function onClick(el) {
    if (el.dataset.wfReviewFilter) {
      wf.reviewFilter = el.dataset.wfReviewFilter;
      wf.page = 1;
      render();
      return true;
    }
    if (el.dataset.wfJobFilter) {
      wf.jobFilter = el.dataset.wfJobFilter;
      render();
      return true;
    }
    const action = el.dataset.wfAction;
    if (!action) return false;
    if (action === 'process-live') {
      actions.processReviews(() => {
        document.getElementById('modal').close();
        go('review');
      });
    } else if (action === 'reject-live' || action === 'publish-live') {
      actions.review(
        wf.reviewId,
        action === 'reject-live' ? 'reject' : 'publish',
        wf.answer,
        wf.source,
        () => openReview(wf.reviewId, true),
      );
    } else if (action === 'review-page') {
      wf.page = Number(el.dataset.page);
      render();
    } else if (action === 'review-detail') openReview(el.dataset.id);
    else if (action === 'review-next') nextReview();
    else if (action === 'reload-review') openReview(wf.reviewId, true);
    else if (action === 'job-start' || action === 'job-stop')
      actions.job(wf.jobName, action === 'job-stop', () => openJob(wf.jobName));
    else if (action === 'job-detail') openJob(el.dataset.name);
    else if (action === 'reload-job') openJob(wf.jobName);
    else if (action === 'candidates') {
      ui.tab = 'mining';
      go('knowledge');
    } else if (action === 'publication-jobs') {
      wf.jobGroup = '知识处理';
      wf.jobFilter = 'all';
      go('jobs');
      toast('审核发布仍需在审核详情重试；作业结果需单独核对');
    } else if (action === 'knowledge') {
      ui.tab = 'content';
      go('knowledge');
    } else if (action === 'job-result') {
      const row = resource('jobs').data?.jobs?.find((item) => item.name === wf.jobName);
      if (row) {
        ui.tab = 'index';
        go(jobResultPage(row));
      }
    } else if (action === 'job-guide')
      modal(
        '作业运行流程',
        '<ol class="workflow-guide"><li><strong>先检查执行条件</strong><p>选定登记作业，核对数据库、模型、材料和运行资源。</p></li><li><strong>确认后启动，再追踪状态</strong><p>登记作业均可在详情核对后启动；按后台返回的状态和日志判断进展，同一作业运行中不能重复启动。</p></li><li><strong>回到业务页核对结果</strong><p>进程完成后检查真实库存或报告。失败时保留已完成步骤，检查依赖后再决定是否重跑。</p></li></ol><div class="notice section-gap">本页复用现有白名单作业接口，支持核对后启动与停止，运行中轮询状态和日志。样例详情可手动切换状态。</div>',
      );
    else if (ui.mode === 'sample' && ['reject-sample', 'publish-sample'].includes(action)) {
      const row = reviews.find((item) => String(item.id) === wf.reviewId);
      if (!row) return true;
      if (action === 'reject-sample' && row.status === 'pending') {
        Object.assign(row, {
          status: 'rejected',
          reviewer: '展示审核员',
          reviewed_at: '2026-09-30T10:00:00',
        });
        refreshSampleReview(row);
        toast('展示：已驳回，未新增知识');
      } else if (action === 'publish-sample' && row.status === 'publishing') {
        if (ui.scenario === 'offline') {
          toast('展示：向量库仍离线，发布状态保留');
          return true;
        }
        Object.assign(row, { status: 'approved', publish_error: null });
        recordPublished(row);
        refreshSampleReview(row);
        toast('展示：重试发布已完成');
      }
    }
    return true;
  }
  function onInput(el) {
    if (el.id === 'wf-answer') wf.answer = el.value;
    else if (el.id === 'wf-review-query') wf.reviewDraft = el.value;
    else if (el.id === 'wf-job-query') {
      wf.jobQuery = el.value;
      document.getElementById('wf-job-rows').innerHTML =
        jobRows(resource('jobs').data).join('') ||
        '<tr><td colspan="6"><div class="empty">当前筛选下没有作业</div></td></tr>';
    }
  }
  function onChange(el) {
    if (el.id === 'wf-source') {
      wf.source = el.value;
      if (ui.mode === 'live') readMaterial(wf.source);
      else document.getElementById('wf-material-evidence').innerHTML = materialEvidence(wf.source);
      return true;
    }
    if (el.id === 'wf-review-size') {
      wf.size = Number(el.value);
      wf.page = 1;
      render();
      return true;
    }
    if (el.id === 'wf-review-outcome') {
      wf.outcome = el.value;
      return true;
    }
    if (el.id === 'wf-job-group') {
      wf.jobGroup = el.value;
      render();
      return true;
    }
    if (el.id === 'wf-job-state' && ui.mode === 'sample') {
      if (ui.scenario === 'empty') jobs = sampleJobs();
      ui.scenario = 'normal';
      const row = jobs.find((item) => item.name === wf.jobName);
      if (!row || !(el.value in jobLabels)) return true;
      Object.assign(row, {
        status: el.value,
        pid: null,
        started_at: el.value === 'idle' ? null : '2026-09-30T10:00:00',
        finished_at: ['ok', 'failed', 'stopped'].includes(el.value) ? '2026-09-30T10:02:00' : null,
        returncode: el.value === 'ok' ? 0 : el.value === 'failed' ? 1 : null,
        log_mtime: '2026-09-30T10:02:00',
        log: `[展示日志] 手动切换为：${jobLabels[el.value]}。\n[展示日志] 本操作没有执行作业。`,
      });
      render();
      openJob(row.name);
      return true;
    }
    return false;
  }
  function onSubmit(event) {
    if (event.target.id === 'wf-queue-form') {
      event.preventDefault();
      wf.reviewQuery = wf.reviewDraft.trim();
      wf.page = 1;
      render();
      return true;
    }
    if (event.target.id !== 'wf-review-form') return false;
    event.preventDefault();
    if (ui.mode === 'live')
      actions.review(wf.reviewId, 'approve', wf.answer, wf.source, () =>
        openReview(wf.reviewId, true),
      );
    else submitReview();
    return true;
  }
  function reset() {
    detailToken++;
    materialToken++;
    stopJobPoll();
    wf.reviewId = null;
    wf.jobName = null;
    wf.formError = '';
    document.getElementById('modal').close();
  }
  return {
    hasResource: (key) => key === 'reviews' || key === 'jobs',
    paths: { reviews: '/api/review/queue', jobs: '/api/jobs' },
    sampleResource,
    reviewTime: () => reviewResource().time,
    reviewCounts,
    publishedChunks,
    reviewPage,
    jobPage,
    onClick,
    onInput,
    onChange,
    onSubmit,
    reset,
  };
};
