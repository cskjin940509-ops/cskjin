#!/usr/bin/env python3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bse_market_mapping import eastmoney_secid, tencent_symbol

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_gateway" / "validation" / "bse-920087.json"
CODE = "920087"
LEGACY_CODE = "831087"
DAY = "2026-08-18"


def get(url, referer):
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 AStockStrategy-BSE-Test/1.1","Accept":"*/*","Referer":referer,"Cache-Control":"no-cache"})
    with urlopen(req, timeout=15) as r:
        return r.read()


def tx_day_symbol(sym):
    p = json.loads(get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"+urlencode({"param":f"{sym},day,{DAY},{DAY},10,"}), "https://gu.qq.com/").decode("utf-8","replace"))
    root = (p.get("data") or {}).get(sym) or {}
    rows = root.get("day") or root.get("qfqday") or []
    return {"symbol":sym,"keys":sorted(root.keys()),"row":next((r for r in rows if isinstance(r,list) and r and r[0]==DAY),None)}


def tx_historical_probes():
    out={}
    for sym in ("bj920087","bj831087","sz920087","sh920087"):
        try: out[sym]=tx_day_symbol(sym)
        except Exception as e: out[sym]={"symbol":sym,"error":f"{e.__class__.__name__}: {e}"}
    return out


def em_day():
    secid = eastmoney_secid(CODE)
    q={"secid":secid,"klt":101,"fqt":0,"lmt":5,"end":DAY.replace("-",""),"fields1":"f1,f2,f3,f4,f5,f6","fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61","ut":"fa5fd1943c7b386f172d6893dbfba10b"}
    p=json.loads(get("https://push2his.eastmoney.com/api/qt/stock/kline/get?"+urlencode(q),"https://quote.eastmoney.com/bj/920087.html").decode("utf-8","replace"))
    rows=((p.get("data") or {}).get("klines") or [])
    return {"secid":secid,"row":next((r for r in rows if isinstance(r,str) and r.startswith(DAY+",")),None)}


def tx_live():
    sym=tencent_symbol(CODE)
    raw=get("https://qt.gtimg.cn/q="+sym,"https://gu.qq.com/").decode("gbk","replace")
    return {"symbol":sym,"rawPrefix":raw[:180]}


def main():
    report={"code":CODE,"legacyCode":LEGACY_CODE,"name":"秋乐种业","checkedAt":datetime.now(CN).isoformat(timespec="seconds"),"expected":{"tencentLive":"bj920087","eastmoney":"0.920087"},"checks":{}}
    for name,fn in (("tencentHistoricalProbes",tx_historical_probes),("eastmoneyHistorical",em_day),("tencentLive",tx_live)):
        try: report["checks"][name]=fn()
        except Exception as e: report["checks"][name]={"error":f"{e.__class__.__name__}: {e}"}
    probes=report["checks"].get("tencentHistoricalProbes",{})
    tx_hist=next((x for x in probes.values() if isinstance(x,dict) and x.get("row")),None)
    eh=report["checks"].get("eastmoneyHistorical",{}).get("row")
    live=report["checks"].get("tencentLive",{}).get("rawPrefix","")
    report["liveMappingVerified"] = bool("920087" in live and "秋乐种业" in live)
    report["eastmoneyHistoryVerified"] = bool(eh)
    report["tencentHistoryAvailable"] = bool(tx_hist)
    report["verified"] = bool(report["liveMappingVerified"] and report["eastmoneyHistoryVerified"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if not report["verified"]: raise SystemExit(2)

if __name__ == "__main__": main()
