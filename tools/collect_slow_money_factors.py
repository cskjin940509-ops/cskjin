#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

import akshare as ak
import pandas as pd

from slow_money_factors import themes_for_text

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_factors"
HIST = OUT / "history"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def cutoff_day():
    now = datetime.now(CN)
    return now.date() - timedelta(days=1) if now.hour < 16 else now.date()


def ds(d: date): return d.strftime("%Y%m%d")
def iso(d: date): return d.strftime("%Y-%m-%d")


def code6(v):
    s = str(v).strip()
    if s.endswith('.0') and s[:-2].isdigit(): s = s[:-2]
    return s.zfill(6)


def df_records(df):
    if df is None or df.empty: return []
    return df.where(pd.notna(df), None).to_dict("records")


def fetch_margin_day(d: date):
    stamp = ds(d); merged = {}; errors = {}
    try:
        df = ak.stock_margin_detail_sse(date=stamp)
        for r in df_records(df):
            code = code6(r.get("标的证券代码"))
            if not code or code[0] not in "603": continue
            bal = finite(r.get("融资余额")); buy = finite(r.get("融资买入额")); repay = finite(r.get("融资偿还额"))
            merged[code] = {"code":code,"name":r.get("标的证券简称"),"balance":bal,"buyAmount":buy,"repayAmount":repay,
                "netBuyExact":(buy-repay) if buy is not None and repay is not None else None,"source":"上交所融资融券明细","exchange":"SSE"}
    except Exception as e: errors["SSE"] = e.__class__.__name__
    try:
        df = ak.stock_margin_detail_szse(date=stamp)
        for r in df_records(df):
            code = code6(r.get("证券代码"))
            if not code or code[0] not in "03": continue
            merged[code] = {"code":code,"name":r.get("证券简称"),"balance":finite(r.get("融资余额")),"buyAmount":finite(r.get("融资买入额")),
                "repayAmount":None,"netBuyExact":None,"source":"深交所融资融券明细","exchange":"SZSE"}
    except Exception as e: errors["SZSE"] = e.__class__.__name__
    return iso(d), merged, errors


def collect_margin(cutoff: date):
    snapshots=[]
    for i in range(18):
        d=cutoff-timedelta(days=i)
        if d.weekday()>=5: continue
        day,rows,errors=fetch_margin_day(d)
        if rows:
            snapshots.append((day,rows,errors))
            if len(snapshots)>=6: break
    if not snapshots: return {"dataDate":None,"stockCount":0,"stocks":{},"errors":["no-margin-data"]}
    snapshots.sort(key=lambda x:x[0],reverse=True)
    latest_day,latest,latest_errors=snapshots[0]; prev=snapshots[1][1] if len(snapshots)>1 else {}; prev5=snapshots[5][1] if len(snapshots)>5 else {}
    out={}
    for code,cur in latest.items():
        bal=finite(cur.get("balance")); p1=finite((prev.get(code) or {}).get("balance")); p5=finite((prev5.get(code) or {}).get("balance"))
        c1=bal-p1 if bal is not None and p1 is not None else None; c5=bal-p5 if bal is not None and p5 is not None else None; buy=finite(cur.get("buyAmount"))
        out[code]={**cur,"balanceChange1d":c1,"balanceChangePct1d":c1/p1 if c1 is not None and p1 not in (None,0) else None,
            "balanceChange5d":c5,"balanceChangePct5d":c5/p5 if c5 is not None and p5 not in (None,0) else None,
            "buyToBalancePct":buy/bal if buy is not None and bal not in (None,0) else None,"netBalanceChange1d":c1,
            "netSignalSemantics":"上交所另提供买入-偿还精确值；深交所以融资余额日变动作为净变化，不反推偿还额"}
    return {"dataDate":latest_day,"stockCount":len(out),"tradingDates":[x[0] for x in snapshots],"stocks":out,
        "source":["上交所融资融券明细","深交所融资融券明细"],"latency":"T+1日频；当日盘中使用上一已发布交易日","errors":latest_errors}


