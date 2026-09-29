"""微调 数据集:分层划分 80/10/10 + 训练集增强(同义词替换/句式微调)。
增强只扩训练集——验证/测试是考题,不许照练习题变。运行:make finetune-dataset(需聊天上游)。"""
import asyncio
import json
import pathlib

from app.core.llm import get_chat_model
from app.core.taxonomy import TOPIC_NAMES
from scripts.finetune.corpus_lib import dedupe, split_dataset

SRC = pathlib.Path("data/finetune/corpus_labeled.jsonl")
OUT = pathlib.Path("data/finetune/dataset")


SUPPLEMENT = pathlib.Path(__file__).parent / "supplement_sizefit.jsonl"

AUGMENT_PROMPT = """把下面这句电商客服用户问题改写一个变体:换同义词、微调句式(比如改成「我想问一下……」的口气),
不改原意、不增删诉求。只输出改写后的句子。

{text}"""


async def augment(samples: list[dict], concurrency: int = 8) -> list[dict]:
    model = get_chat_model()
    sem = asyncio.Semaphore(concurrency)

    async def one(s: dict) -> dict | None:
        async with sem:
            try:
                r = await model.ainvoke(AUGMENT_PROMPT.format(text=s["text"]))
                t = r.content.strip()
            except Exception as e:
                print(f"[augment] 改写失败,丢弃该变体: {s['text'][:30]}… ({type(e).__name__})")
                return None
        return {"text": t, "labels": s["labels"], "origin": "augmented",
                "source_origin": s.get("origin"), "source_id": s.get("source_id")} if t else None

    outs = await asyncio.gather(*[one(s) for s in samples])
    return [o for o in outs if o]


def _dump(path: pathlib.Path, samples: list[dict]) -> None:
    path.write_text("\n".join(
        json.dumps({k: s[k] for k in ("text", "labels", "origin", "source_origin", "source_id")
                    if k in s}, ensure_ascii=False)
        for s in samples), encoding="utf-8")


def _dist(name: str, samples: list[dict]) -> None:
    counts = {n: 0 for n in TOPIC_NAMES}
    for s in samples:
        for lb in s["labels"]:
            counts[lb] += 1
    print(f"{name}({len(samples)} 条): " + " ".join(f"{k}={v}" for k, v in counts.items()))


async def main() -> None:
    samples = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    train, val, test = split_dataset(samples)
    aug = await augment(train)
    seen = {s["text"] for s in samples}
    train = train + [a for a in aug if a["text"] not in seen]
    if SUPPLEMENT.exists():
        sup = [json.loads(l) for l in SUPPLEMENT.read_text(encoding="utf-8").splitlines()
               if l.strip()]
        train = train + [{**s, "origin": "supplement"} for s in sup
                         if s["text"] not in seen]
    train = dedupe(train)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, ds in (("train", train), ("val", val), ("test", test)):
        _dump(OUT / f"{name}.jsonl", ds)
        _dist(name, ds)


if __name__ == "__main__":
    asyncio.run(main())
