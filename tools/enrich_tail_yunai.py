#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TAIL_ROOT=ROOT/'astock_tail'
LATEST=TAIL_ROOT/'latest.json'
HIST=TAIL_ROOT/'history'
YUNAI=ROOT/'astock_gateway'/'yunai_live.json'


def write_snapshot_if_safe(o: dict, text: str):
    rel=o.get('snapshotPath')
    if not rel:
        return
    try:
        p=(ROOT/rel).resolve()
        root=TAIL_ROOT.resolve()
        if not p.is_relative_to(root):
            return
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(text,encoding='utf-8')
    except Exception:
        return


def main():
    if os.getenv('DRY_RUN','0')=='1' or not LATEST.exists():
        print(json.dumps({'yunaiTail':'skip-no-tail'},ensure_ascii=False)); return
    o=json.loads(LATEST.read_text(encoding='utf-8'))
    codes=list((o.get('stocks') or {}).keys())
    if not codes:
        o['yunaiIntegration']={'state':'no-candidates'}
    elif not YUNAI.exists():
        o['yunaiIntegration']={'state':'gateway-unavailable'}
    else:
        y=json.loads(YUNAI.read_text(encoding='utf-8'))
        ov=y.get('stocks') or {}; qc=vc=cc=0
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
            if x.get('unsupportedMarket'):
                row['yunaiQuote']={'supported':False,'reason':x.get('unsupportedMarket')}
            (o.get('stocks') or {})[code]=row
        o['yunaiIntegration']={'state':'connected' if y.get('connected') else 'gateway-degraded','gatewayCheckedAt':y.get('checkedAt'),'quoteChecked':qc,'quoteVerifiedWithin1Pct':vc,'capitalAvailable':cc,'priceRole':'第二实时行情源交叉核对','capitalRole':'独立资金确认源；当前不改变TB3池排序'}
        if 'Yunai Quant API' not in str(o.get('dataSource') or ''):
            o['dataSource']=str(o.get('dataSource') or '')+' + Yunai Quant API'
    text=json.dumps(o,ensure_ascii=False,indent=2)+'\n'
    LATEST.write_text(text,encoding='utf-8')
    write_snapshot_if_safe(o,text)
    day=o.get('date')
    if day and o.get('status')=='TailFinal':
        hp=HIST/f'{day}.json'
        hp.parent.mkdir(parents=True,exist_ok=True)
        hp.write_text(text,encoding='utf-8')
    print(json.dumps({'yunaiTail':o.get('yunaiIntegration'),'status':o.get('status'),'slot':o.get('scheduledSlot')},ensure_ascii=False))

if __name__=='__main__': main()
