// Isolated state/contract checks: no browser, database, model or real fetch calls.
const fs = require('node:fs'),
  path = require('node:path'),
  vm = require('node:vm'),
  assert = require('node:assert/strict');
const base = path.resolve(__dirname, '..');
const flush = async () => {
  for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r));
};
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};
const reply = (data, status = 200) => ({
  ok: status < 400,
  status,
  headers: { get: () => 'application/json' },
  json: async () => data,
});
const esc = (x) =>
  String(x ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
const buffer = (text) => new TextEncoder().encode(text).buffer;
function setup(name, mode = 'live') {
  const e = {
    html: '',
    calls: [],
    jobs: [],
    data: {},
    nodes: {},
    ui: { mode, scenario: 'normal', cache: {}, epoch: 0 },
    state: { page: name === 'admin-reports' ? 'quality' : 'models', surface: 'admin' },
  };
  const node = (id) =>
    (e.nodes[id] ??=
      id === 'modal'
        ? {
            open: false,
            dataset: {},
            close() {
              this.open = false;
            },
            classList: { add() {} },
          }
        : { innerHTML: '', textContent: '' });
  const context = {
    window: {},
    location: { pathname: '/v2/' },
    document: { getElementById: node, querySelector: () => null },
    TextDecoder,
    AbortController,
    URLSearchParams,
    setTimeout,
    clearTimeout,
    fetch: (url, options = {}) => {
      e.calls.push({ url, options });
      return e.fetch ? e.fetch(url, options) : Promise.resolve(reply({}));
    },
  };
  const child = {
    hasResource: () => false,
    hasPage: () => false,
    onClick: () => false,
    onInput() {},
    onChange: () => false,
    onSubmit: () => false,
    reset() {},
    overviewModules: () => [],
    reviewCounts: () => ({ pending: 0 }),
    publishedChunks: () => [],
    paths: {},
  };
  for (const part of ['Workflows', 'Actions', 'Reports', 'Classification'])
    context.window['createMinihelp' + part] = (h) => {
      if (name === 'admin-data') e.ui = h.ui;
      return child;
    };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(base, name + '.js'), 'utf8'), context);
  const factory =
    context.window[
      name === 'admin-data'
        ? 'createMinihelpDataPanels'
        : name === 'admin-reports'
          ? 'createMinihelpReports'
          : 'createMinihelpClassification'
    ];
  const h = {
    esc,
    icon: () => '',
    pill: (text, color) => `<span data-tone="${color || 'green'}">${esc(text)}</span>`,
    stat: (label, value, unit, foot) => `${label}:${value}${unit}:${foot}`,
    metric: (label, value, unit, foot) => `${label}:${value}${unit}:${foot}`,
    panel: (title, body, extra = '') => `<section><h2>${title}</h2>${extra}${body}</section>`,
    table: (heads, rows) => `<table>${heads.join('|')}${rows.join('')}</table>`,
    stamp: (x) => esc(x ?? '—'),
    listStamp: (x) => esc(x ?? '—'),
    state: e.state,
    ui: e.ui,
    toast() {},
    modal: (title, body) => {
      e.modal = title + body;
      node('modal').open = true;
    },
    go: (page) => (e.state.page = page),
    resource: (key) =>
      e.data[key] ||
      (key === 'evaluationState'
        ? { status: 'ready', data: { running: false } }
        : e.factory.sampleResource(key)),
    loadingOrError: (v) => (v.status === 'ready' ? '' : '<p>数据不可用</p>'),
    request: async () => ({}),
    actions: {
      available: () => e.ui.mode === 'live' && !e.ui.actionBusy,
      job: (name, stop, reopen) => e.jobs.push({ name, stop, reopen }),
    },
    render: () => {
      e.html =
        name === 'admin-data'
          ? e.factory.renderPage('knowledge')
          : name === 'admin-reports'
            ? e.factory.qualityPage()
            : e.factory.modelsPage();
    },
  };
  e.factory = factory(h);
  e.context = context;
  if (name === 'admin-data') {
    e.fetch = (url) =>
      Promise.resolve(
        reply(
          url === '/api/kb/overview'
            ? {
                chunks: { total: 0, done: 0, pending: 0, by_content_type: {} },
                content_types: [{ key: 'policy' }],
                sources: [],
                milvus: { online: true, count: 0 },
              }
            : { items: [], total: 0, page: 1, pages: 1, size: 20 },
        ),
      );
    e.factory.onClick({ dataset: { dataTab: 'import' } });
  }
  e.click = (dataset) => e.factory.onClick({ dataset });
  e.input = (id, value) => e.factory.onInput({ id, value });
  e.change = (id, value, type = 'select-one') =>
    e.factory.onChange({ id, value, type, checked: value });
  e.submit = (id) => e.factory.onSubmit({ target: { id }, preventDefault() {} });
  e.file = (name, content, size = 100) =>
    e.factory.onChange({
      id: 'data-import-file',
      files: [{ name, size, arrayBuffer: () => Promise.resolve(buffer(content)) }],
      value: name,
    });
  return e;
}
(async () => {
  const passed = [];
  const file = setup('admin-data');
  await flush();
  file.input('data-import-text', '保留原文');
  file.file('new.md', '\uFEFF# 新材料\r\n正文');
  await flush();
  assert.equal(file.ui.text, '# 新材料\n正文');
  assert.equal(file.ui.preview, null);
  assert.equal(file.ui.fileName, 'new.md');
  assert.equal(file.calls.filter((c) => c.options.method === 'POST').length, 0);
  passed.push('文件只载入可编辑正文，清除旧预览，不自动预览或入库');
  for (const [name, text, size] of [
    ['bad.pdf', '正文', 100],
    ['huge.md', '正文', 1048577],
    ['empty.txt', ' ', 10],
    ['long.txt', 'x'.repeat(40001), 50000],
  ]) {
    file.file(name, text, size);
    await flush();
    assert.equal(file.ui.text, '# 新材料\n正文');
    assert.match(file.ui.fileNotice, /保留/);
  }
  file.factory.onChange({
    id: 'data-import-file',
    files: [
      {
        name: 'invalid.txt',
        size: 2,
        arrayBuffer: async () => new Uint8Array([0xff, 0xff]).buffer,
      },
    ],
    value: '',
  });
  await flush();
  assert.equal(file.ui.text, '# 新材料\n正文');
  assert.equal(file.ui.fileReading, false);
  passed.push('格式、大小、空白、字符限制、编码失败保留原正文');
  for (const action of ['edit', 'type', 'mode', 'refresh', 'new-file']) {
    const f = setup('admin-data');
    await flush();
    f.input('data-import-text', '旧正文');
    const delayed = deferred();
    f.factory.onChange({
      id: 'data-import-file',
      files: [{ name: 'late.md', size: 100, arrayBuffer: () => delayed.promise }],
      value: '',
    });
    f.submit('data-preview-form');
    assert.equal(f.calls.filter((c) => c.url === '/api/kb/preview').length, 0);
    if (action === 'edit') f.input('data-import-text', '新编辑');
    if (action === 'type') f.change('data-import-type', 'faq');
    if (action === 'mode') f.click({ dataMode: 'sample' });
    if (action === 'refresh') f.click({ dataAction: 'refresh' });
    if (action === 'new-file') {
      f.file('latest.txt', '最新文件');
      await flush();
    }
    const expected = f.ui.text;
    delayed.resolve(buffer('迟到内容'));
    await flush();
    assert.equal(f.ui.text, expected);
    assert.equal(f.ui.fileReading, false);
  }
  passed.push('读取期间不允许预览；旧文件读取不能覆盖编辑、类型、模式、刷新或新文件');
  const rag = setup('admin-reports');
  rag.click({ reportTab: 'quality:trial' });
  assert.equal(rag.calls.length, 0);
  assert.equal(rag.factory.qualityTime(), null);
  rag.input('report-trial-query', '问题');
  rag.change('report-trial-strategy', 'hybrid_rerank');
  rag.change('report-trial-k', '7');
  rag.change('report-trial-rewrite', true, 'checkbox');
  rag.change('report-trial-split', true, 'checkbox');
  const pending = deferred();
  rag.fetch = () => pending.promise;
  rag.submit('report-trial-form');
  rag.submit('report-trial-form');
  assert.equal(rag.calls.length, 1);
  assert.deepEqual(JSON.parse(rag.calls[0].options.body), {
    query: '问题',
    strategy: 'hybrid_rerank',
    top_k: 7,
    rewrite: true,
    split: true,
  });
  pending.resolve(
    reply({
      answer: '依据回答<script>',
      refused: false,
      citations: [{ n: 1, section_path: '来源', answer: '完整证据' }],
    }),
  );
  await flush();
  assert.match(rag.html, /依据回答&lt;script&gt;/);
  assert.match(rag.html, /完整证据/);
  assert.equal(typeof rag.factory.qualityTime(), 'string');
  passed.push('单题点击后请求，四项参数正确、重复提交锁定、答案与引用转义');
  rag.change('report-trial-k', '51');
  rag.submit('report-trial-form');
  assert.equal(rag.calls.length, 1);
  assert.equal(rag.factory.qualityTime(), null);
  rag.change('report-trial-k', '5');
  rag.fetch = async () => reply({ answer: '拒答说明', refused: true, citations: [] });
  rag.submit('report-trial-form');
  await flush();
  assert.match(rag.html, /证据不足 · 拒答/);
  rag.fetch = async () => reply({}, 502);
  rag.submit('report-trial-form');
  await flush();
  assert.match(rag.html, /HTTP 502/);
  assert.doesNotMatch(rag.html, /拒答说明/);
  rag.fetch = async () => reply({ answer: '不完整', refused: false });
  rag.submit('report-trial-form');
  await flush();
  assert.match(rag.html, /数据不完整/);
  passed.push('Top K 验证、拒答、失败及不完整返回不冒充有效答案');
  const stale = setup('admin-reports');
  stale.click({ reportTab: 'quality:trial' });
  stale.input('report-trial-query', '问题 A');
  const d = deferred();
  stale.fetch = () => d.promise;
  stale.submit('report-trial-form');
  stale.input('report-trial-query', '问题 B');
  d.resolve(reply({ answer: '旧答案', refused: false, citations: [] }));
  await flush();
  assert.doesNotMatch(stale.html, /旧答案/);
  stale.input('report-trial-query', '问题 C');
  const d2 = deferred();
  stale.fetch = () => d2.promise;
  stale.submit('report-trial-form');
  stale.ui.epoch++;
  stale.factory.reset();
  d2.resolve(reply({ answer: '旧模式答案', refused: false, citations: [] }));
  await flush();
  assert.doesNotMatch(stale.factory.qualityPage(), /旧模式答案/);
  passed.push('旧输入及来源刷新前的单题结果不覆盖当前状态');
  const sample = setup('admin-reports', 'sample');
  sample.click({ reportAction: 'try-case', index: '0' });
  sample.submit('report-trial-form');
  await flush();
  assert.match(sample.html, /预设展示样例/);
  assert.equal(sample.calls.length, 0);
  passed.push('题集试问只载入问题；展示样例不请求模型');
  const cost = setup('admin-reports');
  cost.data.observation = {
    status: 'ready',
    data: {
      cost: {
        summary: {
          requests: 4,
          generations: 6,
          known_input_tokens: 4434,
          known_output_tokens: 497,
          unpriced: 0,
          unknown_usage: 0,
        },
        rows: [
          {
            intent: '订单',
            input_tokens: 2432,
            output_tokens: 248,
            priced_subtotals: { CNY: 0.1, USD: 0.2 },
          },
        ],
        meta: { source: 'test' },
      },
    },
  };
  let html = cost.factory.observationPage();
  assert.match(html, /4,931/);
  assert.match(html, /54\.4%/);
  assert.match(html, /CNY/);
  assert.match(html, /USD/);
  cost.data.observation.data.cost.summary.known_input_tokens = null;
  html = cost.factory.observationPage();
  assert.match(html, /已知 Token:—/);
  assert.doesNotMatch(html, /54\.4%/);
  passed.push('Token 总数与分布分母正确，币种分列，缺失不补零');
  const cls = setup('admin-classification');
  cls.factory.modelsPage();
  assert.equal(cls.jobs.length, 0);
  cls.click({ clsAction: 'run-job', name: 'finetune-train' });
  assert.equal(cls.jobs[0].name, 'finetune-train');
  assert.equal(cls.jobs[0].stop, false);
  cls.ui.actionBusy = true;
  cls.click({ clsAction: 'run-job', name: 'finetune-eval' });
  assert.equal(cls.jobs.length, 1);
  cls.ui.actionBusy = false;
  cls.click({ clsAction: 'run-job', name: 'unregistered' });
  assert.equal(cls.jobs.length, 1);
  cls.ui.mode = 'sample';
  cls.click({ clsAction: 'run-job', name: 'finetune-train' });
  assert.equal(cls.jobs.length, 1);
  passed.push('分类器直接重跑仅交给既有确认流程，模式、忙状态及白名单有效');
  cls.ui.scenario = 'failed';
  for (const tab of ['data', 'evaluation', 'errors', 'trial']) {
    cls.click({ clsTab: tab });
    assert.doesNotMatch(cls.html, /NaN|undefined/);
  }
  cls.click({ clsTab: 'errors' });
  assert.match(cls.html, /cls-compare-tag missed/);
  assert.match(cls.html, /cls-compare-tag extra/);
  cls.input('cls-error-query', '不匹配的内容');
  assert.equal(cls.nodes['cls-error-rows'].innerHTML.includes('没有匹配错例'), true);
  cls.ui.scenario = 'missing';
  for (const tab of ['data', 'evaluation', 'errors']) {
    cls.click({ clsTab: tab });
    assert.doesNotMatch(cls.html, /NaN|undefined/);
  }
  assert.equal(cls.calls.length, 0);
  passed.push('分类器失败、缺失与筛选保留正确未知状态、漏打/多打标记，渲染无请求');
  console.log(
    JSON.stringify(
      { passed: passed.length, checks: passed, network: 'all fetch calls mocked' },
      null,
      2,
    ),
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
