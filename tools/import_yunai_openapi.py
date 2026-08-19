#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_gateway"
BASE = "https://quant.yunai.com.cn"
DOC_PATH = "/quant-market/v3/api-docs"


def bearer() -> str | None:
    raw = os.environ.get("YUNAI_TOKEN", "").strip()
    if not raw:
        return None
    return raw if raw.lower().startswith("bearer ") else "Bearer " + raw


def fetch_doc(use_auth: bool):
    headers = {
        "Accept": "application/json,*/*",
        "User-Agent": "Mozilla/5.0 AStockStrategy-Yunai-Importer/1.0",
        "Referer": BASE + "/doc.html",
        "Cache-Control": "no-cache",
    }
    if use_auth:
        token = bearer()
        if not token:
            raise RuntimeError("YUNAI_TOKEN missing")
        headers["Authorization"] = token
    req = Request(BASE + DOC_PATH, headers=headers)
    with urlopen(req, timeout=20) as r:
        raw = r.read().decode("utf-8", "replace")
        return r.status, r.headers.get("Content-Type", ""), json.loads(raw)


def schema_summary(schema):
    if not isinstance(schema, dict):
        return schema
    keep = {}
    for k in ("$ref", "type", "format", "description", "required", "enum", "default", "example", "nullable"):
        if k in schema:
            keep[k] = schema[k]
    if "items" in schema:
        keep["items"] = schema_summary(schema["items"])
    if "properties" in schema and isinstance(schema["properties"], dict):
        keep["properties"] = {k: schema_summary(v) for k, v in schema["properties"].items()}
    for k in ("allOf", "oneOf", "anyOf"):
        if isinstance(schema.get(k), list):
            keep[k] = [schema_summary(x) for x in schema[k]]
    return keep


def content_schema(obj):
    if not isinstance(obj, dict):
        return None
    content = obj.get("content") or {}
    out = {}
    if isinstance(content, dict):
        for ctype, detail in content.items():
            if not isinstance(detail, dict):
                continue
            schema = detail.get("schema")
            if schema is not None:
                out[ctype] = schema_summary(schema)
    return out or None


def classify(text: str) -> list[str]:
    t = text.lower()
    groups = {
        "两融": ("margin", "financing", "securities lending", "融券", "融资", "两融"),
        "ETF": ("etf", "fund share", "fund-share", "nav", "份额", "净值", "申购", "赎回"),
        "资金流": ("money flow", "money-flow", "fund flow", "fund-flow", "capital flow", "flow", "资金流"),
        "板块": ("sector", "industry", "concept", "板块", "行业", "概念"),
        "行情": ("quote", "snapshot", "market", "ticker", "realtime", "行情"),
        "K线": ("kline", "candlestick", "bar", "ohlc", "history", "historical", "k线"),
        "证券基础": ("security", "symbol", "instrument", "calendar", "trading", "证券", "代码"),
        "财务": ("financial", "income", "balance", "cash flow", "fundamental", "财务"),
        "因子/策略": ("factor", "strategy", "screen", "rank", "backtest", "因子", "策略"),
    }
    return [name for name, keys in groups.items() if any(k in t for k in keys)] or ["其他"]


def build_inventory(doc: dict):
    endpoints = []
    paths = doc.get("paths") or {}
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        path_params = methods.get("parameters") if isinstance(methods.get("parameters"), list) else []
        for method, spec in methods.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch"} or not isinstance(spec, dict):
                continue
            params = []
            for p in path_params + (spec.get("parameters") or []):
                if not isinstance(p, dict):
                    continue
                params.append({
                    "name": p.get("name"),
                    "in": p.get("in"),
                    "required": bool(p.get("required", False)),
                    "description": p.get("description"),
                    "schema": schema_summary(p.get("schema") or {}),
                })
            req_body = spec.get("requestBody") or {}
            responses = []
            for code, rsp in (spec.get("responses") or {}).items():
                if not isinstance(rsp, dict):
                    continue
                responses.append({
                    "status": str(code),
                    "description": rsp.get("description"),
                    "content": content_schema(rsp),
                })
            tags = [str(x) for x in (spec.get("tags") or [])]
            summary = spec.get("summary") or spec.get("operationId") or ""
            description = spec.get("description") or ""
            text = " ".join([path, summary, description, *tags])
            endpoints.append({
                "method": method.upper(),
                "path": path,
                "operationId": spec.get("operationId"),
                "summary": summary,
                "description": description,
                "tags": tags,
                "categories": classify(text),
                "parameters": params,
                "requestBody": {
                    "required": bool(req_body.get("required", False)),
                    "content": content_schema(req_body),
                } if req_body else None,
                "responses": responses,
            })
    endpoints.sort(key=lambda x: (x["path"], x["method"]))
    return endpoints


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    attempts = []
    doc = None
    for use_auth in (False, True):
        try:
            status, ctype, payload = fetch_doc(use_auth)
            attempts.append({"auth": use_auth, "status": status, "contentType": ctype})
            if isinstance(payload, dict) and isinstance(payload.get("paths"), dict):
                doc = payload
                break
        except HTTPError as e:
            attempts.append({"auth": use_auth, "status": e.code})
        except (URLError, TimeoutError, RuntimeError, OSError, json.JSONDecodeError) as e:
            attempts.append({"auth": use_auth, "error": e.__class__.__name__})
    if doc is None:
        report = {"state": "unavailable", "source": BASE + DOC_PATH, "attempts": attempts}
        (OUT / "yunai_openapi.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        raise SystemExit(2)

    endpoints = build_inventory(doc)
    schemas = {}
    for name, schema in ((doc.get("components") or {}).get("schemas") or {}).items():
        if isinstance(schema, dict):
            schemas[name] = schema_summary(schema)
    category_counts = {}
    for ep in endpoints:
        for cat in ep["categories"]:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    report = {
        "state": "ready",
        "importedAt": datetime.now(CN).isoformat(timespec="seconds"),
        "source": BASE + DOC_PATH,
        "openapi": doc.get("openapi") or doc.get("swagger"),
        "info": doc.get("info"),
        "servers": doc.get("servers"),
        "endpointCount": len(endpoints),
        "methodCounts": {
            "GET": sum(1 for x in endpoints if x["method"] == "GET"),
            "POST": sum(1 for x in endpoints if x["method"] == "POST"),
            "PUT": sum(1 for x in endpoints if x["method"] == "PUT"),
            "DELETE": sum(1 for x in endpoints if x["method"] == "DELETE"),
            "PATCH": sum(1 for x in endpoints if x["method"] == "PATCH"),
        },
        "categoryCounts": category_counts,
        "attempts": attempts,
        "endpoints": endpoints,
        "schemas": schemas,
    }
    (OUT / "yunai_openapi.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("state", "source", "endpointCount", "methodCounts", "categoryCounts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
