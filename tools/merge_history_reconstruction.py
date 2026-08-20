#!/usr/bin/env python3
"""将历史重建摘要挂到动态历史实验室，但绝不混算真实冻结样本。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "astock_history" / "latest.json"
RECON = ROOT / "astock_history" / "reconstruction" / "latest.json"


def main():
    if not LIVE.exists():
        print('{"state":"skip","reason":"live history missing"}')
        return
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    if not RECON.exists():
        live.pop("reconstruction", None)
        live["sourceModes"] = {
            "default": "实时冻结",
            "available": ["实时冻结"],
            "noteZh": "历史重建尚未生成；当前页面只展示真实冻结样本。",
        }
        LIVE.write_text(json.dumps(live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print('{"state":"live-only"}')
        return

    recon = json.loads(RECON.read_text(encoding="utf-8"))
    # App 只需要研究摘要，不把大体量逐笔样本重复嵌入 live latest。
    public = {k: v for k, v in recon.items() if k not in {"samples", "cohorts", "failures"}}
    live["schemaVersion"] = max(int(live.get("schemaVersion") or 0), 3)
    live["sourceModes"] = {
        "default": "实时冻结",
        "available": ["实时冻结", "历史重建"],
        "strictlySeparated": True,
        "noteZh": "两套样本独立统计。历史重建仅用于研究和参数校准，不计入样本外战绩。",
    }
    live["reconstruction"] = public
    live["sourcePolicyZh"] = (
        "真实冻结样本用于样本外验证；历史重建样本独立展示，仅用于研究/校准。"
        "两者不合并样本数、不合并收益、不共享可信度评级。"
    )
    LIVE.write_text(json.dumps(live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "merged",
        "liveSamples": (live.get("overall") or {}).get("sampleCount"),
        "reconstructionSamples": ((public.get("overall") or {}).get("sampleCount")),
        "reconstructionVersion": public.get("version"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
