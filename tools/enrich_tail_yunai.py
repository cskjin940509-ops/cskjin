#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path
import yunai_tail_overlay as yo

ROOT=Path(__file__).resolve().parents[1]
LATEST=ROOT/'astock_tail'/'latest.json'
HIST=ROOT/'astock_tail'/'history'


def main():
    if os.getenv('DRY_RUN','0')=='1' or not LATEST.exists():
        print(json.dumps({'yunaiTail':'skip-no-frozen-tail'},ensure_ascii=False)); return
    o=json.loads(LATEST.read_text(encoding='utf-8'))
    codes=list((o.get('stocks') or {}).keys())
    if not codes:
        o['yunaiIntegration']={'state':'no-candidates'}
    else:
        ov=yo.fetch_stock_overlay(codes)
        qc=vc=cc=0
        for code in codes:
            row=(o.get('stocks') or {}).get(code) or {}; x=ov.get(code) or {}
            q=x.get('quote') or {}; cap=x.get('capital') or {}
            if x.get('quoteOk'):
                qc+=1; yp=q.get('price'); ep=row.get('price'); verified=False
                try: verified=yp is not None and ep not in (None,0) and abs(float(yp)/float(ep)-1)<=0.01
                except Exception: pass
                if verified: vc+=1
                row['yunaiQuote']={'verifiedWithin1Pct':verified,'price':yp,'changePct':q.get('changePct'),'amount':q.get('amount')}
            if x.get('capitalOk'):
                large=cap.get('largeNetInflow'); total=cap.get('totalNetInflow')
                if large is not None or total is not None: cc+=1
                row['yunaiCapital']={'largeNetInflow':large,'totalNetInflow':total,'role':'独立大单资金分布，不等同东方财富主力净流入'}
            (o.get('stocks') or {})[code]=row
        o['yunaiIntegration']={'state':'connected','quoteChecked':qc,'quoteVerifiedWithin1Pct':vc,'capitalAvailable':cc,'priceRole':'第二实时行情源交叉核对','capitalRole':'独立资金确认源；当前不改变TB3池排序'}
        o['dataSource']=str(o.get('dataSource') or '')+' + Yunai Quant API'
    text=json.dumps(o,ensure_ascii=False,indent=2)+'\n'
    LATEST.write_text(text,encoding='utf-8')
    day=o.get('date')
    if day:
        hp=HIST/f'{day}.json'
        if hp.exists(): hp.write_text(text,encoding='utf-8')
    print(json.dumps({'yunaiTail':o.get('yunaiIntegration')},ensure_ascii=False))

if __name__=='__main__': main()
