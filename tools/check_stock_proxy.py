#!/usr/bin/env python3
"""Sanitized production connectivity check; never prints credentials."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_slow_money_factors_v2 as collector

cn = timezone(timedelta(hours=8))
day = (datetime.now(cn).date() - timedelta(days=1)).strftime("%Y%m%d")
try:
    rows = collector._proxy_rows("margin", {"trade_date": day, "limit": 10})
    print(json.dumps({"proxyConfigured": True, "reachable": True,
                      "api": "margin", "rows": len(rows)}))
except Exception as error:
    print(json.dumps({"proxyConfigured": bool(collector.os.getenv("STOCK_API_TOKEN")),
                      "reachable": False, "errorType": error.__class__.__name__,
                      "error": str(error)[:160]}))
