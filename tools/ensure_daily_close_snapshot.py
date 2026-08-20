#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "astock_gateway"
LATEST = GATEWAY / "latest.json"
HISTORY = GATEWAY / "history"
CORE = ("sh000001", "sz399006", "sh000688", "sh000300", "sh000852")


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def hhmmss(value) -> int | None:
    if value is None:
        return None
    s = re.sub(r"\D", "", str(value))
    if len(s) >= 6:
        s = s[-6:]
    if len(s) != 6 or not s.isdigit():
        return None
    h, m, sec = int(s[:2]), int(s[2:4]), int(s[4:6])
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= sec <= 59):
        return None
    return h * 10000 + m * 100 + sec


def readiness(payload: dict, day: str) -> tuple[bool, dict]:
    market = payload.get("marketSnapshot") or {}
    heat = payload.get("boardHeatmap") or {}
    indices = market.get("indices") or {}
    times = {k: hhmmss((indices.get(k) or {}).get("quoteTime")) for k in CORE}
    close_count = sum(1 for t in times.values() if t is not None and t >= 145900)
    industry_count = len(heat.get("industry") or [])
    concept_count = len(heat.get("concept") or [])
    ok = (
        market.get("sourceDate") == day
        and bool(payload.get("verifiedToday"))
        and close_count >= 4
        and industry_count > 0
        and concept_count > 0
    )
    return ok, {
        "sourceDate": market.get("sourceDate"),
        "verifiedToday": payload.get("verifiedToday"),
        "closeCoreCount": close_count,
        "coreQuoteTimes": times,
        "industryCount": industry_count,
        "conceptCount": concept_count,
    }


def main() -> int:
    now = datetime.now(CN)
    day = now.date().isoformat()
    if now.weekday() >= 5:
        print(json.dumps({"state": "skip-non-trading-weekday", "date": day}, ensure_ascii=False))
        return 0
    if now.hour < 15:
        raise RuntimeError("尚未到15:00，禁止冻结日终市场快照")

    HISTORY.mkdir(parents=True, exist_ok=True)
    hist = HISTORY / f"{day}.json"

    # A scheduled run may start a little before all vendors expose final close.
    # Retry inside the same job so Official generation never depends on another workflow finishing first.
    attempts = 7
    for attempt in range(1, attempts + 1):
        run("tools/update_market_gateway.py")
        run("tools/sanitize_market_gateway.py")
        run("tools/ensure_market_snapshot_core_indices.py")

        payload = json.loads(LATEST.read_text(encoding="utf-8"))
        ok, detail = readiness(payload, day)
        if ok:
            payload["closeFreeze"] = {
                "state": "ready",
                "date": day,
                "frozenAt": datetime.now(CN).isoformat(timespec="seconds"),
                "ruleZh": "仅当至少4个核心指数行情时间达到14:59且当天行业/概念截面完整时冻结",
                **detail,
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            LATEST.write_text(text, encoding="utf-8")
            hist.write_text(text, encoding="utf-8")
            print(json.dumps({"state": "close-snapshot-ready", "date": day, "attempt": attempt, **detail}, ensure_ascii=False))
            return 0

        # update_market_gateway.py may have created a date-only history snapshot before
        # its quote-time freshness is adequate. Never allow that provisional file to feed Official.
        if hist.exists():
            hist.unlink()
        print(json.dumps({"state": "waiting-final-close", "date": day, "attempt": attempt, **detail}, ensure_ascii=False))
        if attempt < attempts:
            time.sleep(45)

    raise RuntimeError("收盘行情在自动重试窗口内仍未达到冻结条件；本轮不生成Official，等待下一兜底时点")


if __name__ == "__main__":
    raise SystemExit(main())