def fetch_sse_etf_day(d: date):
    try:
        df=ak.fund_etf_scale_sse(date=ds(d)); rows={}
        for r in df_records(df):
            code=code6(r.get("基金代码")); shares=finite(r.get("基金份额"))
            if not code or shares is None: continue
            rows[code]={"code":code,"name":r.get("基金简称"),"shares":shares,"exchange":"SSE"}
        return iso(d),rows,None
    except Exception as e: return iso(d),{},e.__class__.__name__


def collect_sse_etf(cutoff: date):
    dates=[cutoff-timedelta(days=i) for i in range(38) if (cutoff-timedelta(days=i)).weekday()<5]; got=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        fs={ex.submit(fetch_sse_etf_day,d):d for d in dates}
        for f in as_completed(fs):
            day,rows,err=f.result()
            if rows: got.append((day,rows,err))
    got.sort(key=lambda x:x[0],reverse=True); return got[:21]


def collect_szse_etf(cutoff: date):
    start=cutoff-timedelta(days=45)
    try: df=ak.fund_scale_daily_szse(start_date=ds(start),end_date=ds(cutoff),symbol="ETF")
    except Exception as e: return [],e.__class__.__name__
    by_day={}
    for r in df_records(df):
        raw=r.get("日期"); day=raw.strftime("%Y-%m-%d") if hasattr(raw,"strftime") else str(raw)[:10]
        code=code6(r.get("基金代码")); shares=finite(r.get("基金份额"))
        if not code or shares is None: continue
        by_day.setdefault(day,{})[code]={"code":code,"name":r.get("基金简称"),"shares":shares,"exchange":"SZSE"}
    got=[(day,rows,None) for day,rows in by_day.items() if rows]; got.sort(key=lambda x:x[0],reverse=True); return got[:21],None


def etf_spot_prices():
    try:
        df=ak.fund_etf_spot_em(); out={}
        for r in df_records(df):
            code=code6(r.get("代码")); px=finite(r.get("最新价"))
            if code and px is not None: out[code]=px
        return out,None
    except Exception as e: return {},e.__class__.__name__


def combine_etf_snapshots(sse,szse):
    by_day={}
    for day,rows,_ in sse+szse: by_day.setdefault(day,{}).update(rows)
    return [(day,by_day[day]) for day in sorted(by_day.keys(),reverse=True)][:21]


