#!/usr/bin/env python3
"""Enrich the A-share gateway with Yunai Quant API data.

Security:
- Reads YUNAI_TOKEN from environment only.
- Never writes the token, Authorization header, JWT payload, username, or user id.
- Yunai failures never break Tencent/Eastmoney fallback collection.

The first verified endpoint is the market-status endpoint supplied by the API user.
The script also probes common Knife4j/OpenAPI discovery endpoints and, if available,
writes a sanitized endpoint inventory so additional Yunai datasets can be mapped
without hard-coding undocumented paths.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "astock_gateway"
LATEST = GATEWAY / "latest.json"
SNAPS = ROOT / "astock_snapshots" / "index.json"
BASE = "https://quant.yunai.com.cn"
MARKET_STATUS_PATH = "/quant-market/api/v1/quantitative/quotes/market-status"
OPENAPI_CANDIDATES = [
    "/v3/api-docs/swagger-config",
    "/v3/api-docs",
    "/swagger-resources",
    "/v2/api-docs",
    "/quant-market/v3/api-docs/swagger-config",
    "/quant-market/v3/api-docs",
    "/quant-market/swagger-resources",
    "/quant-market/v2/api-docs",
]
SENSITIVE_KEYS = {
    "authorization", "token", "access_token", "refresh_token", "jwt", "username",
    "userid", "user_id", "mobile", "phone", "sub", "jti", "iss", "aud"
}


def bearer() -> str | None:
    raw = os.environ.get("YUNAI_TOKEN", "").strip()
    if not raw:
        return None
    return raw if raw.lower().startswith("bearer ") else "Bearer " + raw


def fetch(path: str, query: dict | None = None, timeout: int = 15):
    token = bearer()
    if not token:
        raise RuntimeError("YUNAI_TOKEN missing")
    url = BASE + path
    if query:
        url += "?" + urlencode(query)
    request = Request(url, headers={
        "Accept": "*/*",
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 AStockStrategy-Yunai/1.0",
        "Cache-Control": "no-cache",
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
        content_type = response.headers.get("Content-Type", "")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw
        return response.status, content_type, payload


def sanitize(value, depth=0):
    if depth > 8:
        return None
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                continue
            out[str(key)] = sanitize(item, depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(x, depth + 1) for x in value[:1000]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def endpoint_category(path: str, tags: list[str] | None = None) -> str:
    text = (path + " " + " ".join(tags or [])).lower()
    groups = [
        ("两融", ("margin", "financing", "融券", "融资")),
        ("ETF", ("etf", "fund-share", "nav", "份额", "净值", "申赎")),
        ("资金流", ("money-flow", "fund-flow", "capital-flow", "资金", "flow")),
        ("板块", ("sector", "industry", "concept", "板块", "行业", "概念")),
        ("K线", ("kline", "candlestick", "bar", "history", "historical", "ohlc")),
        ("行情", ("quote", "ticker", "realtime", "snapshot", "market-status")),
        ("财务", ("financial", "fundamental", "income", "balance", "cashflow", "财务")),
        ("回测/因子", ("backtest", "factor", "strategy", "screen", "rank")),
        ("证券基础", ("security", "symbol", "instrument", "calendar", "trading-day")),
    ]
    for name, keys in groups:
        if any(k in text for k in keys):
            return name
    return "其他"


def extract_paths(doc) -> list[dict]:
    if not isinstance(doc, dict):
        return []
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return []
    inventory = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, spec in methods.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue
            spec = spec if isinstance(spec, dict) else {}
            tags = [str(x) for x in (spec.get("tags") or [])]
            params = []
            for p in spec.get("parameters") or []:
                if isinstance(p, dict):
                    params.append({
                        "name": p.get("name"),
                        "in": p.get("in"),
                        "required": bool(p.get("required", False)),
                    })
            inventory.append({
                "method": method.upper(),
                "path": str(path),
                "summary": spec.get("summary") or spec.get("operationId"),
                "tags": tags,
                "category": endpoint_category(str(path), tags),
                "parameters": params,
            })
    inventory.sort(key=lambda x: (x["category"], x["path"], x["method"]))
    return inventory


def discover_openapi() -> dict:
    attempts = []
    for path in OPENAPI_CANDIDATES:
        try:
            status, content_type, payload = fetch(path, timeout=10)
            attempts.append({"path": path, "status": status, "contentType": content_type})
            inventory = extract_paths(payload)
            if inventory:
                return {"state": "ready", "source": path, "endpoints": inventory, "attempts": attempts}
            # Springdoc swagger-config may point to grouped API docs.
            if isinstance(payload, dict):
                urls = payload.get("urls") or []
                candidates = []
                if isinstance(payload.get("url"), str):
                    candidates.append(payload["url"])
                for item in urls if isinstance(urls, list) else []:
                    if isinstance(item, dict) and isinstance(item.get("url"), str):
                        candidates.append(item["url"])
                for target in candidates:
                    if not target.startswith("/"):
                        continue
                    st, ct, doc = fetch(target, timeout=10)
                    attempts.append({"path": target, "status": st, "contentType": ct})
                    inventory = extract_paths(doc)
                    if inventory:
                        return {"state": "ready", "source": target, "endpoints": inventory, "attempts": attempts}
            # Springfox /swagger-resources is a list of locations.
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    target = item.get("location") or item.get("url")
                    if not isinstance(target, str) or not target.startswith("/"):
                        continue
                    st, ct, doc = fetch(target, timeout=10)
                    attempts.append({"path": target, "status": st, "contentType": ct})
                    inventory = extract_paths(doc)
                    if inventory:
                        return {"state": "ready", "source": target, "endpoints": inventory, "attempts": attempts}
        except HTTPError as error:
            attempts.append({"path": path, "status": error.code})
        except (URLError, TimeoutError, RuntimeError, OSError) as error:
            attempts.append({"path": path, "error": error.__class__.__name__})
    return {"state": "unavailable", "endpoints": [], "attempts": attempts}


def market_status() -> dict:
    checked = datetime.now(CN).isoformat(timespec="seconds")
    status, content_type, payload = fetch(
        MARKET_STATUS_PATH,
        {"market": "ALL", "lang": "en_US"},
        timeout=12,
    )
    safe = sanitize(payload)
    digest = hashlib.sha256(json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "connected": 200 <= status < 300,
        "provider": "Yunai Quant API",
        "checkedAt": checked,
        "httpStatus": status,
        "contentType": content_type,
        "endpoint": MARKET_STATUS_PATH,
        "responseDigest": digest,
        "data": safe,
    }


def sync_snapshot(day: str | None, yunai: dict):
    if not day or not SNAPS.exists():
        return
    try:
        arr = json.loads(SNAPS.read_text(encoding="utf-8"))
        changed = False
        for item in arr:
            if item.get("date") != day:
                continue
            item["yunai"] = yunai
            market = item.get("marketSnapshot")
            if isinstance(market, dict) and yunai.get("marketStatus", {}).get("connected"):
                market["marketStatusProvider"] = "Yunai Quant API"
            changed = True
            break
        if changed:
            SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def main():
    if not LATEST.exists():
        raise SystemExit("astock_gateway/latest.json missing")
    payload = json.loads(LATEST.read_text(encoding="utf-8"))
    token = bearer()
    if not token:
        payload["yunai"] = {
            "configured": False,
            "connected": False,
            "state": "等待 GitHub Secret: YUNAI_TOKEN",
        }
        LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"yunai": "not-configured"}, ensure_ascii=False))
        return

    result = {"configured": True, "connected": False}
    try:
        status = market_status()
        result["marketStatus"] = status
        result["connected"] = bool(status.get("connected"))
    except Exception as error:
        result["marketStatus"] = {"connected": False, "error": error.__class__.__name__}

    discovery = discover_openapi()
    result["openapiState"] = discovery.get("state")
    result["endpointCount"] = len(discovery.get("endpoints") or [])
    result["categories"] = sorted({x.get("category") for x in discovery.get("endpoints") or [] if x.get("category")})
    GATEWAY.mkdir(parents=True, exist_ok=True)
    (GATEWAY / "yunai_openapi.json").write_text(
        json.dumps(discovery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    payload["yunai"] = result
    sources = list(payload.get("dataSources") or [])
    if result.get("connected") and "Yunai Quant API" not in sources:
        sources.insert(0, "Yunai Quant API")
    payload["dataSources"] = sources
    market = payload.get("marketSnapshot")
    if isinstance(market, dict) and result.get("connected"):
        market["marketStatusProvider"] = "Yunai Quant API"
        market["dataSource"] = "Yunai Quant API（市场状态） + 腾讯行情 + 东方财富"

    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sync_snapshot((payload.get("marketSnapshot") or {}).get("sourceDate"), result)
    print(json.dumps({
        "yunai": "connected" if result.get("connected") else "failed",
        "endpointCount": result.get("endpointCount"),
        "categories": result.get("categories"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
