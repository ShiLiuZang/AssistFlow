# 模块：验收API
# 提供智能客服主题分类模型的完整验收流程接口
# 覆盖数据准备、模型训练、评测、错例分析、在线服务等九大验收区块
# 核心职责：确保模型在投产前通过黄金样例、测试集评测、阈值扫描等质量闸门

import json
import pathlib
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import jobs
from app.core import topic_views
from app.core.taxonomy import SEVERITY, TOPIC_NAMES
from app.core.auth import current_staff
from app.core.ratelimit import limit_staff_model

router = APIRouter(prefix="/api/acceptance", dependencies=[Depends(current_staff)])


FINETUNE_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "finetune"
REPORTS = FINETUNE_DIR / "reports"
DATASET = FINETUNE_DIR / "dataset"
MODEL = FINETUNE_DIR / "model"
ONNX = FINETUNE_DIR / "onnx"
CLASSIFIER = "http://127.0.0.1:8110"

# 语料血缘：从原始捞取到最终标注的三阶段流水线
LINEAGE = (
    ("corpus_raw.jsonl", "取数", "低置信度问题池优先；为空时取历史用户提问，落盘前脱敏", "finetune-corpus"),
    ("corpus_clean.jsonl", "脱敏去重", "去手机号/单号 → 去重 → LLM 修错别字 → 再去重", "finetune-corpus"),
    ("corpus_labeled.jsonl", "预标 + 模拟补足", "LLM 预标真实问题,再按类补造到每类 100 条", "finetune-corpus"),
)

# 数据集三分：训练用于学习、验证用于选参数、测试用于最终验收
SPLITS = (("train", "训练集(含增强与定向补数)"), ("val", "验证集(挑轮次 + 定阈值)"),
          ("test", "测试集(留出考卷,只在评测用一次)"))

# 模型投产三件套：权重文件、分词器配置、分类阈值
MODEL_TRIO = ("model.safetensors", "tokenizer.json", "threshold.json")


def _stat(path: pathlib.Path) -> dict:
    """
    文件盘点统一口径：检查文件是否存在及基本元信息

    参数:
        path: 待检查的文件路径

    返回:
        包含路径、存在性、字节数、修改时间的字典
        对于jsonl/md文件额外统计非空行数

    设计说明:
        行数统计仅针对文本类产物，排除空行确保反映实际内容量
    """
    if not path.exists():
        return {"path": str(path), "present": False}
    st = path.stat()
    out = {"path": str(path), "present": True, "bytes": st.st_size,
           "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}

    # 仅对文本类产物统计行数，排除空行
    if path.suffix in (".jsonl", ".md"):
        out["lines"] = sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                           if line.strip())
    return out


