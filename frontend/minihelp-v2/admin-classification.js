/* Topics, classifier reports and explicit single-query inference. Samples never replace live failures. */
window.createMinihelpClassification = function (h) {
  'use strict';
  const {
    esc,
    icon,
    pill,
    metric,
    panel,
    table,
    stamp,
    modal,
    render,
    go,
    ui,
    resource,
    loadingOrError,
  } = h;
  const local = {
    label: '退换货',
    page: 1,
    size: 10,
    modelTab: 'acceptance',
    kind: 'all',
    errorQuery: '',
    trial: 0,
    trialShown: false,
  };
  Object.assign(local, { trialText: '', trialResult: null, trialError: '' });
  const paths = {
    topicCatalog: '/api/topics/catalog',
    topicDistribution: '/api/topics/distribution',
    classifierOverview: '/api/acceptance/overview',
    classifierData: '/api/acceptance/data',
    classifierEval: '/api/acceptance/eval',
    classifierErrors: '/api/acceptance/errors',
    classifierService: '/api/acceptance/service',
  };
  const names = [
    '退换货',
    '物流',
    '尺码',
    '发票',
    '质量问题',
    '运费',
    '优惠活动',
    '价保',
    '支付',
    '订单修改',
    '库存补货',
    '商品信息',
    '保修维修',
    '账号',
    '会员积分',
    '评价',
    '其他',
  ];
  const boundaries = [
    '退货、换货、退款怎么办；修归保修维修，退归这里',
    '货走到哪了、什么时候送到；运费的钱事归运费',
    '大小、码数合不合适',
    '开票、抬头、报销凭证',
    '商品本身的毛病',
    '运费谁出、运费险理赔；管的是钱，货走到哪了归物流',
    '券和活动怎么用、能不能叠',
    '买完降价了补不补差价',
    '付款环节出的问题',
    '下单之后改信息、取消订单',
    '有没有货、什么时候补',
    '材质、功能、用法',
    '保修期限、维修换新；修归这里，退归退换货',
    '登录、绑定、账号安全',
    '会员权益、积分怎么用',
    '评价、晒单的规则',
    '上面都对不上的，先兜底',
  ];
  const catalog = {
    status: 'catalog',
    classes: names.map((label, i) => ({ label, boundary: boundaries[i] })),
  };
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const dec = (v) => (finite(v) ? v.toFixed(4) : '—');
  const pct = (v) => (finite(v) ? (100 * v).toFixed(1) + '%' : '—');
  const num = (v) => (v == null ? '—' : esc(v));
  const source = (v) =>
    ({
      conversation_history: '历史会话隔离归类',
      low_confidence_pool: '低置信问题池',
      retrieval_low_conf: '低置信检索',
      self_check: '回答自检',
      user_feedback: '用户反馈',
      simulated: 'LLM 补造',
      augmented: '训练增强',
      supplement: '定向补数',
      unmarked: '未标注',
    })[v] ||
    v ||
    '未标注';
  const origin = (v) => (v === 'conversation_history' ? '历史真实提问' : source(v));
  const act = (text, action, attrs = '', cls = '') =>
    `<button class="btn ${cls}" data-cls-action="${action}" ${attrs}>${text}</button>`;
  const note = (text, alert = false) =>
    `<div class="notice report-note ${alert ? 'amber' : ''}" ${alert ? 'role="alert"' : ''}>${esc(text)}</div>`;
  const tags = (values) =>
    Array.isArray(values) && values.length
      ? `<div class="tag-row">${values.map((v) => pill(v, 'neutral')).join('')}</div>`
      : '<span class="muted">—</span>';
  const meta = (items) =>
    `<div class="report-meta">${items.map(([k, v]) => `<span>${esc(k)}<strong>${v == null ? '—' : esc(v)}</strong></span>`).join('')}</div>`;
  const status = (v) =>
    pill(
      { pass: '达标', fail: '未达标', missing: '未生成' }[v] || '未知',
      v === 'fail' ? 'red' : v === 'pass' ? '' : 'neutral',
    );
  const health = (v) =>
    v === true
      ? pill('服务在线')
      : v === false
        ? pill('服务离线', 'amber')
        : pill('服务未知', 'neutral');
  const serviceDetail = (v) =>
    v && typeof v === 'object'
      ? v.ok === true
        ? '健康检查通过'
        : JSON.stringify(v)
      : String(v || '').startsWith('ConnectTimeout:')
        ? '连接分类服务超时，请确认推理服务正在运行。'
        : String(v || '').startsWith('ConnectError:')
          ? '无法连接分类服务，请检查服务状态。'
          : v || '未提供';
  const reportMissing = (r) =>
    r?.present === true
      ? null
      : note(
          r?.hint?.startsWith('产物解析失败')
            ? '报告读取失败，请检查保存文件后刷新。'
            : '报告尚未生成；当前页面只读取已有结果。',
          true,
        );
  const time = '2026-09-30T10:20:00+08:00';
  const sampleQuestions = Array.from({ length: 26 }, (_, i) => ({
    question_id: 600 + i,
    text:
      i < 16
        ? `退货申请样例 ${i + 1}：签收后如何申请退货${i % 3 === 0 ? '，寄回运费由谁承担' : ''}？`
        : i < 21
          ? `物流样例 ${i - 15}：订单发货后多久送到？`
          : i < 24
            ? '商品出现故障，能申请维修吗？'
            : '我想了解商品材质与清洗方法。',
    raw_question:
      i < 16
        ? `签收后如何申请退货${i % 3 === 0 ? '，寄回运费由谁承担' : ''}？`
        : i < 21
          ? '发货后多久送到？'
          : i < 24
            ? '商品坏了，能修吗？'
            : '这个用什么材料，怎么洗？',
    labels:
      i < 16
        ? i % 3 === 0
          ? ['退换货', '运费']
          : ['退换货']
        : i < 21
          ? ['物流']
          : i < 24
            ? ['质量问题', '保修维修']
            : ['商品信息'],
    normalized: false,
    source: 'conversation_history',
    occurrence_count: 1,
    review_status: null,
    asked_at: time,
    classified_at: time,
  })).reverse();
  const trials = [
    {
      text: '商品有故障，想申请退货，寄回运费由谁出？',
      labels: ['退换货', '质量问题', '运费'],
      fallback: false,
      scores: [
        ['退换货', 0.92],
        ['质量问题', 0.84],
        ['运费', 0.81],
      ],
    },
    {
      text: '请问可以转人工吗？',
      labels: ['其他'],
      fallback: true,
      scores: [
        ['其他', 0.18],
        ['商品信息', 0.12],
      ],
    },
  ];
  function sampleDistribution() {
    const rows = ui.scenario === 'empty' ? [] : sampleQuestions;
    return {
      source: ui.scenario === 'unmarked' ? null : 'conversation_history',
      total: rows.length,
      latest: rows.length && ui.scenario !== 'unmarked' ? time : null,
      classes: names.map((label) => ({
        label,
        count: rows.filter((r) => r.labels.includes(label)).length,
        samples: rows
          .filter((r) => r.labels.includes(label))
          .slice(0, 3)
          .map((r) => r.text),
      })),
    };
  }
  function sampleEvaluation() {
    const missing = ui.scenario === 'missing',
      offline = ui.scenario === 'offline',
      failed = ui.scenario === 'failed';
    const misses = failed ? 3 : 1;
    const errors = Array.from({ length: misses }, (_, i) => ({
      text:
        i === 0
          ? '商品坏了，想退货，运费能报销吗？'
          : i === 1
            ? '账号登录不上，如何处理？'
            : '购买后降价，怎么申请补差价？',
      gold: i === 0 ? ['退换货', '质量问题', '运费'] : i === 1 ? ['账号'] : ['价保'],
      pred: i === 0 ? ['退换货', '质量问题'] : i === 1 ? ['订单修改'] : ['价保', '优惠活动'],
      missed: i === 0 ? ['运费'] : i === 1 ? ['账号'] : [],
      extra: i === 1 ? ['订单修改'] : i === 2 ? ['优惠活动'] : [],
      kind: i === 0 ? '漏打' : i === 1 ? '错位' : '多打',
      matrix_entries: i === 1 ? 2 : 1,
    }));
    const classes = names.map((name, i) => {
      const support = 10,
        fn = name === '运费' ? 1 : failed && name === '账号' ? 1 : 0,
        fp = failed && ['订单修改', '优惠活动'].includes(name) ? 1 : 0,
        tp = support - fn,
        tn = 34 - support - fp,
        p = tp / (tp + fp),
        r = tp / support,
        f1 = (2 * p * r) / (p + r),
        severity = i < 5 ? '严' : i < 13 ? '中' : '宽',
        red_line = severity === '严' ? 0.9 : severity === '中' ? 0.8 : null;
      return {
        name,
        severity,
        p,
        r,
        f1,
        support,
        red_line,
        passed: red_line == null ? null : f1 >= red_line,
        tn,
        fp,
        fn,
        tp,
      };
    });
    if (failed) {
      const row = classes[0];
      Object.assign(row, { tp: 7, fn: 3, r: 0.7, p: 1, f1: 14 / 17, passed: false });
      errors.push(
        ...Array.from({ length: 3 }, (_, i) => ({
          text: `退换货漏打样例 ${i + 1}：想退掉这件商品。`,
          gold: ['退换货'],
          pred: [],
          missed: ['退换货'],
          extra: [],
          kind: '漏打',
          matrix_entries: 1,
        })),
      );
    }
    const tp = classes.reduce((s, c) => s + c.tp, 0),
      fp = classes.reduce((s, c) => s + c.fp, 0),
      fn = classes.reduce((s, c) => s + c.fn, 0),
      p = tp / (tp + fp),
      r = tp / (tp + fn);
    const ev = {
      present: true,
      ran_at: time,
      test_size: 34,
      origin_counts: { conversation_history: 8, simulated: 26 },
      real_subset: { size: 8, micro_f1: null },
      threshold: 0.5,
      micro: { p, r, f1: (2 * p * r) / (p + r) },
      macro: {
        p: classes.reduce((s, c) => s + c.p, 0) / 17,
        r: classes.reduce((s, c) => s + c.r, 0) / 17,
        f1: classes.reduce((s, c) => s + c.f1, 0) / 17,
      },
      classes,
      total_cells: 34 * 17,
      total_fp: fp,
      total_fn: fn,
      red_line_passed: classes.every((c) => c.passed !== false),
    };
    const scanRows = [
      [0.3, 168, 15, 2],
      [0.5, 167, 3, 3],
      [0.7, 154, 0, 16],
    ].map(([threshold, tp, fp, fn]) => ({
      threshold,
      tp,
      fp,
      fn,
      micro_f1: (2 * tp) / (2 * tp + fp + fn),
    }));
    const scan = {
      present: true,
      ran_at: time,
      val_size: 34,
      best_threshold: 0.5,
      best_micro_f1: scanRows[1].micro_f1,
      in_use_threshold: failed ? 0.4 : 0.5,
      consistent: !failed,
      scan: scanRows,
    };
    const absent = { present: false, hint: '产物还没生成' };
    const service = {
      online: missing || offline ? false : true,
      detail: missing
        ? '推理文件尚未生成'
        : offline
          ? '展示状态：无法连接分类服务'
          : '展示状态：健康检查通过',
      threshold: missing ? null : failed ? 0.4 : 0.5,
      onnx_present: !missing,
    };
    const kinds = {};
    errors.forEach((e) => {
      kinds[e.kind] = (kinds[e.kind] || 0) + 1;
    });
    return {
      evaluation: {
        eval: missing ? absent : ev,
        scan: missing ? absent : scan,
        threshold_in_use: service.threshold,
        classifier: service,
      },
      errors: {
        eval: missing ? absent : { present: true, ran_at: time, test_size: 34, threshold: 0.5 },
        errors: missing ? [] : errors,
        kinds: missing ? {} : kinds,
        matrix_entries: fp + fn,
        total_fp: fp,
        total_fn: fn,
        pairs: failed ? [{ missed: '账号', grabbed: '订单修改', count: 1, severity: '宽' }] : [],
        recipes: {
          漏打: '补充主诉求与顺带诉求同时出现的双标签句。',
          错位: '为容易混淆的类目补充成对的对照句。',
          多打: '补充近似但不属于该类目的反例。',
        },
      },
      service,
    };
  }
  function sampleData() {
    const missing = ui.scenario === 'missing',
      evaluation = sampleEvaluation(),
      present = !missing;
    const file = (path, lines = null) => ({
      path,
      present,
      bytes: present ? 2400 : null,
      mtime: present ? time : null,
      ...(lines != null ? { lines: present ? lines : null } : {}),
    });
    const splits = Object.fromEntries(
      [
        ['train', 182],
        ['val', 34],
        ['test', 34],
      ].map(([key, size]) => [
        key,
        {
          desc: { train: '训练集', val: '验证集', test: '测试集' }[key],
          size: present ? size : 0,
          multi_label: present ? (key === 'train' ? 70 : 14) : 0,
          origins: present ? { simulated: size - 8, conversation_history: 8 } : {},
          counts: present
            ? Object.fromEntries(names.map((n) => [n, key === 'train' ? 20 : 10]))
            : {},
          file: file('展示产物 / dataset / ' + key + '.jsonl', size),
        },
      ]),
    );
    return {
      lineage: [
        ['corpus_raw.jsonl', '原始捞取', 50],
        ['corpus_clean.jsonl', '文本清洗', 24],
        ['corpus_labeled.jsonl', '补充并标注', 250],
      ].map(([f, stage, lines]) => ({
        ...file('展示产物 / ' + f, lines),
        file: f,
        stage,
        desc: stage + '的展示文件',
      })),
      corpus_origins: present ? { conversation_history: 24, simulated: 226 } : {},
      dataset: { splits, leaks: { train_val: 0, train_test: 0, val_test: 0 }, clean: true },
      sample_review: file('展示产物 / sample_review.md'),
      model: {
        trio_ok: present,
        threshold: evaluation.service.threshold,
        threshold_file: file('展示产物 / model / threshold.json'),
        files: present
          ? ['model.safetensors', 'tokenizer.json', 'threshold.json'].map((f) =>
              file('展示产物 / model / ' + f),
            )
          : [],
      },
      onnx: {
        files: present ? [file('展示产物 / onnx / model.onnx')] : [],
        report: present
          ? {
              present: true,
              ran_at: time,
              checked: 34,
              mismatch: 0,
              passed: true,
              opset: 17,
              onnx_path: '展示产物 / onnx / model.onnx',
            }
          : { present: false },
      },
      topic_names: names,
    };
  }
  function sampleAcceptance() {
    const result = sampleEvaluation(),
      missing = ui.scenario === 'missing';
    const titles = [
      '语料与数据集',
      '黄金样例闸',
      '训练产物',
      'ONNX 导出与服务',
      '测试集评测',
      '阈值扫描',
      '混淆矩阵',
      '错例复核',
      '旁路批量归类',
    ];
    const keys = [
      'data',
      'golden',
      'train',
      'export',
      'eval',
      'threshold',
      'matrix',
      'errors',
      'classify',
    ];
    const jobs = [
      ['finetune-corpus', 'finetune-dataset'],
      ['finetune-golden'],
      ['finetune-train'],
      ['finetune-export', 'classifier-up'],
      ['finetune-eval'],
      ['finetune-threshold-scan'],
      ['finetune-eval'],
      ['finetune-eval'],
      ['classify-history'],
    ];
    const headlines = [
      '24 条清洗 → 250 条语料 → 182 / 34 / 34 训练/验证/测试',
      '黄金样例 30 / 30 条集合全对',
      '模型三件套齐全',
      `导出对齐 34 条 · ${result.service.online ? '在线' : '离线'}`,
      `micro-F1 ${dec(result.evaluation.eval.micro?.f1)} · 测试集 34 条`,
      `扫描推荐 0.5 · 文件在用 ${result.service.threshold}`,
      '每类独立统计 TP / FP / FN / TN',
      `${result.errors.errors.length} 条错例 · ${result.errors.matrix_entries} 笔矩阵错误`,
      '26 条展示问题，多个类目可同时命中',
    ];
    const blocks = keys.map((key, i) => ({
      key,
      no: i + 1,
      title: titles[i],
      status: missing
        ? 'missing'
        : (key === 'export' && !result.service.online) ||
            (key === 'eval' && !result.evaluation.eval.red_line_passed) ||
            (key === 'threshold' && !result.evaluation.scan.consistent)
          ? 'fail'
          : 'pass',
      headline: missing ? '相关产物尚未生成' : headlines[i],
      note:
        key === 'matrix' || key === 'errors'
          ? '本项达标表示报告可读，模型质量另看测试集评测。'
          : '样例验收结果；真实结果以接口为准。',
      jobs: jobs[i],
    }));
    return {
      blocks,
      passed: blocks.filter((b) => b.status === 'pass').length,
      total: blocks.length,
      all_pass: blocks.every((b) => b.status === 'pass'),
      classifier: result.service,
    };
  }
  function sampleResource(key) {
    if (ui.scenario === 'error' && key !== 'topicCatalog')
      return { status: 'error', error: '展示状态：查询失败。未知读数显示为 —。' };
    let data;
    if (key === 'topicCatalog') data = catalog;
    else if (key === 'topicDistribution') data = sampleDistribution();
    else if (key.startsWith('topicQuestions:')) {
      const [, label, pageString, sizeString] = key.split(':');
      const rows =
          ui.scenario === 'empty'
            ? []
            : sampleQuestions.filter((r) => r.labels.includes(decodeURIComponent(label))),
        size = Number(sizeString),
        pages = Math.max(1, Math.ceil(rows.length / size)),
        page = Math.min(Number(pageString), pages);
      data = {
        label: decodeURIComponent(label),
        source: ui.scenario === 'unmarked' ? null : 'conversation_history',
        page,
        size,
        pages,
        total: rows.length,
        items: rows
          .slice((page - 1) * size, page * size)
          .map((r) =>
            ui.scenario === 'unmarked'
              ? { ...r, source: null, asked_at: null, classified_at: null }
              : r,
          ),
      };
    } else if (key === 'classifierOverview') data = sampleAcceptance();
    else if (key === 'classifierData') data = sampleData();
    else if (key === 'classifierEval') data = sampleEvaluation().evaluation;
    else if (key === 'classifierErrors') data = sampleEvaluation().errors;
    else data = sampleEvaluation().service;
    return { status: 'ready', data, time: null };
  }
  function questionResource() {
    const label = encodeURIComponent(local.label),
      key = `topicQuestions:${label}:${local.page}:${local.size}`;
    return resource(
      key,
      `/api/topics/questions?label=${label}&page=${local.page}&size=${local.size}`,
    );
  }
  function topicsPage() {
    const cv = resource('topicCatalog'),
      dv = resource('topicDistribution'),
      d = dv.data;
    const catalogue = cv.data?.classes || [],
      counts = new Map((d?.classes || []).map((c) => [c.label, c]));
    const hit = d ? (d.classes || []).filter((c) => finite(c.count) && c.count > 0).length : null;
    const stats = `<div class="stat-strip data-metrics">${metric('已归类问题', d?.total, '条', '分布接口的独立问题数')}${metric('已命中类目', hit, '类', '问题可同时命中多个类目')}${metric('权威类目', cv.status === 'ready' ? catalogue.length : null, '类', '名称与边界来自类目定义')}${metric('最新归类', d?.latest ? d.latest.replace('T', ' ').slice(5, 16) : null, '', '接口返回的归类时间')}</div>`;
    const distributionBody =
      loadingOrError(dv) ||
      `${meta([
        ['分布来源', source(d?.source)],
        ['占比口径', '类目问题数 / 已归类问题数'],
      ])}${note('一个问题可以属于多个类目，各类占比之和可能超过 100%。0 条表示当前没有命中，不代表未分类问题总数。')}`;
    if (cv.status !== 'ready') return stats + distributionBody + loadingOrError(cv);
    if (!catalogue.some((c) => c.label === local.label)) {
      local.label = catalogue[0]?.label || '';
      local.page = 1;
    }
    const aside = `<aside class="panel cls-topic-list"><div class="panel-head"><h2>咨询类目</h2><span class="small muted">${catalogue.length} 类</span></div>${catalogue
      .map((c) => {
        const row = counts.get(c.label),
          ratio =
            finite(row?.count) && finite(d?.total) && d.total > 0 ? row.count / d.total : null;
        return `<button class="cls-topic-button ${local.label === c.label ? 'active' : ''}" data-cls-label="${esc(c.label)}" aria-pressed="${local.label === c.label}"><span>${esc(c.label)}<small>${ratio == null ? '—' : pct(ratio)}</small></span><b>${num(row?.count)}</b><span class="cls-topic-track"><i style="width:${ratio == null ? 0 : Math.min(100, ratio * 100)}%"></i></span></button>`;
      })
      .join('')}</aside>`;
    const selected = catalogue.find((c) => c.label === local.label),
      qv = local.label ? questionResource() : null,
      q = qv?.data;
    const examples = (counts.get(local.label)?.samples || []).slice(0, 3);
    const boundary = `<div class="cls-boundary"><span>类目边界</span><p>${esc(selected?.boundary || '未提供')}</p>${examples.length ? `<details class="cls-examples"><summary>分布中的代表问法 · ${examples.length} 条</summary><ul>${examples.map((text) => `<li>${esc(text)}</li>`).join('')}</ul></details>` : ''}</div>`;
    const body = qv
      ? loadingOrError(qv) ||
        `${meta([
          ['列表来源', source(q.source)],
          ['类目问题', q.total],
          ['分页范围', '所选类目的全部问题'],
        ])}${table(
          ['问题 / 原始问法', '完整标签', '来源 / 审核', '归类时间', '操作'],
          (q.items || []).map(
            (r, i) =>
              `<tr><td class="cls-question"><strong>${esc(r.text || r.raw_question || '未标注文本')}</strong><span class="table-sub">#${esc(r.question_id)} · 出现 ${num(r.occurrence_count)} 次</span></td><td>${tags(r.labels)}</td><td>${esc(source(r.source))}<span class="table-sub">审核：${esc({ pending: '待审', approved: '已通过', rejected: '已驳回', publishing: '发布中' }[r.review_status] || r.review_status || '未提供')}</span></td><td class="data-time-cell">${stamp(r.classified_at)}</td><td><button class="table-actions" data-cls-action="question" data-index="${i}">查看 ${icon('arrow')}</button></td></tr>`,
          ),
        )}<div class="data-table-footer cls-pagination"><span>共 ${num(q.total)} 条 · 第 ${num(q.page)} / ${num(q.pages)} 页</span><label>每页<select id="cls-topic-size" aria-label="每页问题数">${[10, 20, 50].map((s) => `<option value="${s}" ${local.size === s ? 'selected' : ''}>${s} 条</option>`).join('')}</select></label><div>${act('上一页', 'previous', q.page <= 1 ? 'disabled' : '')}${act('下一页', 'next', q.page >= q.pages ? 'disabled' : '')}</div></div>`
      : note('暂无可查询类目。');
    return `${stats}${distributionBody}<div class="cls-topics-layout">${aside}<div>${panel(esc(local.label) + ' · 问题明细', `${boundary}${body}`, pill(ui.mode === 'sample' ? '分页样例' : '服务端分页', 'neutral'))}</div></div>`;
  }
  function modelsPage() {
    const tabs = [
      ['acceptance', '九项验收'],
      ['data', '数据与产物'],
      ['evaluation', '评测与阈值'],
      ['errors', '错例复核'],
      ['trial', '单句试分类'],
    ];
    const views = {
      acceptance: acceptancePage,
      data: dataPage,
      evaluation: evaluationPage,
      errors: errorsPage,
      trial: trialPage,
    };
    return `<nav class="section-tabs" aria-label="分类器管理子页面">${tabs.map(([key, title]) => `<button data-cls-tab="${key}" class="${local.modelTab === key ? 'active' : ''}" aria-current="${local.modelTab === key ? 'page' : 'false'}">${title}</button>`).join('')}</nav><div class="cls-report">${views[local.modelTab]()}</div>`;
  }
  const jobTitles = {
    'finetune-corpus': '构建主题语料',
    'finetune-dataset': '划分与增强数据集',
    'finetune-golden': '黄金样例校验',
    'finetune-train': '训练分类器',
    'finetune-export': '导出 ONNX',
    'classifier-up': '启动分类服务',
    'finetune-eval': '测试集评测',
    'finetune-threshold-scan': '重演阈值扫描',
    'classify-history': '归类历史提问',
    'classify-pool': '批量归类问题池',
    'classify-pool-force': '强制归类小批次',
  };
  function jobButtons(jobs) {
    const buttons = (jobs || []).filter((name) => Object.hasOwn(jobTitles, name));
    return `<div class="cls-job-actions">${buttons.map((name) => act('重跑 ' + jobTitles[name], 'run-job', `data-name="${name}" ${!h.actions.available() ? 'disabled' : ''}`, 'soft')).join('')}</div>${ui.mode === 'sample' && buttons.length ? '<p class="field-hint">展示模式不执行任务，切换实时数据后核对范围并启动。</p>' : ''}`;
  }
  const formatted = (v) => (finite(v) ? v.toLocaleString('zh-CN') : '—');
  function numberBar(value, max = 1, alert = false, precision = true) {
    const width =
      finite(value) && finite(max) && max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
    return `<div class="cls-number-bar ${alert ? 'is-alert' : ''}"><span>${precision ? dec(value) : formatted(value)}</span><div class="cls-bar-track" aria-hidden="true"><i style="width:${width}%"></i></div></div>`;
  }
  function summaryScores(e) {
    return `<div class="cls-score-pair">${[
      ['micro', '所有标签判断汇总'],
      ['macro', '17 类分别计算，再平均'],
    ]
      .map(
        ([key, desc]) =>
          `<article><div class="between"><h3>${key}</h3><small>${desc}</small></div><div class="cls-score-numbers">${[
            ['p', '精确率 P'],
            ['r', '召回率 R'],
            ['f1', 'F1'],
          ]
            .map(
              ([k, title]) =>
                `<div><strong>${dec(e[key]?.[k])}</strong><span>${title}</span></div>`,
            )
            .join('')}</div></article>`,
      )
      .join('')}</div>`;
  }
  function matrices(e) {
    return `<div class="cls-matrices">${(e.classes || [])
      .map(
        (c) =>
          `<article class="cls-matrix"><header class="${(finite(c.fp) && c.fp > 0) || (finite(c.fn) && c.fn > 0) ? 'has-errors' : ''}"><strong>${esc(c.name)}</strong>${pill(c.severity || '档位未标注', c.severity === '严' ? '' : 'neutral')}</header><div>${[
            ['tn', 'TN · 正确排除'],
            ['fp', 'FP · 多打'],
            ['fn', 'FN · 漏打'],
            ['tp', 'TP · 命中'],
          ]
            .map(
              ([key, title]) =>
                `<section class="${key === 'tp' ? 'is-correct' : (key === 'fp' || key === 'fn') && finite(c[key]) && c[key] > 0 ? 'is-error' : ''}"><b>${formatted(c[key])}</b><span>${title}</span></section>`,
            )
            .join('')}</div></article>`,
      )
      .join('')}</div>`;
  }
  function scanBars(s, current) {
    return `<div class="cls-scan-bars">${(s.scan || []).map((row) => `<div class="cls-scan-row ${row.threshold === s.best_threshold ? 'recommended' : ''}"><strong>${finite(row.threshold) ? row.threshold.toFixed(2) : '—'}</strong>${numberBar(row.micro_f1)}<span class="cls-scan-markers">${row.threshold === s.best_threshold ? pill('扫描推荐') : ''}${finite(current) && row.threshold === current ? pill('文件在用', 'neutral') : ''}</span></div>`).join('') || '<div class="empty">没有候选线记录</div>'}</div>`;
  }
  function lineageFlow(d) {
    const splits = d.dataset?.splits || {};
    return `<div class="cls-lineage">${(d.lineage || []).map((f) => `<article><span>${esc(f.stage || '未标注阶段')}</span><strong>${f.present === true ? formatted(f.lines) : '—'}</strong><p>${esc(f.desc || '未提供说明')}</p><small class="mono">${esc(f.file || filename(f.path))}</small></article>`).join('')}<article><span>训练 / 验证 / 测试</span><strong class="cls-split-total">${['train', 'val', 'test'].map((key) => (splits[key]?.file?.present === true ? formatted(splits[key].size) : '—')).join(' / ')}</strong><p>只增强训练集，验证与测试用于留出核对。</p><small class="mono">dataset/*.jsonl</small></article></div>`;
  }
  function distributionTable(d) {
    const splits = d.dataset?.splits || {},
      keys = ['train', 'val', 'test'];
    const maxima = Object.fromEntries(
      keys.map((key) => [
        key,
        Math.max(0, ...Object.values(splits[key]?.counts || {}).filter(finite)),
      ]),
    );
    const labels = d.topic_names || [
      ...new Set(keys.flatMap((key) => Object.keys(splits[key]?.counts || {}))),
    ];
    return table(
      [
        '类目',
        ...keys.map(
          (key) =>
            ({ train: '训练', val: '验证', test: '测试' })[key] +
            ' · ' +
            (splits[key]?.file?.present === true ? formatted(splits[key]?.size) : '—'),
        ),
      ],
      labels.map(
        (label) =>
          `<tr><td>${esc(label)}</td>${keys.map((key) => `<td>${numberBar(splits[key]?.file?.present === true ? splits[key]?.counts?.[label] : null, maxima[key], false, false)}</td>`).join('')}</tr>`,
      ),
    );
  }
  function comparisonTags(values, other, missing) {
    if (!Array.isArray(values) || !values.length) return '<span class="muted">无标签</span>';
    return `<div class="tag-row">${values.map((label) => `<span class="cls-compare-tag ${(other || []).includes(label) ? 'correct' : missing ? 'missed' : 'extra'}">${esc(label)}</span>`).join('')}</div>`;
  }
  function scoreChart(scores, threshold) {
    const rows = [...(scores || [])].sort((a, b) => b.score - a.score);
    return `<div class="cls-probabilities">${rows.map((row) => `<div class="cls-probability-row ${row.hit ? 'hit' : ''}"><strong>${esc(row.label)}</strong><div class="cls-probability-track" aria-hidden="true"><i style="width:${finite(row.score) ? Math.max(0, Math.min(100, row.score * 100)) : 0}%"></i>${finite(threshold) && threshold >= 0 && threshold <= 1 ? `<span class="cls-threshold-line" style="left:${threshold * 100}%"></span>` : ''}</div><b>${dec(row.score)}</b><span>${row.hit ? pill('命中') : ''}</span></div>`).join('')}<p class="field-hint section-gap">分数范围 0–1${finite(threshold) ? `，竖线为判定阈值 ${threshold}` : '，阈值未提供'}；命中标签以服务返回为准，兜底不等于过线。</p></div>`;
  }
  function gateNumbers(key, data, evaluation, errors, overview) {
    const e = evaluation?.eval,
      s = evaluation?.scan,
      splits = data?.dataset?.splits || {};
    const countFile = (file) => (file?.present === true ? formatted(file.lines) : '—');
    const splitSize = (key) =>
      splits[key]?.file?.present === true ? formatted(splits[key].size) : '—';
    const validEval = e?.present === true,
      validScan = s?.present === true;
    const values = {
      data: [
        ['标注语料', countFile(data?.lineage?.find((f) => f.file === 'corpus_labeled.jsonl'))],
        ['训练集', splitSize('train')],
        ['验证 / 测试', splitSize('val') + ' / ' + splitSize('test')],
      ],
      train: [
        [
          '模型三件套',
          data?.model?.trio_ok === true ? '齐全' : data?.model?.trio_ok === false ? '未齐全' : '—',
        ],
        ['文件阈值', data?.model?.threshold ?? '—'],
      ],
      export: [
        [
          '对齐预测',
          data?.onnx?.report?.present === true ? formatted(data.onnx.report.checked) : '—',
        ],
        [
          '不一致',
          data?.onnx?.report?.present === true ? formatted(data.onnx.report.mismatch) : '—',
        ],
        [
          '服务',
          overview?.classifier?.online === true
            ? '在线'
            : overview?.classifier?.online === false
              ? '离线'
              : '—',
        ],
      ],
      eval: [
        ['micro-F1', validEval ? dec(e.micro?.f1) : '—'],
        ['macro-F1', validEval ? dec(e.macro?.f1) : '—'],
      ],
      threshold: [
        ['扫描推荐', validScan ? (s.best_threshold ?? '—') : '—'],
        ['文件在用', evaluation?.threshold_in_use ?? '—'],
      ],
      matrix: [
        ['多打 FP', validEval ? formatted(e.total_fp) : '—'],
        ['漏打 FN', validEval ? formatted(e.total_fn) : '—'],
      ],
      errors: [
        ['错例', errors?.eval?.present === true ? formatted(errors.errors?.length) : '—'],
        ['错误笔数', errors?.eval?.present === true ? formatted(errors.matrix_entries) : '—'],
      ],
    }[key];
    return values
      ? `<div class="cls-gate-numbers">${values.map(([title, value]) => `<div><span>${title}</span><b>${esc(value)}</b></div>`).join('')}</div>`
      : '';
  }
  function acceptancePage() {
    const v = resource('classifierOverview');
    if (v.status !== 'ready') return loadingOrError(v);
    const d = v.data,
      blocks = d.blocks || [],
      data = resource('classifierData').data,
      evaluation = resource('classifierEval').data,
      errors = resource('classifierErrors').data;
    return `<div class="stat-strip data-metrics">${metric('通过验收', d.passed, '/ ' + num(d.total), '后端逐项判定')}${metric('未达标', blocks.filter((b) => b.status === 'fail').length, '项', '产物存在，但验收条件未满足')}${metric('未生成', blocks.filter((b) => b.status === 'missing').length, '项', '缺少所需产物或报告')}${metric('分类服务', d.classifier?.online === true ? '在线' : d.classifier?.online === false ? '离线' : null, '', '独立健康检查')}</div>${note('文件齐全、评测达标与服务在线分别判断。矩阵和错例项达标仅表示报告可读；完整验收需所有项目满足条件。')}${meta(
      [
        [
          '整体验收',
          d.all_pass === true ? '全部达标' : d.all_pass === false ? '尚未全部达标' : '未知',
        ],
        ['服务状态', serviceDetail(d.classifier?.detail)],
      ],
    )}<div class="cls-gates">${blocks.map((b) => `<section class="panel cls-gate"><div class="panel-head"><h2><span class="mono muted">${num(b.no).padStart(2, '0')}</span> ${esc(b.title)}</h2>${status(b.status)}</div><div class="panel-pad">${gateNumbers(b.key, data, evaluation, errors, d)}<strong class="cls-gate-headline">${esc(b.headline || '尚无结论')}</strong><p>${esc(b.note || '未提供说明')}</p>${jobButtons(b.jobs)}<button class="table-actions" data-cls-action="gate" data-key="${esc(b.key)}">查看依据 ${icon('arrow')}</button></div></section>`).join('')}</div>`;
  }
  const filename = (path) => (path ? String(path).split(/[\\/]/).pop() : '未标注文件');
  const fileContext = (f) =>
    f.stage ||
    { model: '训练模型', onnx: '推理文件' }[
      String(f.path || '')
        .split(/[\\/]/)
        .slice(-2, -1)[0]
        ?.trim()
    ] ||
    (filename(f.path) === 'sample_review.md' ? '语料复核' : '用途未标注');
  const bytes = (v) =>
    finite(v)
      ? v >= 1048576
        ? (v / 1048576).toFixed(1) + ' MB'
        : v >= 1024
          ? (v / 1024).toFixed(1) + ' KB'
          : v + ' B'
      : '—';
  function fileRows(files, group) {
    return files.map(
      (f, i) =>
        `<tr><td class="mono cls-path">${esc(f.file || filename(f.path))}<span class="table-sub">${esc(fileContext(f))}</span></td><td>${f.present === true ? pill('文件存在') : f.present === false ? pill('文件缺失', 'amber') : pill('未知', 'neutral')}</td><td>${f.present === true ? bytes(f.bytes) : '—'}</td><td>${f.present === true ? num(f.lines) : '—'}</td><td>${f.present === true ? stamp(f.mtime) : '—'}</td><td><button class="table-actions" data-cls-action="file" data-group="${group}" data-index="${i}">详情</button></td></tr>`,
    );
  }
  function dataPage() {
    const v = resource('classifierData');
    if (v.status !== 'ready') return loadingOrError(v);
    const d = v.data,
      splits = d.dataset?.splits || {},
      complete = ['train', 'val', 'test'].every((k) => splits[k]?.file?.present === true),
      leaks = d.dataset?.leaks || {};
    const allFiles = [
        ...(d.model?.files || []),
        ...(d.onnx?.files || []),
        ...(d.sample_review ? [d.sample_review] : []),
      ],
      exportReport = d.onnx?.report,
      missing = reportMissing(exportReport);
    const top = `<div class="stat-strip data-metrics">${metric('标注语料', formatted((d.lineage || []).find((f) => f.file === 'corpus_labeled.jsonl')?.present ? (d.lineage || []).find((f) => f.file === 'corpus_labeled.jsonl').lines : null), '条', '形成数据集的输入')}${['train', 'val', 'test'].map((key) => metric({ train: '训练集', val: '验证集', test: '测试集' }[key], formatted(splits[key]?.file?.present === true ? splits[key].size : null), '条', `多标签 ${formatted(splits[key]?.file?.present === true ? splits[key].multi_label : null)} 条`)).join('')}</div>`;
    const overlap = `<div class="cls-leakage">${[
      ['train_val', '训练 ∩ 验证'],
      ['train_test', '训练 ∩ 测试'],
      ['val_test', '验证 ∩ 测试'],
    ]
      .map(
        ([key, title]) =>
          `<article class="${complete && finite(leaks[key]) && leaks[key] > 0 ? 'is-error' : ''}"><span>${title}</span><strong>${formatted(complete ? leaks[key] : null)} <small>条</small></strong>${pill(!complete ? '尚不能核对' : leaks[key] === 0 ? '未发现重叠' : finite(leaks[key]) ? '存在重叠' : '读数未知', !complete ? 'neutral' : leaks[key] > 0 ? 'red' : leaks[key] === 0 ? '' : 'neutral')}</article>`,
      )
      .join('')}</div>`;
    const origins = `<div class="cls-split-origins">${Object.entries(splits)
      .map(
        ([key, split]) =>
          `<article><strong>${esc({ train: '训练集', val: '验证集', test: '测试集' }[key] || key)}</strong><p>多标签 ${formatted(split.file?.present === true ? split.multi_label : null)} 条</p><small>${
            Object.entries(split.origins || {})
              .map(([k, n]) => esc(origin(k)) + ' ' + formatted(n) + ' 条')
              .join(' · ') || '来源未提供'
          }</small></article>`,
      )
      .join('')}</div>`;
    return (
      top +
      panel(
        '语料血缘 · 从问题到数据集',
        `<div class="panel-pad">${lineageFlow(d)}${meta([
          [
            '标注语料来源',
            Object.entries(d.corpus_origins || {})
              .map(([k, n]) => origin(k) + ' ' + formatted(n) + ' 条')
              .join('；') || '未提供',
          ],
        ])}${jobButtons(['finetune-corpus', 'finetune-dataset'])}</div>${table(['产物 / 阶段', '文件状态', '大小', '记录行数', '更新时间', '操作'], fileRows(d.lineage || [], 'lineage'))}`,
      ) +
      panel(
        '三份数据集 · 泄漏自检与标签分布',
        `<div class="panel-pad">${overlap}${origins}<p class="field-hint section-gap">重叠只核对完全相同文本。多标签样本可计入多个类目；柱长分别按各列最多类目缩放，数字为实际样本数。</p></div><div class="cls-distribution-table">${distributionTable(d)}</div>${table(
          ['数据集文件', '文件状态', '大小', '记录行数', '更新时间', '操作'],
          fileRows(
            ['train', 'val', 'test']
              .filter((key) => splits[key]?.file)
              .map((key) => ({
                ...splits[key].file,
                stage: { train: '训练集', val: '验证集', test: '测试集' }[key],
              })),
            'dataset',
          ),
        )}<div class="panel-pad">${jobButtons(['finetune-dataset'])}</div>`,
        pill(
          !complete
            ? '文件未齐全'
            : d.dataset.clean === true
              ? '未发现相同文本'
              : d.dataset.clean === false
                ? '发现重叠'
                : '未知',
          d.dataset?.clean === false ? 'red' : 'neutral',
        ),
      ) +
      panel(
        '模型、推理与复核文件',
        `<div class="panel-pad">${meta([
          [
            '模型三件套',
            d.model?.trio_ok === true ? '齐全' : d.model?.trio_ok === false ? '未齐全' : '未知',
          ],
          ['文件在用阈值', d.model?.threshold],
        ])}${jobButtons(['finetune-train', 'finetune-export', 'classifier-up'])}</div>${table(['产物', '文件状态', '大小', '文本行数', '更新时间', '操作'], fileRows(allFiles, 'artifacts'))}`,
      ) +
      panel(
        'ONNX 导出对齐报告',
        `<div class="panel-pad">${
          missing ||
          meta([
            ['报告时间', exportReport.ran_at],
            ['核对预测', exportReport.checked],
            ['不一致', exportReport.mismatch],
            [
              '对齐结论',
              exportReport.passed === true
                ? '通过'
                : exportReport.passed === false
                  ? '未通过'
                  : '未知',
            ],
            ['产物路径', exportReport.onnx_path],
            ['Opset', exportReport.opset],
          ])
        }<p class="field-hint">文件存在、对齐报告、服务在线和质量达标分别核对。</p>${jobButtons(['finetune-export'])}</div>`,
      )
    );
  }
  function evaluationPage() {
    const v = resource('classifierEval');
    if (v.status !== 'ready') return loadingOrError(v);
    const d = v.data,
      e = d.eval,
      s = d.scan,
      missing = reportMissing(e),
      scanMissing = reportMissing(s);
    const metrics = missing
      ? ''
      : `<div class="stat-strip data-metrics">${metric('测试集', formatted(e.test_size), '条', `真实提问 ${formatted(e.real_subset?.size)} 条`)}${metric('评测阈值', e.threshold, '', `文件在用 ${d.threshold_in_use ?? '—'}`)}${metric('micro-F1', dec(e.micro?.f1), '', '汇总全部标签判断')}${metric('macro-F1', dec(e.macro?.f1), '', '各类指标平均')}</div>`;
    const classRows = (e?.classes || []).map(
      (c) =>
        `<tr class="${c.passed === false ? 'cls-failed' : ''}"><td><strong>${esc(c.name)}</strong><span class="table-sub">${pill((c.severity || d.severity?.[c.name] || '未标注') + '档', c.severity === '严' ? '' : 'neutral')}</span></td><td>${numberBar(c.p)}</td><td>${numberBar(c.r)}</td><td>${numberBar(c.f1, 1, c.passed === false)}</td><td>${formatted(c.support)}</td><td>${c.red_line == null ? pill('无单类红线', 'neutral') : pill(dec(c.red_line) + (c.passed === true ? ' · 达标' : c.passed === false ? ' · 未达标' : ' · 待核对'), c.passed === false ? 'red' : c.passed === true ? '' : 'neutral')}</td></tr>`,
    );
    const scores = panel(
      '总分 · micro 与 macro 一起看',
      `<div class="panel-pad">${missing || summaryScores(e)}<p class="field-hint section-gap">micro 汇总全部标签判断；macro 对各类指标分别平均。整体成绩不能代替单类红线。</p>${jobButtons(['finetune-eval'])}</div>`,
    );
    const classes = panel(
      '各类指标与容错红线',
      missing
        ? `<div class="panel-pad">${missing}</div>`
        : `<div class="panel-pad">${note(e.red_line_passed === true ? '报告中的类目红线全部达标。' : e.red_line_passed === false ? '有类目跌破红线，请先核对红色行及错例。' : '未返回红线结论。', e.red_line_passed === false)}${meta(
            [
              ['评测时间', e.ran_at],
              ['真实子集 micro-F1', dec(e.real_subset?.micro_f1)],
              [
                '来源',
                Object.entries(e.origin_counts || {})
                  .map(([k, n]) => origin(k) + ' ' + n + ' 条')
                  .join('；') || '未提供',
              ],
            ],
          )}</div><div class="cls-eval-table">${table(['类目 / 档位', '精确率 P', '召回率 R', 'F1', '正例 support', 'F1 红线'], classRows)}</div>`,
    );
    const scan = panel(
      '判定阈值 · 验证集候选线扫描',
      `<div class="panel-pad">${
        scanMissing ||
        `${meta([
          ['扫描时间', s.ran_at],
          ['验证集', s.val_size],
          ['扫描推荐', s.best_threshold],
          ['文件在用', d.threshold_in_use],
        ])}${scanBars(s, d.threshold_in_use)}<p class="field-hint section-gap">柱长为验证集 micro-F1（0–1）。推荐值与当前文件分别标记；本页不自动应用阈值。</p><details class="cls-scan-detail"><summary>查看各候选线 TP / FP / FN</summary>${table(
          ['阈值', 'micro-F1', 'TP', 'FP', 'FN'],
          (s.scan || []).map(
            (r) =>
              `<tr><td>${num(r.threshold)}</td><td>${dec(r.micro_f1)}</td><td>${formatted(r.tp)}</td><td>${formatted(r.fp)}</td><td>${formatted(r.fn)}</td></tr>`,
          ),
        )}</details>`
      }${jobButtons(['finetune-threshold-scan'])}</div>`,
      scanMissing
        ? ''
        : pill(
            s.consistent === true
              ? '扫描报告与当时在用一致'
              : s.consistent === false
                ? '扫描报告存在差异'
                : '一致性未提供',
            s.consistent === false ? 'amber' : 'neutral',
          ),
    );
    const matrix = missing
      ? ''
      : panel(
          '每类二元混淆矩阵',
          `<div class="panel-pad">${meta([
            ['标签判断', formatted(e.total_cells)],
            ['多打 FP', formatted(e.total_fp)],
            ['漏打 FN', formatted(e.total_fn)],
          ])}<p class="field-hint">每类独立统计四格；错位可同时计入一次 FP 与一次 FN，不是 17 × 17 单标签混淆矩阵。</p>${matrices(e)}<div class="form-actions section-gap">${act('查看完整错例', 'gate-report', 'data-key="errors"', 'soft')}</div>${jobButtons(['finetune-eval'])}</div>`,
        );
    return metrics + scores + classes + scan + matrix;
  }
  function errorRows(d) {
    return (d.errors || [])
      .map((r, i) => ({ ...r, index: i }))
      .filter(
        (r) =>
          (local.kind === 'all' || local.kind === r.kind) &&
          `${r.text} ${(r.gold || []).join(' ')} ${(r.pred || []).join(' ')}`.includes(
            local.errorQuery,
          ),
      )
      .map(
        (r) =>
          `<article class="cls-error-card"><div class="between"><div>${pill(r.kind, r.kind === '错位' ? 'red' : 'amber')}<span class="small muted">记 ${formatted(r.matrix_entries)} 笔矩阵错误</span></div>${act('核对类目边界', 'error', `data-index="${r.index}"`)}</div><h3>${esc(r.text)}</h3><div class="cls-error-labels"><div><span>标准标签</span>${comparisonTags(r.gold, r.pred, true)}</div><div><span>模型预测</span>${comparisonTags(r.pred, r.gold, false)}</div></div><p class="field-hint">${r.missed?.length ? '漏打：' + esc(r.missed.join('、')) + '　' : ''}${r.extra?.length ? '多打：' + esc(r.extra.join('、')) : ''}</p>${d.recipes?.[r.kind] ? `<p class="cls-error-recipe">建议：${esc(d.recipes[r.kind])}</p>` : ''}</article>`,
      );
  }
  function errorsPage() {
    const v = resource('classifierErrors');
    resource('topicCatalog');
    if (v.status !== 'ready') return loadingOrError(v);
    const d = v.data,
      missing = reportMissing(d.eval);
    if (missing) return missing;
    const kindCards = `<div class="cls-error-kinds">${['漏打', '多打', '错位'].map((kind) => `<article><div class="between"><h3>${kind}</h3><strong>${formatted(d.kinds?.[kind])} <small>条</small></strong></div><p>${esc(d.recipes?.[kind] || '未提供修正建议')}</p></article>`).join('')}</div>`;
    return `<div class="stat-strip data-metrics">${metric('错例', formatted(d.errors?.length), '条', '同一句只算一条错例')}${metric('矩阵错误', formatted(d.matrix_entries), '笔', '错位可产生多笔标签错误')}${metric('多打 FP', formatted(d.total_fp), '笔', '错误命中的标签')}${metric('漏打 FN', formatted(d.total_fn), '笔', '未命中的标准标签')}</div>${panel(
      '错误类型 · 错例数与矩阵笔数分开看',
      `<div class="panel-pad">${kindCards}${meta([
        ['报告时间', d.eval.ran_at],
        ['测试样本', d.eval.test_size],
        ['评测阈值', d.eval.threshold],
      ])}${jobButtons(['finetune-eval'])}</div>`,
    )}${panel(
      '边界摩擦 · 哪两类出现错位',
      table(
        ['漏打类目', '多打类目', '同时出现', '漏打类档位'],
        (d.pairs || []).map(
          (p) =>
            `<tr><td><span class="cls-compare-tag missed">${esc(p.missed)}</span></td><td><span class="cls-compare-tag extra">${esc(p.grabbed)}</span></td><td>${formatted(p.count)} 次</td><td>${esc(p.severity || '未标注')}</td></tr>`,
        ),
      ) +
        '<p class="panel-pad field-hint">配对仅表示报告中的漏打与多打共现，为人工核对提供线索。</p>',
    )}${panel('逐条对照 · 标准标签与模型预测', `<div class="panel-toolbar data-toolbar"><div class="data-filters">${['all', '漏打', '多打', '错位'].map((k) => `<button class="filter-chip ${local.kind === k ? 'active' : ''}" data-cls-kind="${k}" aria-pressed="${local.kind === k}">${k === 'all' ? '全部' : esc(k)}${k !== 'all' ? ' ' + formatted(d.kinds?.[k]) : ''}</button>`).join('')}</div><label class="search">${icon('search')}<input id="cls-error-query" aria-label="筛选报告错例" placeholder="筛选当前报告" value="${esc(local.errorQuery)}"></label></div><div class="cls-tag-legend"><span class="cls-compare-tag correct">正确命中</span><span class="cls-compare-tag missed">漏打</span><span class="cls-compare-tag extra">多打</span></div><div id="cls-error-rows" class="cls-error-list">${errorRows(d).join('') || '<div class="empty">当前报告没有匹配错例</div>'}</div><div class="panel-pad">${jobButtons(['finetune-eval'])}</div>`)}`;
  }
  function trialPage() {
    const v = resource('classifierService');
    if (v.status !== 'ready') return loadingOrError(v);
    const d = v.data;
    const servicePanel = panel(
      '推理服务',
      `<div class="panel-pad">${meta([
        ['服务状态', d.online === true ? '在线' : d.online === false ? '离线' : '未知'],
        ['当前阈值', d.threshold],
        [
          'ONNX 文件',
          d.onnx_present === true ? '存在' : d.onnx_present === false ? '缺失' : '未知',
        ],
        ['健康检查', serviceDetail(d.detail)],
      ])}${note(ui.mode === 'live' ? '单句试分类调用当前分类服务并展示实际分数；可从验收卡或作业中心核对条件后重跑任务。' : '以下为两条预设的展示结果，不调用模型，也不推算其他问题的预测分数。')}</div>`,
      health(d.online),
    );
    if (ui.mode === 'live')
      return (
        servicePanel +
        panel(
          '单句试分类',
          `<div class="panel-pad"><form id="cls-trial-form"><label class="field">完整问题<textarea id="cls-trial-text" maxlength="2000" required ${ui.classifyBusy ? 'readonly' : ''} placeholder="输入一句需要核对类目的问题">${esc(local.trialText)}</textarea></label><button class="btn primary" type="submit" ${ui.classifyBusy || ui.actionBusy || d.online !== true ? 'disabled' : ''}>${ui.classifyBusy ? '正在分类…' : '查询真实分类'}</button><button class="btn soft" type="button" data-cls-action="jobs">打开作业中心</button><p class="field-hint section-gap">调用现有本地分类服务，不写入问题池；服务离线时先在作业中心核对 classifier-up。</p></form><div id="cls-trial-output">${local.trialError ? `<p role="alert" class="section-gap">${esc(local.trialError)}</p>` : ''}${local.trialResult ? trialResult(local.trialResult) : ''}</div></div>`,
        )
      );
    const r = trials[local.trial];
    return (
      servicePanel +
      `<div class="section-gap">${panel(
        '单句结果展示样例',
        `<div class="panel-pad"><label class="field">预设问题<select id="cls-trial-preset">${trials.map((r, i) => `<option value="${i}" ${local.trial === i ? 'selected' : ''}>${esc(r.text)}</option>`).join('')}</select></label>${act('查看预设结果', 'trial', '', 'primary')}${
          local.trialShown
            ? `<div class="section-gap">${tags(r.labels)}${meta([
                ['阈值', 0.5],
                ['兜底', r.fallback ? '全部分数低于阈值，返回其他' : '否'],
              ])}${scoreChart(
                r.scores.map(([label, score]) => ({ label, score, hit: score >= 0.5 })),
                0.5,
              )}<p class="field-hint section-gap">只列出样例中的部分分数，未列类目不代表零分；兜底标签不代表该类分数达到阈值。</p></div>`
            : ''
        }</div>`,
      )}</div>`
    );
  }
  function show(title, body) {
    modal(title, body);
    document.getElementById('modal').classList.add('classification-dialog');
  }
  function trialResult(r) {
    return `<div class="section-gap">${tags(r.labels)}${meta([
      ['完整问题', r.text],
      ['服务当前阈值', r.threshold],
      ['兜底', r.fallback ? '是 · 未达阈值，按服务规则返回标签' : '否'],
    ])}${scoreChart(r.scores, r.threshold)}</div>`;
  }
  async function classifySentence() {
    if (
      ui.mode !== 'live' ||
      ui.classifyBusy ||
      ui.actionBusy ||
      !local.trialText.trim() ||
      !location.pathname.startsWith('/v2/')
    )
      return;
    const epoch = ui.epoch,
      text = local.trialText.trim();
    ui.classifyBusy = true;
    local.trialResult = null;
    local.trialError = '';
    render();
    try {
      const data = await h.request('/api/acceptance/classify', { text });
      if (
        !Array.isArray(data.labels) ||
        !Array.isArray(data.scores) ||
        !data.scores.length ||
        data.text !== text ||
        data.scores.some(
          (row) =>
            typeof row.label !== 'string' ||
            !Number.isFinite(row.score) ||
            typeof row.hit !== 'boolean',
        )
      )
        throw new Error('分类结果不完整，请重新核对服务。');
      if (epoch === ui.epoch && ui.mode === 'live') local.trialResult = data;
    } catch (error) {
      if (epoch === ui.epoch) local.trialError = error.message;
    } finally {
      ui.classifyBusy = false;
      if (epoch === ui.epoch) render();
    }
  }
  function onSubmit(event) {
    if (event.target.id !== 'cls-trial-form') return false;
    event.preventDefault();
    classifySentence();
    return true;
  }
  function onClick(el) {
    if (el.dataset.clsLabel) {
      local.label = el.dataset.clsLabel;
      local.page = 1;
      render();
      return true;
    }
    if (el.dataset.clsTab) {
      local.modelTab = el.dataset.clsTab;
      render();
      return true;
    }
    if (el.dataset.clsKind) {
      local.kind = el.dataset.clsKind;
      render();
      return true;
    }
    const a = el.dataset.clsAction;
    if (!a) return false;
    if (a === 'previous' || a === 'next') {
      const q = questionResource().data;
      if (q) {
        local.page = Math.min(q.pages, Math.max(1, q.page + (a === 'next' ? 1 : -1)));
        render();
      }
    } else if (a === 'run-job') {
      const name = el.dataset.name;
      if (Object.hasOwn(jobTitles, name) && h.actions.available())
        h.actions.job(name, false, () => {
          document.getElementById('modal').close();
          go('jobs');
        });
    } else if (a === 'trial') {
      local.trialShown = true;
      render();
    } else if (a === 'guide')
      show(
        '主题与分类器 · 查询范围',
        `<p>主题页读取类目定义、分布与所选类目的服务端分页。分类器页读取既有验收、文件、评测、错例及服务健康结果。</p><p class="section-gap">已有报告可查询；生成语料、训练、导出、评测和批量归类从作业中心核对后启动。单句试分类不写问题池。阈值配置不由页面自动应用。</p><div class="section-gap">${act('查看登记作业', 'jobs')}${act('查看咨询主题', 'topics')}</div>`,
      );
    else if (a === 'jobs' || a === 'topics') {
      document.getElementById('modal').close();
      go(a);
    } else if (a === 'question') {
      const r = questionResource().data?.items?.[Number(el.dataset.index)];
      if (r)
        show(
          '归类问题 · #' + r.question_id,
          `${tags(r.labels)}${meta([
            ['来源', source(r.source)],
            ['出现次数', r.occurrence_count],
            ['提问时间', r.asked_at],
            ['归类时间', r.classified_at],
            ['规范化', r.normalized === true ? '是' : r.normalized === false ? '否' : '未提供'],
            ['审核状态', r.review_status || '未提供'],
          ])}<h3>原始问法</h3><div class="preview-text section-gap">${esc(r.raw_question || '未提供')}</div><h3 class="section-gap">归类文本</h3><div class="preview-text section-gap">${esc(r.text || '未提供')}</div>`,
        );
    } else if (a === 'gate') {
      const b = resource('classifierOverview').data?.blocks?.find((r) => r.key === el.dataset.key);
      if (b)
        show(
          b.title,
          `${status(b.status)}<h3 class="section-gap">${esc(b.headline)}</h3><p class="section-gap">${esc(b.note)}</p>${meta([['关联作业', (b.jobs || []).join('、') || '未提供']])}<p class="field-hint">这是后端已有验收摘要；相关报告在对应子页查看。作业入口可核对执行条件，再确认启动。</p><div class="section-gap">${act('查看对应报告', 'gate-report', `data-key="${esc(b.key)}"`)}${act('查看登记作业', 'jobs')}</div>`,
        );
    } else if (a === 'gate-report') {
      document.getElementById('modal').close();
      const key = el.dataset.key;
      if (key === 'classify') go('topics');
      else if (key === 'golden')
        show(
          '黄金样例闸 · 数据范围',
          note('现有接口提供验收摘要，尚无黄金样例逐条详情查询。未用其他错例代替这项依据。'),
        );
      else {
        local.modelTab = ['data', 'train', 'export'].includes(key)
          ? 'data'
          : key === 'errors'
            ? 'errors'
            : 'evaluation';
        render();
      }
    } else if (a === 'file') {
      const d = resource('classifierData').data,
        files =
          el.dataset.group === 'lineage'
            ? d?.lineage
            : el.dataset.group === 'dataset'
              ? ['train', 'val', 'test']
                  .filter((key) => d?.dataset?.splits?.[key]?.file)
                  .map((key) => ({
                    ...d.dataset.splits[key].file,
                    stage: { train: '训练集', val: '验证集', test: '测试集' }[key],
                  }))
              : [
                  ...(d?.model?.files || []),
                  ...(d?.onnx?.files || []),
                  ...(d?.sample_review ? [d.sample_review] : []),
                ],
        f = files?.[Number(el.dataset.index)];
      if (f)
        show(
          '产物元信息',
          `${meta([
            ['文件路径', f.path],
            ['是否存在', f.present === true ? '存在' : f.present === false ? '缺失' : '未知'],
            ['大小', f.present === true ? bytes(f.bytes) : null],
            ['记录行数', f.present === true ? f.lines : null],
            ['更新时间', f.present === true ? f.mtime : null],
            ['用途', f.desc || f.stage || '未提供'],
          ])}<p class="small muted">当前查询仅提供文件元信息，不读取文件正文。</p>`,
        );
    } else if (a === 'split') {
      const d = resource('classifierData').data,
        s = d?.dataset?.splits?.[el.dataset.key];
      if (s)
        show(
          '数据集 · 标签分布',
          s.file?.present !== true
            ? note('该数据集文件尚未生成。')
            : `${meta([
                ['样本数', s.size],
                ['多标签样本', s.multi_label],
                ['用途', s.desc],
              ])}${table(
                ['标签', '样本数', '占本集样本'],
                Object.entries(s.counts || {}).map(
                  ([k, n]) =>
                    `<tr><td>${esc(k)}</td><td>${num(n)}</td><td>${s.size > 0 ? pct(n / s.size) : '—'}</td></tr>`,
                ),
              )}<p class="field-hint section-gap">同一条样本可以同时计入多个标签；占比之和可能超过 100%。</p>`,
        );
    } else if (a === 'error') {
      const d = resource('classifierErrors').data,
        r = d?.errors?.[Number(el.dataset.index)],
        c = resource('topicCatalog');
      if (r)
        show(
          '错例复核 · ' + r.kind,
          `<div class="preview-text">${esc(r.text)}</div>${meta([
            ['错误笔数', r.matrix_entries],
            ['报告时间', d.eval.ran_at],
            ['评测阈值', d.eval.threshold],
          ])}<div class="report-detail-grid">${[
            ['标准标签', r.gold],
            ['预测标签', r.pred],
            ['漏打', r.missed],
            ['多打', r.extra],
          ]
            .map(
              ([t, l]) =>
                `<section><h3>${t}</h3><div class="section-gap">${tags(l)}</div></section>`,
            )
            .join(
              '',
            )}</div><h3 class="section-gap">权威类目边界</h3>${c.status === 'ready' ? [...new Set([...(r.gold || []), ...(r.pred || [])])].map((lb) => `<p class="cls-recipe"><strong>${esc(lb)}</strong>${esc(c.data.classes.find((x) => x.label === lb)?.boundary || '未提供')}</p>`).join('') : note('类目定义暂不可读取，不推造边界。')}<p class="field-hint section-gap">只核对保存报告，没有提交补数或复训。</p>`,
        );
    }
    return true;
  }
  function onInput(el) {
    if (el.id === 'cls-trial-text' && !ui.classifyBusy) {
      local.trialText = el.value;
      local.trialResult = null;
      local.trialError = '';
      const output = document.getElementById('cls-trial-output');
      if (output)
        output.innerHTML = '<p class="field-hint section-gap">问题已修改，请重新查询。</p>';
      return true;
    }
    if (el.id !== 'cls-error-query') return false;
    local.errorQuery = el.value;
    const d = resource('classifierErrors').data,
      node = document.getElementById('cls-error-rows');
    if (node && d)
      node.innerHTML = errorRows(d).join('') || '<div class="empty">当前报告没有匹配错例</div>';
    return true;
  }
  function onChange(el) {
    if (el.id === 'cls-topic-size') {
      local.size = Number(el.value);
      local.page = 1;
      render();
      return true;
    }
    if (el.id === 'cls-trial-preset') {
      local.trial = Number(el.value);
      local.trialShown = false;
      render();
      return true;
    }
    return false;
  }
  function overviewModules() {
    const d = sampleDistribution(),
      a = sampleAcceptance(),
      unknown = ui.scenario === 'error';
    return [
      {
        key: 'topics',
        title: '咨询主题',
        status: unknown ? 'error' : d.total ? 'ok' : 'missing',
        headline: unknown
          ? '主题统计暂不可读取'
          : d.total
            ? '已归类问题可按类目查看'
            : '尚无已归类问题',
        metrics: [
          { label: '已归类', value: unknown ? null : d.total },
          { label: '类目', value: catalog.classes.length },
        ],
        note: '多标签分布与明细使用同一批样例。',
      },
      {
        key: 'classifier',
        title: '分类器管理',
        status: unknown ? 'error' : a.all_pass ? 'ok' : a.passed ? 'attention' : 'missing',
        headline: unknown
          ? '模型验收暂不可读取'
          : a.all_pass
            ? '九项验收全部达标'
            : '验收、产物和服务状态需分别核对',
        metrics: [
          { label: '通过验收', value: unknown ? null : `${a.passed} / ${a.total}` },
          { label: '服务', value: unknown ? null : a.classifier.online ? '在线' : '离线' },
        ],
        note: '文件齐全不等于评测达标或服务在线。',
      },
    ];
  }
  return {
    hasPage: (page) => ['topics', 'models'].includes(page),
    hasResource: (key) => key.startsWith('topicQuestions:') || Object.hasOwn(paths, key),
    paths,
    topicsPage,
    modelsPage,
    overviewModules,
    sampleResource,
    onClick,
    onInput,
    onChange,
    onSubmit,
    reset: () => {
      local.page = 1;
      local.trialShown = false;
      local.trialResult = null;
      local.trialError = '';
    },
    time: (page) =>
      ui.cache[
        page === 'topics'
          ? 'topicDistribution'
          : {
              acceptance: 'classifierOverview',
              data: 'classifierData',
              evaluation: 'classifierEval',
              errors: 'classifierErrors',
              trial: 'classifierService',
            }[local.modelTab]
      ]?.time,
    scenarioOptions: (page) =>
      page === 'topics'
        ? [
            ['normal', '多标签与分页'],
            ['empty', '暂无归类问题'],
            ['unmarked', '来源与时间未标注'],
            ['error', '统计读取失败'],
          ]
        : [
            ['normal', '已有报告'],
            ['failed', '评测未达标'],
            ['offline', '产物齐全 · 服务离线'],
            ['missing', '产物未生成'],
            ['error', '读取失败'],
          ],
    pagePlans: {
      topics: {
        name: '咨询主题',
        icon: 'chat',
        stage: '本轮可体验',
        text: '权威类目与边界、独立问题数、多标签占比、来源和服务端分页；完整问法进入详情。',
      },
      models: {
        name: '分类器管理',
        icon: 'spark',
        stage: '本轮可体验',
        text: '九项验收、语料和模型文件、评测红线、阈值扫描、二元矩阵、错例与服务健康。实时模式可查询单句分类；各项验收可直接核对并重跑，样例不执行任务。',
      },
    },
  };
};
