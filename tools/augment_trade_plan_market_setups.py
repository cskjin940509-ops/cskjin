#!/usr/bin/env python3
from __future__ import annotations

import json, math, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import update_trade_plan as base
import run_trade_plan_resilient as resilient  # patches base.em_kline with Tencent fallback

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'astock_trade'/'latest.json'
BUYABLE={'BREAKOUT_RETEST','TREND_PULLBACK','BREAKOUT_READY'}

def all_a_rows():
    fs='m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
    q={'pn':1,'pz':6000,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f6','fs':fs,
       'fields':'f2,f3,f6,f8,f12,f14,f15,f16,f17,f18,f20,f21,f62,f184',
       'ut':'bd1d9ddb04089700cf9c27f6f7426281'}
    last=None
    for host in ('push2.eastmoney.com','push2delay.eastmoney.com'):
        try:
            rows=((base.get_json('https://'+host+'/api/qt/clist/get?'+urlencode(q)).get('data') or {}).get('diff') or [])
            if rows:return rows
        except Exception as e:last=e
    if last:raise last
    return []

def n(v):return base.num(v)

def prefilter(rows, cap=180):
    clean=[]
    for x in rows:
        code=str(x.get('f12') or ''); name=str(x.get('f14') or '')
        price,chg,amt,turn,flow=n(x.get('f2')),n(x.get('f3')),n(x.get('f6')),n(x.get('f8')),n(x.get('f184'))
        if not code or not name or 'ST' in name.upper() or price is None or amt is None:continue
        if price<1.5 or amt<1.2e8:continue
        if chg is not None and (chg < -4.5 or chg > 6.8):continue
        # Avoid micro-liquidity and obvious one-day chase candidates; historical pattern does the precise second stage.
        liq=math.log10(max(amt,1.0))*8
        turn_score=min(max(turn or 0,0),20)*1.2
        flow_score=max(-10,min(18,(flow or 0)*0.7))
        heat=liq+turn_score+flow_score-(max(0,(chg or 0)-4.0)*3.0)
        clean.append((heat,{'code':code,'name':name,'sector':'全市场形态扫描','sectorScore':50.0,
                            'price':price,'changePct':chg,'amount':amt,'turnover':turn,
                            'dayHigh':n(x.get('f15')),'dayLow':n(x.get('f16')),'open':n(x.get('f17')),
                            'prevClose':n(x.get('f18')),'mainNetFlow':n(x.get('f62')),'mainFlowPct':flow,
                            'pools':[]}))
    clean.sort(key=lambda z:z[0],reverse=True)
    return [x[1] for x in clean[:cap]]

def setup_rank(p):
    h=((p.get('setup') or {}).get('historical') or {})
    samples=int(h.get('samples') or 0); win=float(h.get('win5D') or 0.5); avg=float(h.get('avg5D') or 0)
    return float((p.get('setup') or {}).get('score') or 0)+min(samples,12)*0.5+(win-0.5)*18+avg*80

def main():
    if not OUT.exists():raise RuntimeError('trade plan latest missing')
    payload=json.loads(OUT.read_text(encoding='utf-8'))
    official=payload.get('officialPlans') or []
    # Existing Official is considered immediately buyable only during LIVE; pre-open we still scan alternatives.
    live_buy=any(x.get('action')=='买入候选' for x in official)
    if live_buy:
        payload['setupCandidates']=[]
        payload.setdefault('summary',{})['expandedSetupCandidates']=0
        payload['marketSetupScan']={'state':'skipped','reason':'official-has-live-buy'}
        OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return

    today=payload.get('date') or datetime.now(base.CN).strftime('%Y-%m-%d')
    rows=all_a_rows(); pre=prefilter(rows)
    histories={}
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut={ex.submit(base.em_kline,x['code'],today,150):x['code'] for x in pre}
        for f in as_completed(fut):
            c=fut[f]
            try:histories[c]=f.result()
            except Exception:histories[c]=[]
    # Use market-list quote as point-in-time display; base.plan_for will label PREOPEN correctly if Tencent current-day quote is absent.
    plans=[]
    for m in pre:
        hist=histories.get(m['code']) or []
        if len(hist)<55:continue
        p=base.plan_for(m,None,hist,today,False,False)
        if not p:continue
        setup=p.get('setup') or {}
        if setup.get('type') not in BUYABLE:continue
        if float(setup.get('score') or 0)<68:continue
        p['source']='全A历史形态精筛'
        if payload.get('phase')=='PREOPEN':
            p['action']='盘前形态候选'
        plans.append(p)
    plans.sort(key=setup_rank,reverse=True)
    # Demand some historical support when available, but don't silently drop a newly observed valid technical setup.
    strong=[p for p in plans if int(((p.get('setup') or {}).get('historical') or {}).get('samples') or 0)>=3]
    chosen=(strong if strong else plans)[:12]
    payload['setupCandidates']=chosen
    sm=payload.setdefault('summary',{});sm['expandedSetupCandidates']=len(chosen);sm['marketPrefilterCount']=len(pre);sm['marketScannedCount']=len(histories)
    payload['marketSetupScan']={'state':'ready','universeRows':len(rows),'prefiltered':len(pre),'historyLoaded':sum(bool(v) for v in histories.values()),
                                'setupMatches':len(plans),'selected':len(chosen),'method':'全A流动性/不过热预筛→历史K线形态精筛→历史5D/MFE/MAE排序'}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload['marketSetupScan'],ensure_ascii=False))

if __name__=='__main__':main()
