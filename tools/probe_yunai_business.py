#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://quant.yunai.com.cn"
DOC = "/quant-market/v3/api-docs"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_gateway" / "yunai_business_probe.json"
CN = timezone(timedelta(hours=8))

TARGETS = [
    ("GET", "/api/v1/quantitative/quotes/market-status"),
    ("POST", "/api/v1/quantitative/quotes/real-time-quotes"),
    ("POST", "/api/v1/quantitative/quotes/capital-distribution"),
    ("POST", "/api/v1/quantitative/quotes/bars-range"),
]


def token() -> str:
    raw = os.environ.get("YUNAI_TOKEN", "").strip()
    if not raw:
        raise RuntimeError("YUNAI_TOKEN missing")
    return raw if raw.lower().startswith("bearer ") else "Bearer " + raw


def http(method: str, path: str, *, query=None, body=None, auth=True, timeout=20):
    url = BASE + path
    if query:
        url += "?" + urlencode(query, doseq=True)
    headers = {
        "Accept": "application/json,*/*",
        "User-Agent": "Mozilla/5.0 AStockStrategy-Yunai-Probe/1.0",
        "Referer": BASE + "/doc.html",
        "Cache-Control": "no-cache",
    }
    data = None
    if auth:
        headers["Authorization"] = token()
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, headers=headers, data=data, method=method)
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = raw
            return r.status, r.headers.get("Content-Type", ""), payload
    except HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", payload


def resolve_ref(doc: dict, ref: str):
    cur = doc
    for part in ref.removeprefix("#/").split("/"):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur if isinstance(cur, dict) else {}


def sample_value(name: str, schema: dict, doc: dict):
    lname = name.lower()
    if lname in {"symbols", "symbolList".lower()}:
        return ["000001"]
    if lname == "symbol":
        return "000001"
    if lname == "market":
        return "CN"
    if lname == "lang":
        return "zh_CN"
    if lname in {"bartype", "period", "interval"}:
        return "day"
    if lname in {"rightoption", "adjust", "adjusttype"}:
        return "nr"
    if lname == "tradesession":
        return "Regular"
    today = datetime.now(CN).date()
    if lname in {"startdate", "begindate"}:
        return (today - timedelta(days=3)).isoformat()
    if lname == "enddate":
        return today.isoformat()
    if lname == "limit":
        return 20
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        preferred = ["CN", "zh_CN", "day", "DAY", "nr", "Regular"]
        for p in preferred:
            if p in enum:
                return p
        return enum[0]
    if "$ref" in schema:
        return sample_object(resolve_ref(doc, schema["$ref"]), doc)
    typ = schema.get("type")
    if typ == "array":
        return [sample_value(name[:-1] if name.endswith("s") else name, schema.get("items") or {}, doc)]
    if typ == "object" or "properties" in schema:
        return sample_object(schema, doc)
    if typ in {"integer", "number"}:
        return 1
    if typ == "boolean":
        return False
    return "CN"


def sample_object(schema: dict, doc: dict):
    if "$ref" in schema:
        schema = resolve_ref(doc, schema["$ref"])
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    # Include a few common optional routing fields because many market APIs need them.
    include_optional = {"market", "lang", "barType", "rightOption", "tradeSession", "limit"}
    out = {}
    for name, sub in props.items():
        if name in required or name in include_optional:
            out[name] = sample_value(name, sub if isinstance(sub, dict) else {}, doc)
    return out


def operation(doc: dict, method: str, path: str):
    return (((doc.get("paths") or {}).get(path) or {}).get(method.lower()) or {})


def make_body(doc: dict, method: str, path: str):
    op = operation(doc, method, path)
    body = op.get("requestBody") or {}
    content = body.get("content") or {}
    for detail in content.values():
        if not isinstance(detail, dict):
            continue
        schema = detail.get("schema") or {}
        return sample_value("body", schema, doc)
    return None


def summarize(payload):
    if isinstance(payload, dict):
        out = {"type": "object", "keys": list(payload.keys())[:30]}
        for k in ("code", "msg", "message", "success", "tradeSession"):
            if k in payload and isinstance(payload[k], (str, int, float, bool, type(None))):
                out[k] = payload[k]
        data = payload.get("data")
        if isinstance(data, dict):
            out["dataKeys"] = list(data.keys())[:20]
        elif isinstance(data, list):
            out["dataCount"] = len(data)
        # capture one top-level symbol-shaped value without dumping a huge response
        for k, v in payload.items():
            if k in {"code", "msg", "message", "data"}:
                continue
            if isinstance(v, (dict, list)):
                out["sampleKey"] = k
                out["sampleType"] = type(v).__name__
                if isinstance(v, list):
                    out["sampleCount"] = len(v)
                break
        return out
    if isinstance(payload, list):
        return {"type": "array", "count": len(payload), "firstType": type(payload[0]).__name__ if payload else None}
    text = str(payload)
    return {"type": type(payload).__name__, "preview": text[:300]}


def main():
    now = datetime.now(CN).isoformat(timespec="seconds")
    report = {"checkedAt": now, "base": BASE, "authenticated": False, "calls": []}
    try:
        _ = token()
        report["authenticated"] = True
    except Exception as e:
        report["error"] = e.__class__.__name__
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise

    st, _, doc = http("GET", DOC, auth=False)
    if st != 200 or not isinstance(doc, dict):
        raise RuntimeError(f"OpenAPI unavailable: {st}")

    for method, path in TARGETS:
        query = None
        body = None
        if method == "GET" and path.endswith("market-status"):
            query = {"market": "CN", "lang": "zh_CN"}
        elif method == "POST":
            body = make_body(doc, method, path)
        status, ctype, payload = http(method, path, query=query, body=body, auth=True)
        report["calls"].append({
            "method": method,
            "path": path,
            "httpStatus": status,
            "contentType": ctype,
            "request": {"query": query, "body": body},
            "response": summarize(payload),
            "ok": 200 <= status < 300,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"authenticated": report["authenticated"], "calls": [{"path": x["path"], "status": x["httpStatus"], "ok": x["ok"]} for x in report["calls"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