def _load_report(name: str, make_target: str) -> dict:
    """
    加载验收报告JSON文件

    参数:
        name: 报告文件名（如 "eval_report.json"）
        make_target: 对应的make任务名（如 "finetune-eval"）

    返回:
        包含报告内容的字典，缺失时返回提示信息和任务入口

    设计说明:
        产物不存在不视为错误，而是返回引导用户生成产物的提示
        确保前端可以展示"未生成"状态并提供执行入口
    """
    path = REPORTS / name
    if not path.exists():
        return {"present": False, "make": make_target,
                "hint": f"产物还没生成，先运行 python -m scripts.tasks {make_target}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"present": False, "make": make_target, "hint": f"产物解析失败:{e}"}
    data["present"] = True
    data["make"] = make_target
    return data


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    """
    读取JSONL文件（每行一个JSON对象）

    参数:
        path: JSONL文件路径

    返回:
        解析后的字典列表，文件不存在返回空列表
    """
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _origin_counts(rows: list[dict]) -> dict[str, int]:
    """
    统计语料来源分布

    参数:
        rows: 语料记录列表，每条包含origin字段

    返回:
        来源 -> 数量的映射字典

    设计说明:
        缺失origin字段的记录归入"unmarked"类，确保所有数据都被计数
    """
    counts: dict[str, int] = {}
    for row in rows:
        origin = row.get("origin") or "unmarked"
        counts[origin] = counts.get(origin, 0) + 1
    return counts


def _split_stats() -> dict:
    """
    统计三份数据集的规模、标签分布及数据泄漏情况

    返回:
        包含各数据集统计信息、泄漏检测结果的字典

    核心逻辑:
        1. 遍历训练/验证/测试三个数据集
        2. 统计每个数据集的样本数、多标签样本数、各类标签计数
        3. 提取所有文本内容用于交叉检测
        4. 计算三对数据集之间的文本重叠数量

    质量闸门:
        验证集和测试集是考卷，一旦被训练集见过，所有评测分数都不作数
        leaks必须全为0，否则模型可能记住了答案而非真正学会
    """
    texts: dict[str, set[str]] = {}
    out: dict[str, dict] = {}
    for key, desc in SPLITS:
        rows = _read_jsonl(DATASET / f"{key}.jsonl")
        counts = {n: 0 for n in TOPIC_NAMES}
        multi = 0
        for r in rows:
            labels = r.get("labels") or []
            multi += len(labels) > 1  # 统计多标签样本数
            for lb in labels:
                if lb in counts:
                    counts[lb] += 1
        texts[key] = {r["text"] for r in rows}
        out[key] = {"desc": desc, "size": len(rows), "multi_label": multi,
                    "origins": _origin_counts(rows),
                    "counts": counts, "file": _stat(DATASET / f"{key}.jsonl")}

    # 数据泄漏检测：计算三对数据集之间的文本重叠
    leaks = {
        "train_val": len(texts.get("train", set()) & texts.get("val", set())),
        "train_test": len(texts.get("train", set()) & texts.get("test", set())),
        "val_test": len(texts.get("val", set()) & texts.get("test", set())),
    }
    return {"splits": out, "leaks": leaks, "clean": sum(leaks.values()) == 0}


async def _probe_classifier() -> dict:
    """
    探测8110端口的ONNX分类服务是否在线

    返回:
        包含在线状态和详细信息的字典

    设计说明:
        服务离线不视为错误，而是返回状态描述
        前端根据此状态决定是否显示"拉起服务"按钮
        2秒超时快速失败，避免阻塞整个验收页面加载
    """
    # 先检查ONNX产物是否齐全，缺失则无法启动服务
    if not all((ONNX / name).exists() for name in
               ("model.onnx", "tokenizer.json", "threshold.json")):
        return {"online": False, "detail": "当前项目尚无 ONNX 分类器产物"}
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{CLASSIFIER}/healthz")
            r.raise_for_status()
            return {"online": True, "detail": r.json()}
    except Exception as e:
        return {"online": False, "detail": f"{type(e).__name__}: {e}"}


def _threshold_in_use() -> float | None:
    """
    读取当前使用的分类阈值

    返回:
        阈值浮点数，文件不存在返回None

    设计说明:
        threshold.json由阈值扫描任务生成，记录验证集上选出的最优阈值
        评测和在线服务都读取此文件，确保阈值一致性
    """
    path = MODEL / "threshold.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("threshold")


@router.get("/overview")
async def overview() -> dict:
    """
    验收总览：九个区块的完整状态仪表盘

    返回:
        包含九大验收区块状态、通过数、任务列表的字典

    九大区块:
        1. 数据与语料：原始捞取到数据集切分的完整血缘
        2. 黄金样例闸：手工标注的黄金集合，通过率必须达标
        3. 训练产物：模型权重、分词器、阈值三件套
        4. ONNX导出：转换到推理格式并验证与PyTorch一致性
        5. 测试集评测：留出考卷的F1分数，分严档/中档红线
        6. 阈值扫描：九候选阈值重演，确认最优值一致性
        7. 混淆矩阵：错误的方向比错误的数量更重要
        8. 错例复核：逐条分析漏打/多打/错位，指导补数方向
        9. 旁路批量归类：用训练好的模型对历史数据或问题池打标签

    状态口径:
        missing - 产物还未生成
        fail - 产物存在但未达标
        pass - 产物存在且达标

    设计说明:
        所有子任务并发查询，避免串行等待
        每个区块都关联make任务，前端可一键触发生成
    """
    # 并发加载所有报告和状态
    golden = _load_report("golden_report.json", "finetune-golden")
    evaluation = _load_report("eval_report.json", "finetune-eval")
    scan = _load_report("threshold_scan.json", "finetune-threshold-scan")
    export = _load_report("export_report.json", "finetune-export")
    ds = _split_stats()

    # 检查数据产物完整性：语料血缘四段文件 + 三份数据集文件
    data_present = all((FINETUNE_DIR / filename).exists() for filename, *_ in LINEAGE) and all(
        split["file"]["present"] for split in ds["splits"].values()
    )

    health = await _probe_classifier()
    trio = {n: _stat(MODEL / n) for n in MODEL_TRIO}
    trio_present = all(item["present"] for item in trio.values())

    # 尝试读取主题归类统计，区分历史会话和问题池两种数据源
    try:
        dist = await topic_views.distribution()
        dist_total, dist_hit = dist["total"], sum(1 for c in dist["classes"] if c["count"])
        dist_source = dist.get("source", "low_confidence_pool")
        dist_err = None
    except Exception:
        dist_total = dist_hit = None
        dist_source = None
        dist_err = "主题归类表未迁移或数据库不可用"

    # 根据数据源选择对应的归类任务报告
    classify = (_load_report("history_classify_run.json", "classify-history")
                if dist_source == "conversation_history"
                else _load_report("classify_run.json", "classify-pool"))

    def gate(present: bool, ok: bool | None) -> str:
        """根据产物存在性和达标情况返回闸门状态"""
        if not present:
            return "missing"
        return "pass" if ok else "fail"

    def note(present: bool, ok: bool | None, yes: str, no: str) -> str:
        """
        生成区块的提示文案

        参数:
            present: 产物是否存在
            ok: 是否达标（None表示无达标概念）
            yes: 达标时的文案
            no: 未达标时的文案

        设计说明:
            产物未生成时不能显示"未达标"，因为未跑过≠没过线
            这会误导用户采取错误的修复动作
        """
        if not present:
            return "还没跑过,点右下按钮现场跑一遍"
        return yes if ok else no

    corpus_lines = {f: _stat(FINETUNE_DIR / f).get("lines") for f, *_ in LINEAGE}

    # 构建九大验收区块
    blocks = [
        # 区块1: 数据与语料 - 从原始捞取到数据集切分的完整链路
        {"key": "data", "no": 1, "title": "语料与数据集", "page": "/acceptance/data",
         "status": gate(data_present, ds["clean"] and bool(ds["splits"]["test"]["size"])),
         "headline": (f"{corpus_lines['corpus_raw.jsonl']} 条捞池 → "
                      f"{corpus_lines['corpus_clean.jsonl']} 条清洗 → "
                      f"{corpus_lines['corpus_labeled.jsonl']} 条语料 → "
                      f"{ds['splits']['train']['size']}/{ds['splits']['val']['size']}"
                      f"/{ds['splits']['test']['size']} 训练/验证/测试"
                      if data_present else "语料或训练/验证/测试集尚未生成"),
         "note": ("请先构建主题语料与数据集" if not data_present else
                  "测试集为空,不能验收" if not ds["splits"]["test"]["size"] else
                  "考卷与练习题零重叠" if ds["clean"] else "训练集与考卷有重叠,分数不作数"),
         "jobs": ["finetune-corpus", "finetune-dataset"]},

        # 区块2: 黄金样例闸 - 手工标注的高质量样例集，通过率必须达标
        {"key": "golden", "no": 2, "title": "黄金样例闸", "page": None,
         "status": gate(golden.get("present", False), golden.get("passed")),
         "headline": (f"通过率 {golden['rate']:.0%}(闸线 {golden['pass_line']:.0%}),"
                      f"{golden['hits']}/{golden['total']} 条集合全对"
                      if golden.get("present") else golden.get("hint", "")),
         "note": (f"{len(golden.get('failures', []))} 条错例;不过线就改 prompt,"
                  "不许改黄金样例来凑分" if golden.get("present")
                  else "还没跑过,点右下按钮现场跑一遍"),
         "jobs": ["finetune-golden"]},

        # 区块3: 训练产物 - 模型权重、分词器、阈值三件套
        {"key": "train", "no": 3, "title": "训练产物", "page": "/acceptance/data",
         "status": gate(trio_present, trio_present),
         "headline": (f"权重 {trio['model.safetensors']['bytes'] / 1024 / 1024:.0f}MB · "
                      f"tokenizer · threshold {_threshold_in_use()}"
                      if trio_present else "模型权重、tokenizer 或阈值文件尚未生成"),
         "note": "三件套齐全,评测与服务都读 threshold.json"
                 if trio_present else "权重三件套不全",
         "jobs": ["finetune-train"]},

        # 区块4: ONNX导出 - 转推理格式并验证与PyTorch一致性
        {"key": "export", "no": 4, "title": "ONNX 导出与服务", "page": None,
         "status": gate(export.get("present", False),
                        export.get("passed") and health["online"]),
         "headline": (f"{export['checked']} 条预测与 torch 一致"
                      f"(不一致 {export['mismatch']} 条) · :8110 "
                      f"{'在线' if health['online'] else '离线'}"
                      if export.get("present") else export.get("hint", "")),
         "note": "导出后必须逐条对齐 torch 才放行",
         "jobs": ["finetune-export", "classifier-up"]},

        # 区块5: 测试集评测 - 留出考卷的最终成绩，分严档/中档红线
        {"key": "eval", "no": 5, "title": "测试集评测", "page": "/acceptance/eval",
         "status": gate(evaluation.get("present", False), evaluation.get("red_line_passed")),
         "headline": (f"micro-F1 {evaluation['micro']['f1']:.3f} · "
                      f"macro-F1 {evaluation['macro']['f1']:.3f} · "
                      f"测试集 {evaluation['test_size']} 条"
                      if evaluation.get("present") else evaluation.get("hint", "")),
         "note": (note(evaluation.get("present", False), evaluation.get("red_line_passed"),
                       "严档 F1 ≥ 0.9、中档 ≥ 0.8 全部达标", "有类目跌破容错红线,回头搞数据")
                  + (f"；真实提问测试样本 {evaluation.get('real_subset', {}).get('size', 0)}/"
                     f"{evaluation['test_size']} 条" if evaluation.get("present") else "")),
         "jobs": ["finetune-eval"]},

        # 区块6: 阈值扫描 - 九候选阈值重演，确认最优值一致性
        {"key": "threshold", "no": 6, "title": "阈值扫描", "page": "/acceptance/eval",
         "status": gate(scan.get("present", False), scan.get("consistent")),
         "headline": (f"九候选线重演,当选 {scan['best_threshold']}"
                      f"(验证集 micro-F1 {scan['best_micro_f1']:.4f})"
                      if scan.get("present") else scan.get("hint", "")),
         "note": note(scan.get("present", False), scan.get("consistent"),
                      f"与 threshold.json 在用的 {scan.get('in_use_threshold')} 一致",
                      "重演结果与在用阈值不一致"),
         "jobs": ["finetune-threshold-scan"]},

        # 区块7: 混淆矩阵 - 错误的方向比数量更重要
        {"key": "matrix", "no": 7, "title": "混淆矩阵", "page": "/acceptance/eval",
         "status": gate(evaluation.get("present", False), True),
         "headline": (f"{evaluation['total_cells']} 道是非题错 "
                      f"{evaluation['total_fp'] + evaluation['total_fn']} 道:"
                      f"冤枉 {evaluation['total_fp']} · 放跑 {evaluation['total_fn']}"
                      if evaluation.get("present") else evaluation.get("hint", "")),
         "note": "要紧的不是错几个,是错的方向",
         "jobs": ["finetune-eval"]},

        # 区块8: 错例复核 - 逐条分析漏打/多打/错位，指导补数方向
        {"key": "errors", "no": 8, "title": "错例复核", "page": "/acceptance/errors",
         "status": gate(evaluation.get("present", False), True),
         "headline": (f"{len(evaluation.get('errors', []))} 条错例,"
                      f"记 {sum(e['matrix_entries'] for e in evaluation.get('errors', []))} 笔矩阵账"
                      if evaluation.get("present") else evaluation.get("hint", "")),
         "note": "错例条数 ≠ 矩阵笔数:错位一条记两笔",
         "jobs": ["finetune-eval"]},

        # 区块9: 旁路批量归类 - 用训练好的模型对历史数据或问题池打标签
        {"key": "classify", "no": 9, "title": "旁路批量归类", "page": "/topics",
         "status": gate(classify.get("present", False), classify.get("status") != "failed"),
         "headline": ((f"{'历史会话' if classify.get('source') == 'conversation_history' else '问题池'}"
                       f"上次归类写入 {classify['written']} 条"
                       if classify.get("status") == "done"
                       else ("历史会话已全部归类，本次写入 0 条(幂等)"
                             if classify.get("source") == "conversation_history"
                             else "上次跑批:池里没有待归类问题(幂等)")
                       if classify.get("status") == "empty"
                       else f"待归类 {classify.get('pending')} 条,不足一批")
                      if classify.get("present") else classify.get("hint", "")),
         "note": (f"{'历史会话隔离归类' if dist_source == 'conversation_history' else 'topic_classifications'}"
                  f" 共 {dist_total} 条,命中 {dist_hit}/17 类"
                  if dist_total is not None else f"库里读数失败:{dist_err}"),
         "jobs": ["classify-history", "classify-pool", "classify-pool-force"]},
    ]

    passed = sum(b["status"] == "pass" for b in blocks)
    return {"blocks": blocks, "passed": passed, "total": len(blocks),
            "all_pass": passed == len(blocks), "classifier": health,
            "jobs": jobs.status_all()}


@router.get("/eval")
async def eval_detail() -> dict:
    """
    评测详情页数据

    返回:
        包含评测报告、阈值扫描、当前阈值、严重性分级的完整字典

    数据内容:
        - 每个类别的精确率/召回率/F1/样本数/红线达标情况
        - 混淆矩阵：17×17的预测对照表
        - micro-F1（所有样本平均）vs macro-F1（每类平均再平均）
        - 阈值扫描的九候选线及各自F1分数

    设计说明:
        评测报告中的errors字段包含大量错例详情，占用空间大
        此接口剔除errors避免传输冗余，错例复核有专门接口
    """
    evaluation = _load_report("eval_report.json", "finetune-eval")
    # 移除errors字段，错例详情由专门接口提供
    evaluation.pop("errors", None)
    scan = _load_report("threshold_scan.json", "finetune-threshold-scan")
    return {"eval": evaluation, "scan": scan,
            "threshold_in_use": _threshold_in_use(),
            "severity": SEVERITY, "classifier": await _probe_classifier()}


@router.get("/data")
async def data_detail() -> dict:
    """
    数据产物详情页数据

    返回:
        包含语料血缘、数据集统计、模型产物、ONNX产物的完整字典

    数据内容:
        - 语料血缘：从原始捞取到最终标注的四段流水线
        - 语料来源统计：真实问题、LLM补足等各来源占比
        - 数据集分布：训练/验证/测试三份的规模、标签计数、数据泄漏检测
        - 样本复核记录：人工审核语料质量的markdown文件
        - 模型产物：权重、分词器、阈值三件套
        - ONNX产物：推理格式转换结果及对齐报告
    """
    lineage = [{"file": f, "stage": stage, "desc": desc, "make": target,
                **_stat(FINETUNE_DIR / f)} for f, stage, desc, target in LINEAGE]
    return {
        "lineage": lineage,
        "corpus_origins": _origin_counts(_read_jsonl(FINETUNE_DIR / "corpus_labeled.jsonl")),
        "dataset": _split_stats(),
        "sample_review": _stat(FINETUNE_DIR / "sample_review.md"),
        "model": {"files": [_stat(p) for p in sorted(MODEL.glob("*")) if p.is_file()],
                  "threshold": _threshold_in_use(),
                  "threshold_file": _stat(MODEL / "threshold.json"),
                  "trio_ok": all((MODEL / n).exists() for n in MODEL_TRIO)},
        "onnx": {"files": [_stat(p) for p in sorted(ONNX.glob("*")) if p.is_file()],
                 "report": _load_report("export_report.json", "finetune-export")},
        "topic_names": list(TOPIC_NAMES),
    }


@router.get("/errors")
async def errors_detail() -> dict:
    """
    错例复核页数据

    返回:
        包含错例列表、错误类型统计、边界摩擦配对、修复建议的完整字典

    核心功能:
        1. 逐条展示预测错误的样本及其标准/预测标签对照
        2. 统计漏打/多打/错位三种错误模式的分布
        3. 计算边界摩擦配对：哪些类之间经常混淆

    边界摩擦配对:
        记录"该打没打的类 ← 反而打了的类"的出现次数
        同一对反复出现说明两类边界模糊，需要成对补对照句
        补什么句子需要人工判断，此接口只提供统计线索

    修复建议:
        - 漏打：补"主诉求+顺带诉求"的双标签句
        - 错位：成对补对照句，让模型学会看语境
        - 多打：补该类的反例（近似但不属于它的句子）
    """
    evaluation = _load_report("eval_report.json", "finetune-eval")
    if not evaluation.get("present"):
        return {"eval": evaluation, "errors": [], "kinds": {}, "pairs": []}

    errors = evaluation.get("errors", [])
    kinds: dict[str, int] = {}
    pairs: dict[tuple[str, str], int] = {}

    # 统计错误类型和边界摩擦配对
    for e in errors:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        # 计算每个漏打类与每个多打类之间的混淆次数
        for miss in e["missed"]:
            for extra in e["extra"]:
                pairs[(miss, extra)] = pairs.get((miss, extra), 0) + 1

    return {
        "eval": {k: evaluation[k] for k in ("ran_at", "test_size", "threshold", "present")},
        "errors": errors,
        "kinds": kinds,
        "matrix_entries": sum(e["matrix_entries"] for e in errors),
        "total_fp": evaluation["total_fp"], "total_fn": evaluation["total_fn"],
        # 按出现次数降序排列配对，附加严重性等级
        "pairs": [{"missed": m, "grabbed": g, "count": c, "severity": SEVERITY.get(m)}
                  for (m, g), c in sorted(pairs.items(), key=lambda x: -x[1])],
        "recipes": {
            "漏打": "次要诉求被主旋律淹没 → 补「主诉求 + 顺带诉求」的双标签句",
            "错位": "某个词横跨两类 → 成对补对照句,两边同时喂才学得会看语境",
            "多打": "边界过宽把邻类也扫进来 → 补该类的反例(近似但不属于它的句子)",
        },
    }


@router.get("/service")
async def service() -> dict:
    """
    分类服务状态查询

    返回:
        包含服务在线状态、当前阈值、ONNX产物存在性的字典

    用途:
        前端用此接口判断是否显示"拉起服务"或"测试分类"按钮
    """
    return {**await _probe_classifier(), "threshold": _threshold_in_use(),
            "onnx_present": (ONNX / "model.onnx").exists()}


class ClassifyIn(BaseModel):
    """单句分类请求体"""
    text: str


@router.post("/classify", dependencies=[Depends(limit_staff_model)])
async def classify(body: ClassifyIn) -> dict:
    """
    单句试分类接口

    参数:
        body: 包含待分类文本的请求体

    返回:
        包含17类分数、过线标签、是否触发兜底的完整字典

    核心功能:
        将一句话发送给8110端口的ONNX分类服务
        返回17类各自的置信度分数及过线标签列表

    多标签机制:
        17类各自独立过阈值，过几个打几个
        如果所有类都未过阈值，触发兜底流程

    设计说明:
        此接口主要用于验收页面演示分类效果
        让用户现场看到"独立过阈值"和"多标签"的运作机制
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="请输入一句话")

    # 检查ONNX产物完整性
    if not all((ONNX / name).exists() for name in
               ("model.onnx", "tokenizer.json", "threshold.json")):
        raise HTTPException(status_code=503, detail="当前项目尚无 ONNX 分类器产物")

    # 调用分类服务
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{CLASSIFIER}/classify", json={"texts": [text]})
            r.raise_for_status()
            result = r.json()["results"][0]
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"分类器服务不可用({type(e).__name__}),先拉起 :8110") from e

    threshold = _threshold_in_use()
    # 按分数降序排列，方便前端展示
    scores = sorted(result["scores"].items(), key=lambda x: -x[1])

    return {"text": text, "threshold": threshold, "labels": result["labels"],
            "scores": [{"label": k, "score": v, "hit": k in result["labels"]}
                       for k, v in scores],
            # 兜底判断：最高分也未过阈值
            "fallback": bool(threshold is not None and scores
                             and scores[0][1] < threshold)}