def collect_etf(cutoff: date):
    sse=collect_sse_etf(cutoff); szse,szerr=collect_szse_etf(cutoff); snaps=combine_etf_snapshots(sse,szse); prices,price_err=etf_spot_prices()
    if not snaps: return {"dataDate":None,"etfCount":0,"etfs":{},"themes":{},"errors":["no-etf-data"]}
    latest_day,latest=snaps[0]; prev=snaps[1][1] if len(snaps)>1 else {}; prev5=snaps[5][1] if len(snaps)>5 else {}; prev20=snaps[20][1] if len(snaps)>20 else {}
    etfs={}
    for code,cur in latest.items():
        sh=finite(cur.get("shares")); p1=finite((prev.get(code) or {}).get("shares")); p5=finite((prev5.get(code) or {}).get("shares")); p20=finite((prev20.get(code) or {}).get("shares"))
        d1=sh-p1 if sh is not None and p1 is not None else None; d5=sh-p5 if sh is not None and p5 is not None else None; d20=sh-p20 if sh is not None and p20 is not None else None
        name=cur.get("name") or ""; themes=themes_for_text(name); px=prices.get(code)
        etfs[code]={**cur,"themes":themes,"shareChange1d":d1,"shareChangePct1d":d1/p1 if d1 is not None and p1 not in (None,0) else None,
            "shareChange5d":d5,"shareChangePct5d":d5/p5 if d5 is not None and p5 not in (None,0) else None,
            "shareChange20d":d20,"shareChangePct20d":d20/p20 if d20 is not None and p20 not in (None,0) else None,
            "latestPriceForEstimate":px,"netCreationAmountEstimate1d":d1*px if d1 is not None and px is not None else None,
            "amountEstimateNote":"份额变化×东方财富ETF最新价，仅作一级净申赎金额近似；评分主要使用份额变化率"}
    themes={}
    for code,row in etfs.items():
        for theme in row.get("themes") or []:
            t=themes.setdefault(theme,{"members":[],"currentShares":0.0,"prevShares1d":0.0,"prevShares5d":0.0,"prevShares20d":0.0,"positive1d":0,"mature1d":0,"netCreationAmountEstimate1d":0.0})
            t["members"].append(code); cur=finite(row.get("shares")); d1=finite(row.get("shareChange1d")); d5=finite(row.get("shareChange5d")); d20=finite(row.get("shareChange20d"))
            if cur is not None: t["currentShares"]+=cur
            if cur is not None and d1 is not None:
                t["prevShares1d"]+=cur-d1; t["mature1d"]+=1
                if d1>0: t["positive1d"]+=1
            if cur is not None and d5 is not None: t["prevShares5d"]+=cur-d5
            if cur is not None and d20 is not None: t["prevShares20d"]+=cur-d20
            amt=finite(row.get("netCreationAmountEstimate1d"));
            if amt is not None: t["netCreationAmountEstimate1d"]+=amt
    for theme,t in themes.items():
        cur=t["currentShares"]; p1=t["prevShares1d"]; p5=t["prevShares5d"]; p20=t["prevShares20d"]
        t["shareChangePct1d"]=(cur-p1)/p1 if p1>0 and t["mature1d"]>0 else None; t["shareChangePct5d"]=(cur-p5)/p5 if p5>0 else None; t["shareChangePct20d"]=(cur-p20)/p20 if p20>0 else None
        t["positiveRatio1d"]=t["positive1d"]/t["mature1d"] if t["mature1d"] else None; t["etfCount"]=len(t["members"]); t["members"]=t["members"][:30]
    errors={}; sse_errors=sorted({err for _,_,err in sse if err})
    if sse_errors: errors["SSE"]=sse_errors
    if szerr: errors["SZSE"]=szerr
    if price_err: errors["price"]=price_err
    return {"dataDate":latest_day,"etfCount":len(etfs),"tradingDates":[x[0] for x in snaps],"etfs":etfs,"themes":themes,
        "source":["上交所ETF基金份额","深交所基金规模日频","东方财富ETF行情仅用于金额估算"],"latency":"T+1日频；一级资金以交易所基金份额变化推导","errors":errors}


def main():
    cutoff=cutoff_day(); margin=collect_margin(cutoff); etf=collect_etf(cutoff); dates=[x for x in (margin.get("dataDate"),etf.get("dataDate")) if x]; data_date=min(dates) if dates else None
    payload={"schemaVersion":1,"factorVersion":"v1.0-exchange-slow-money","dataDate":data_date,"collectedAt":datetime.now(CN).isoformat(timespec="seconds"),
        "usableFor":"下一交易日及之后；禁止用于同一数据日的盘中决策","margin":margin,"etf":etf,
        "provenance":{"margin":"AKShare封装的上交所/深交所融资融券明细","etf":"AKShare封装的上交所ETF份额 + 深交所ETF基金规模日频",
            "principle":"只使用交易所已发布数据；缺失保持空白；不把ETF二级市场主力资金冒充一级申赎"}}
    OUT.mkdir(parents=True,exist_ok=True); HIST.mkdir(parents=True,exist_ok=True)
    (OUT/"latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if data_date: (HIST/f"{data_date}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":"slow-money-updated" if data_date else "slow-money-no-data","dataDate":data_date,"marginStocks":margin.get("stockCount"),"etfs":etf.get("etfCount"),"themes":len(etf.get("themes") or {})},ensure_ascii=False))

if __name__ == "__main__": main()
