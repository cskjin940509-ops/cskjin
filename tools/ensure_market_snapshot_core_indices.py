#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "astock_gateway"
SNAPS = ROOT / "astock_snapshots" / "index.json"

CORE = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000300": "沪深300",
    "sh000852": "中证1000",
}


def fetch_quotes():
    url = "https://qt.gtimg.cn/q=" + ",".join(CORE)
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 AStockStrategy-CoreIndex/1.0","Referer":"https://gu.qq.com/","Cache-Control":"no-cache"})
    with urlopen(req, timeout=12) as r:
        text = r.read().decode("gbk", "replace")
    out = {}
    for sym, payload in re.findall(r'v_([A-Za-z0-9]+)="([^"]*)"', text):
        f = payload.split("~")
        if len(f) <= 37 or sym not in CORE:
            continue
        stamp = f[30] if len(f) > 30 else ""
        def n(i):
            try: return float(f[i])
            except Exception: return None
        out[sym] = {
            "name": CORE[sym], "close": n(3), "changePct": n(32),
            "amount": (n(37) * 10000.0) if n(37) is not None else None,
            "quoteTime": stamp[-6:] if len(stamp) >= 14 else None,
            "quoteDate": stamp[:8] if len(stamp) >= 8 else None,
        }
    return out


def patch_payload(payload, quotes, day):
    market = payload.get("marketSnapshot") or {}
    if market.get("sourceDate") != day:
        return False
    indices = market.setdefault("indices", {})
    changed = False
    for sym, row in quotes.items():
        if row.get("quoteDate") != day.replace("-", ""):
            continue
        clean = {k:v for k,v in row.items() if k != "quoteDate"}
        if indices.get(sym) != clean:
            indices[sym] = clean
            changed = True
    if changed:
        market["coreIndexCoverage"] = f"{sum(1 for s in CORE if s in indices)}/{len(CORE)}"
        market["coreIndexSource"] = "腾讯当日收盘快照"
    return changed


def main():
    now = datetime.now(CN)
    if now.weekday() >= 5:
        print(json.dumps({"state":"skip","reason":"non-trading-day"}, ensure_ascii=False)); return
    day = now.strftime("%Y-%m-%d")
    quotes = fetch_quotes()
    changed = []
    for path in (GATEWAY / "latest.json", GATEWAY / "history" / f"{day}.json"):
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if patch_payload(payload, quotes, day):
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            changed.append(str(path.relative_to(ROOT)))
    if SNAPS.exists():
        arr = json.loads(SNAPS.read_text(encoding="utf-8"))
        touched = False
        for item in arr:
            if item.get("date") == day and item.get("status") == "Official":
                if patch_payload(item, quotes, day): touched = True
                break
        if touched:
            SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            changed.append("astock_snapshots/index.json")
    print(json.dumps({"state":"updated" if changed else "unchanged","date":day,"files":changed,"quotes":len(quotes)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
