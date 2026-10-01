/* Confirmed writes reuse the existing APIs. Samples never reach this module. */
window.createMinihelpActions = function (h) {
  'use strict';
  const { ui, esc, modal, render, request, go } = h;
  let pending = null,
    sequence = 0;
  const dialog = () => document.getElementById('modal');
  const available = () =>
    ui.mode === 'live' &&
    location.pathname.startsWith('/v2/') &&
    !ui.actionBusy &&
    !ui.ingestBusy &&
    !ui.vectorStarting &&
    !ui.vectorChecking &&
    !ui.classifyBusy;
  const fields = (rows) =>
    `<dl class="data-record-fields">${rows.map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b ?? '—')}</dd></div>`).join('')}</dl>`;
  const full = (title, text) =>
    `<h3 class="section-gap">${esc(title)}</h3><div class="data-detail-text section-gap">${esc(text)}</div>`;
  function show(title, body, footer = '') {
    modal(title, body, footer || '<button class="btn" data-action="modal-close">关闭</button>');
    dialog().classList.add('knowledge-dialog');
  }
  function invalidate() {
    ui.epoch++;
    ui.cache = {};
    render();
  }
  async function prepare(build) {
    if (!available()) return;
    const token = ++sequence,
      epoch = ui.epoch;
    pending = null;
    ui.actionBusy = true;
    render();
    show('核对操作范围', '<div class="empty" role="status">正在读取最新状态…</div>');
    dialog().dataset.actionToken = String(token);
    try {
      const spec = await build();
      if (
        token !== sequence ||
        epoch !== ui.epoch ||
        !dialog().open ||
        dialog().dataset.actionToken !== String(token)
      )
        return;
      pending = spec;
      show(
        spec.title,
        `<form id="admin-confirm-form">${spec.body}<label class="data-ingest-check section-gap"><input id="admin-confirm-check" type="checkbox" required>我已核对对象、范围和执行条件，确认执行本次操作。</label><p class="field-hint section-gap">提交后查询真实结果。超时不自动重试，已完成的步骤不会由页面撤回。</p></form>`,
        `<button class="btn" data-admin-action="cancel">返回核对</button><button class="btn primary" form="admin-confirm-form" type="submit">${esc(spec.button || '确认执行')}</button>`,
      );
      dialog().dataset.actionToken = String(token);
    } catch (error) {
      if (token === sequence && epoch === ui.epoch && dialog().open)
        show(
          '暂不能执行',
          `<p role="alert">${esc(error.message)}</p><p class="field-hint section-gap">尚未发送写入请求。</p>`,
        );
    } finally {
      ui.actionBusy = false;
      render();
    }
  }
  async function execute() {
    const spec = pending;
    if (
      !spec ||
      typeof spec.path !== 'string' ||
      typeof spec.valid !== 'function' ||
      !available() ||
      dialog().dataset.actionToken !== String(sequence) ||
      !document.getElementById('admin-confirm-check')?.checked
    )
      return;
    const token = sequence;
    pending = null;
    ui.actionBusy = true;
    ui.actionNotice = spec.title + '：请求正在执行，关闭弹窗不会停止后台操作。';
    show(
      spec.title,
      '<div class="empty" role="status">正在执行，请等待真实返回结果…</div><p class="field-hint section-gap">关闭仅收起弹窗，后台操作继续；结果会显示在页面上。</p>',
    );
    dialog().dataset.actionToken = String(token);
    render();
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), spec.timeout || 60000);
    let message,
      uncertain = false;
    try {
      const response = await fetch(spec.path, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(spec.data !== undefined ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(spec.data !== undefined ? { body: JSON.stringify(spec.data) } : {}),
      });
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error('服务没有返回完整结果。');
      }
      if (!response.ok)
        throw Object.assign(
          new Error(
            typeof data.detail === 'string'
              ? data.detail
              : `请求未完成（HTTP ${response.status}）。`,
          ),
          { uncertain: response.status >= 500, status: response.status },
        );
      if (!spec.valid(data, response.status)) throw new Error('返回结果不完整，需要查询真实状态。');
      message = spec.result(data, response.status);
    } catch (error) {
      uncertain = error.uncertain !== false;
      message =
        (error.name === 'AbortError' ? '请求超时，结果待核对。' : error.message) +
        (error.status === 409
          ? ' 状态已变化，请重新读取对象。'
          : uncertain
            ? ' 可能已完成部分步骤；请先查询库存、记录或作业状态，勿直接重复提交。'
            : ' 请修正输入或重新核对条件。');
    } finally {
      clearTimeout(timer);
      ui.actionBusy = false;
      ui.actionNotice = spec.title + '：' + message;
      invalidate();
    }
    if (token === sequence && dialog().open && dialog().dataset.actionToken === String(token)) {
      show(
        uncertain ? '结果待核对' : '操作结果',
        `<p role="status">${esc(message)}</p>${spec.after || ''}`,
        `<button class="btn" data-action="modal-close">关闭</button><button class="btn primary" data-admin-action="reopen">查询当前结果</button>`,
      );
      pending = { reopen: spec.reopen };
    }
  }
  function candidate(row, action, reopen) {
    return prepare(async () => {
      const fresh = await request('/api/kb/staging/' + row.id);
      if (fresh.status !== 'kept') throw new Error('候选已不在待审状态，请重新查看。');
      if (action === 'approve' && fresh.material?.valid !== true)
        throw new Error('当前材料校验未通过，不能采纳。');
      const approved = action === 'approve';
      return {
        title: approved ? '采纳候选问答' : '弃用候选问答',
        button: approved ? '确认采纳' : '确认弃用',
        path: '/api/kb/staging/' + action,
        data: { ids: [fresh.id] },
        body:
          fields([
            ['候选 ID', '#' + fresh.id],
            ['可信材料', fresh.source_ref],
          ]) +
          full('问题', fresh.question) +
          full('完整答案', fresh.answer) +
          `<p class="notice section-gap">${approved ? '将保存此问答，并调用现有全库 pending 向量补齐（包含历史待补原文），会使用嵌入服务；全部完成后才标为已采纳。失败可能保留待补块。' : '保留候选记录并标为弃用，不新增知识，不调用模型。'}</p>`,
        valid: (d) =>
          approved
            ? d.approved === 1 &&
              Array.isArray(d.chunk_ids) &&
              d.chunk_ids.length === 1 &&
              d.chunk_ids.every(Number.isInteger)
            : d.rejected === 1,
        result: (d) =>
          approved
            ? '已采纳 1 条，返回知识块 ID：' + d.chunk_ids.join('、') + '。请核对候选状态和库存。'
            : '已弃用 1 条，原记录保留。',
        reopen,
      };
    });
  }
  function review(id, action, answer, source, reopen) {
    return prepare(async () => {
      const row = await request('/api/review/' + id);
      if (action === 'publish' ? row.status !== 'publishing' : row.status !== 'pending')
        throw new Error('审核状态已变化，请重新查看记录。');
      let material;
      if (action === 'approve') {
        if (!answer.trim() || !source) throw new Error('请填写人工确认答案并选择可信材料。');
        material = await request('/api/review/materials/' + encodeURIComponent(source));
        if (!material.text.includes(answer.trim()))
          throw new Error('核准答案必须是可信材料中的连续原文，请返回修改。');
      }
      const labels = { approve: '核准并发布', reject: '驳回审核', publish: '重试发布' };
      return {
        title: labels[action],
        path: '/api/review/' + id + '/' + action,
        data:
          action === 'approve' ? { approved_answer: answer.trim(), source_ref: source } : undefined,
        body:
          fields([
            ['审核 ID', '#' + id],
            [
              '当前状态',
              {
                pending: '待审',
                publishing: '发布中',
                approved: '已通过',
                rejected: '已驳回',
                idle: '本次未运行',
                running: '运行中',
                ok: '进程执行完成',
                failed: '进程执行失败',
                stopped: '已停止',
              }[row.status] || '未知',
            ],
            ['可信材料', source || row.source_ref],
            ['材料指纹', material?.sha256 || row.source_digest],
          ]) +
          full('标准问题', row.question) +
          full('人工确认答案', action === 'approve' ? answer.trim() : row.answer || '未核准') +
          `<p class="notice section-gap">${action === 'reject' ? '保留审核记录，标为驳回，不新增知识。' : '将复用现有定向发布流程，保存核准结果、写知识块并调用嵌入服务。返回 202 表示发布尚未完成，需核对后重试；不会重新核准。'}</p>`,
        valid: (d, status) =>
          d.id === Number(id) &&
          ['publishing', 'approved', 'rejected'].includes(d.status) &&
          (status === 202
            ? d.status === 'publishing'
            : action === 'reject'
              ? d.status === 'rejected'
              : d.status === 'approved'),
        result: (d, status) =>
          status === 202
            ? '核准记录已保存，发布尚未完成。请查看当前状态与发布异常，修复依赖后人工重试。'
            : d.status === 'rejected'
              ? '已驳回，未新增知识。'
              : '审核与发布已完成。' + (d.chunk_id ? '知识块 #' + d.chunk_id + '。' : ''),
        reopen,
      };
    });
  }
  const jobEffects = {
    'kb-preview': '读取现有材料并输出切块预览日志，不写知识库、不调用模型。',
    'kb-build': '读取现有材料并写入 MySQL pending 原文，之后另行补齐向量。',
    'kb-vectorize': '处理启动时全库 pending 原文，调用嵌入服务并写入 Milvus。',
    'finetune-golden': '调用聊天模型核对黄金样例，并更新校验报告。',
    'finetune-corpus': '从现有数据构建语料，调用聊天模型并更新语料产物。',
    'finetune-dataset': '划分、增强数据集，调用聊天模型并更新数据集文件。',
    'finetune-train': '训练分类器，消耗本机计算资源并更新模型产物。',
    'finetune-eval': '读取已有权重与测试集，更新测试集评测报告。',
    'finetune-export': '读取已有权重并更新 ONNX 导出产物和对齐报告。',
    'finetune-threshold-scan': '使用验证集与分类服务更新扫描报告，按现有脚本执行。',
    'classifier-up': '启动本地分类服务，进程持续运行，直至停止。',
    'classify-pool': '分类现有问题池并写入归类结果。',
    'classify-pool-force': '强制处理不足一批的问题池，写入归类结果。',
    'classify-history': '分类历史用户提问，写入现有隔离结果库，不改业务表。',
  };
  function job(name, stop, reopen) {
    return prepare(async () => {
      if (!Object.hasOwn(jobEffects, name)) throw new Error('此作业没有登记操作范围。');
      const row = await request('/api/jobs/' + encodeURIComponent(name));
      if (row.name !== name || !['idle', 'running', 'ok', 'failed', 'stopped'].includes(row.status))
        throw new Error('作业状态暂无法确认。');
      if (stop ? row.status !== 'running' : row.status === 'running')
        throw new Error(stop ? '此作业已经不在运行。' : '同一作业正在运行，请查看日志。');
      if (!stop && name === 'kb-vectorize') {
        const kb = await request('/api/kb/overview');
        if (
          kb.db_error ||
          !Number.isInteger(kb.chunks?.pending) ||
          kb.chunks.pending < 1 ||
          kb.milvus?.online !== true
        )
          throw new Error('当前没有可补齐原文，或原文/向量服务不可用。请先核对索引状态。');
      }
      return {
        title: stop ? '停止作业' : '启动作业',
        path: '/api/jobs/' + name + (stop ? '/stop' : ''),
        timeout: 30000,
        body:
          fields([
            ['作业', row.title],
            ['登记名称', name],
            [
              '当前状态',
              {
                pending: '待审',
                publishing: '发布中',
                approved: '已通过',
                rejected: '已驳回',
                idle: '本次未运行',
                running: '运行中',
                ok: '进程执行完成',
                failed: '进程执行失败',
                stopped: '已停止',
              }[row.status] || '未知',
            ],
            ['执行条件', row.needs],
            ['开始时间', row.started_at],
          ]) +
          `<p class="notice section-gap">${esc(stop ? '将终止当前作业及其子进程。已经完成的数据库写入、文件产物不会撤回，停止后需核对部分结果。' : jobEffects[name] + ' 本次日志将按现有运行器重建；请确认依赖、材料和运行资源已就绪。')}</p>`,
        valid: (d) =>
          d.name === name &&
          ['running', 'ok', 'failed', 'stopped'].includes(d.status) &&
          (!stop || ['stopped', 'ok', 'failed'].includes(d.status)),
        result: (d) =>
          '后端当前状态：' +
          { running: '运行中', ok: '进程执行完成', failed: '进程执行失败', stopped: '已停止' }[
            d.status
          ] +
          '。请查看日志，再到业务页核对结果。',
        reopen,
      };
    });
  }
  function evaluation(topK, generate, reopen) {
    return prepare(async () => {
      const state = await request('/api/knowledge/evaluation-state'),
        cases = await request('/api/knowledge/cases');
      if (state.running) throw new Error('已有评估正在运行，请先查看状态。');
      if (!Array.isArray(cases.cases) || !cases.cases.length)
        throw new Error('固定题集为空或不可读取。');
      if (!Number.isInteger(topK) || topK < 1 || topK > 50)
        throw new Error('top_k 需为 1–50 的整数。');
      return {
        title: '运行 RAG 评估',
        path: '/api/knowledge/evaluate',
        data: { top_k: topK, generate },
        timeout: 610000,
        body:
          fields([
            ['当前固定题集', cases.cases.length + ' 题'],
            ['每题检索 top_k', topK],
            ['生成回答', generate ? '启用' : '关闭'],
          ]) +
          `<p class="notice section-gap">执行现有四策略评估并更新 RAG 报告，最长约 10 分钟。检索可能使用嵌入和重排服务；${generate ? '同时调用聊天模型生成回答。' : '仅评估检索，不生成回答。'}失败保留旧报告，页面不会将旧报告标为本次成功。</p>`,
        valid: (d) =>
          typeof d.created_at === 'string' &&
          Array.isArray(d.dataset) &&
          Array.isArray(d.details) &&
          d.generation === generate,
        result: (d) =>
          '本次评估已返回并保存报告，时间：' + d.created_at + '。请核对逐题结果与失败调用。',
        reopen,
      };
    });
  }
  function processReviews(reopen) {
    return prepare(async () => ({
      title: '生成待审建议',
      path: '/api/review/process?limit=20',
      body: '<p>按现有处理器读取最多 20 条尚未归并的问题，检索知识并调用聊天模型生成建议，写入待审队列。不会自动核准或发布知识。</p><p class="notice section-gap">已有归并、隐私与来源约束继续由后端执行；生成建议仍需人工核对。</p>',
      valid: (d) =>
        ['created', 'merged', 'skipped'].every((key) => Number.isInteger(d[key]) && d[key] >= 0),
      result: (d) =>
        `新增待审 ${d.created} 条，归并 ${d.merged} 条，跳过 ${d.skipped} 条。请查询当前队列。`,
      reopen,
    }));
  }
  function onClick(el) {
    const a = el.dataset.adminAction;
    if (!a) return false;
    if (ui.actionBusy) return true;
    if (a === 'cancel' || a === 'reopen') {
      const reopen = pending?.reopen;
      pending = null;
      sequence++;
      if (reopen) reopen();
      else dialog().close();
    }
    return true;
  }
  function onSubmit(event) {
    if (event.target.id !== 'admin-confirm-form') return false;
    event.preventDefault();
    execute();
    return true;
  }
  function reset() {
    pending = null;
    sequence++;
  }
  return {
    candidate,
    review,
    job,
    evaluation,
    processReviews,
    onClick,
    onSubmit,
    reset,
    available,
    fields,
    full,
  };
};
