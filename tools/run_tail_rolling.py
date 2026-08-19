#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import run_tail_decision as core

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_tail"
HIST = OUT / "history"
INTRADAY = OUT / "intraday"
LATEST = OUT / "latest.json"
VERSION = "v1.1-tail-1430-1500-rolling"


def slot_for(now: datetime) -> str:
    if now.time() >= dtime(15, 0):
        return "1500"
    minute = (now.minute // 5) * 5
    if now.hour == 14 and minute < 30:
        minute = 30
    return f"{now.hour:02d}{minute:02d}"


def main():
    now = datetime.now(CN)
    day = now.strftime("%Y-%m-%d")
    dry_run = os.getenv("DRY_RUN", "0") == "1"
    allow_any = os.getenv("ALLOW_ANY_TIME", "0") == "1" or dry_run

    if now.weekday() >= 5:
        print(json.dumps({"state": "skip", "reason": "weekend", "date": day}, ensure_ascii=False))
        return

    if not allow_any and not (dtime(14, 30) <= now.time() < dtime(15, 6)):
        print(json.dumps({"state": "skip", "reason": "outside-rolling-tail-window", "capturedAt": now.isoformat(timespec="seconds")}, ensure_ascii=False))
        return

    HIST.mkdir(parents=True, exist_ok=True)
    INTRADAY.mkdir(parents=True, exist_ok=True)
    final_path = HIST / f"{day}.json"
    is_final = now.time() >= dtime(15, 0)

    if is_final and final_path.exists() and os.getenv("FORCE_REBUILD", "0") != "1":
        try:
            existing = json.loads(final_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        if existing.get("status") == "TailFinal":
            LATEST.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"state": "tail-final-immutable", "date": day, "capturedAt": existing.get("capturedAt")}, ensure_ascii=False))
            return

    if dry_run:
        core.main()
        return

    # Reuse the already-tested point-in-time scanner, but rolling controller owns persistence semantics.
    old_force = os.environ.get("FORCE_REBUILD")
    old_allow = os.environ.get("ALLOW_ANY_TIME")
    os.environ["FORCE_REBUILD"] = "1"
    os.environ["ALLOW_ANY_TIME"] = "1"
    try:
        core.main()
    finally:
        if old_force is None:
            os.environ.pop("FORCE_REBUILD", None)
        else:
            os.environ["FORCE_REBUILD"] = old_force
        if old_allow is None:
            os.environ.pop("ALLOW_ANY_TIME", None)
        else:
            os.environ["ALLOW_ANY_TIME"] = old_allow

    if not LATEST.exists():
        raise RuntimeError("tail scanner did not produce latest.json")

    result = json.loads(LATEST.read_text(encoding="utf-8"))
    slot = slot_for(now)
    result["strategyVersion"] = VERSION
    result["refreshIntervalMin"] = 5
    result["scheduledSlot"] = slot
    result["scheduledFor"] = f"{day}T{slot[:2]}:{slot[2:]}:00+08:00"
    result["isFinal"] = is_final

    if is_final:
        result["status"] = "TailFinal"
        result["phase"] = "收盘锁定"
        result["note"] = "14:30后每5分钟重算尾盘主线与筛选池；本批次为15:00收盘后第一次成功结果，已锁定。B1两融/B2 ETF申赎缺失时不伪造。"
        result["executionNote"] = "TailFinal 为当日尾盘最终留档；后续不会因盘后数据或未来表现改写本批次原始信号。"
        result["snapshotPath"] = f"astock_tail/history/{day}.json"
    else:
        result["status"] = "TailLive"
        result["phase"] = "尾盘滚动"
        result["note"] = "14:30后每5分钟使用当时可获得行情重新计算主线与筛选池；当前为盘中滚动结果，15:00后将再算一次并锁定。B1两融/B2 ETF申赎缺失时不伪造。"
        result["executionNote"] = "TailLive 仅用于尾盘决策参考，会在下一5分钟刷新；每个时点快照单独留档，不用未来数据回写。"
        result["snapshotPath"] = f"astock_tail/intraday/{day}/{slot}.json"

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    LATEST.write_text(text, encoding="utf-8")

    if is_final:
        final_path.write_text(text, encoding="utf-8")
    else:
        slot_dir = INTRADAY / day
        slot_dir.mkdir(parents=True, exist_ok=True)
        (slot_dir / f"{slot}.json").write_text(text, encoding="utf-8")
        # Before 15:00 there must be no file that can be mistaken for the day's final tail result.
        if final_path.exists():
            final_path.unlink()

    print(json.dumps({
        "state": "tail-final-frozen" if is_final else "tail-live-updated",
        "date": day,
        "slot": slot,
        "capturedAt": result.get("capturedAt"),
        "TailCore": len((result.get("pools") or {}).get("TailCore") or []),
        "confirmedMainlines": [x.get("name") for x in result.get("confirmedMainlines") or []],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
