#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from slow_money_factors import apply_to_stock_candidates, availability_strings

ROOT = Path(__file__).resolve().parents[1]
RADAR = ROOT / "astock_radar" / "latest.json"


def main():
    if not RADAR.exists():
        print(json.dumps({"state":"no-radar"}, ensure_ascii=False)); return
    radar=json.loads(RADAR.read_text(encoding="utf-8")); stock_obj=radar.get("stocks") or {}; rows=[]
    for code,x in stock_obj.items():
        if not isinstance(x,dict): continue
        row=dict(x); row["code"]=code; row.setdefault("score",row.get("earlyEntryScore") if row.get("earlyEntryScore") is not None else row.get("baseScore")); rows.append(row)
    rows,pools,factors=apply_to_stock_candidates(rows,radar.get("pools") or {},radar.get("date"))
    for row in rows:
        code=str(row.get("code") or "")
        if code not in stock_obj: continue
        for key in ("marginScore","marginFactorScore","marginData","etfScore","etfFlowScore","etfData","slowCompositeScore","slowFactorDataDate"):
            if key in row: stock_obj[code][key]=row[key]
    radar["stocks"]=stock_obj; radar["pools"]=pools; radar.setdefault("factorAvailability",{}).update(availability_strings(factors))
    radar["slowMoneyFactor"]={"state":"ready" if factors else "unavailable","dataDate":factors.get("dataDate") if factors else None,"latency":"T+1日频",
        "B1Members":len(pools.get("B1") or []),"B2Members":len(pools.get("B2") or []),"note":"两融与ETF份额是上一已发布交易日的慢资金结构因子，不冒充盘中实时。"}
    RADAR.write_text(json.dumps(radar,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":"radar-slow-money-enriched","dataDate":factors.get("dataDate") if factors else None,"B1":pools.get("B1") or [],"B2":pools.get("B2") or []},ensure_ascii=False))

if __name__ == "__main__": main()
