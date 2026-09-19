"""python -m scripts.preview_kb：只读预览，无数据库和模型调用。"""
import json
from dataclasses import asdict
from app.kb.documents import build_chunks
from app.kb.sources import KB_DIR, SOURCE_TYPES


def main():
    for name, content_type in SOURCE_TYPES.items():
        for index, chunk in enumerate(build_chunks((KB_DIR / name).read_text(encoding="utf-8"), content_type)):
            print(json.dumps({"source_file": name, "chunk_index": index, **asdict(chunk)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
