"""Minihelp 知识库与 微调 作业的跨平台白名单入口。"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    "kb-mine": "scripts.mine_kb",
    "staff-create": "scripts.create_staff",
    "kb-preview": "scripts.preview_kb",
    "kb-build": "scripts.build_kb",
    "kb-vectorize": "scripts.vectorize_kb",
    "finetune-golden": "scripts.finetune.validate_golden",
    "finetune-corpus": "scripts.finetune.build_corpus",
    "finetune-dataset": "scripts.finetune.build_dataset",
    "finetune-train": "scripts.finetune.train",
    "finetune-eval": "scripts.finetune.evaluate",
    "finetune-export": "scripts.finetune.export_onnx",
    "finetune-threshold-scan": "scripts.finetune.scan_threshold_replay",
    "classifier-up": "scripts.finetune.serve",
    "classify-pool": "scripts.finetune.classify_pool",
    "classify-pool-force": "scripts.finetune.classify_pool",
    "classify-history": "scripts.finetune.classify_history",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=sorted(MODULES))
    args, extra = parser.parse_known_args()
    if args.name == "classify-pool-force":
        extra = ["--force", *extra]
    return subprocess.call(
        [sys.executable, "-m", MODULES[args.name], *extra],
        cwd=ROOT,
        env={**os.environ, "PYTHONUTF8": "1"},
    )


if __name__ == "__main__":
    raise SystemExit(main())
