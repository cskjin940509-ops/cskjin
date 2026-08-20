#!/usr/bin/env python3
from __future__ import annotations

import json, math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import update_trade_plan as base
import run_trade_plan_resilient as resilient  # import patches base.em_kline with Tencent fallback

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'astock_trade'/'latest.json'
BUYABLE={'BREAKOUT_RETEST','TREND_PULLBACK','BREAKOUT_READY'}
FS_SHSZ='m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
FIELDS='f2,f3,f6,f8,f12,f14,f15,f16,f17,f18,f20,f21,f62,f184'
UT='bd1d9ddb04089700cf9c27f6f7426281'

def market_page(page,pz=100):
    q={'pn':page,'pz':pz,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f6','fs':FS_SHSZ,'fields':FIELDS,'ut':UT}
    last=None
    for host in ('push2.eastmoney.com','push2delay.eastmoney.com'):
        try:
            data=base.get_json('https://'+host+'/api/qt/clist/get?'+urlencode(q)).get('data') or {}
            return int(data.get('total') or 0), list(data.get('diff') or [])
        except Exception as e:last=e
    if last:raise last
    return 0,[]

def all_a_rows():
    total,first=market_page(1)
    pz=100
    pages=max(1,min(70,math.ceil(total/pz) if total else 1))
    collected=list(first)
    if pages>1:
        with ThreadPoolExecutor(max_workers=10) as ex:
            fut={ex.submit(market_page,p,pz):p for p in range(2,pages+1)}
            for f in as_completed(fut):
                try:
                    _,rows=f.result();collected.extend(rows)
                except Exception:pass
    unique={}
    for x in collected:
        c=str(x.get('f12') or '')
        if c:unique[c]=x
    return list(unique.values()),total,pages

def n(v):return base.num(v)

def prefilter(rows, cap=220):
    clean=[]
    for x in rows:
        code=str(x.get('f12') or ''); name=str(x.get('f14') or '')
        price,chg,amt,turn,flow=n(x.get('f2')),n(x.get('f3')),n(x.get('f6')),n(x.get('f8')),n(x.get('f184'))
        if not code or not name or 'ST' in name.upper() or price is None or amt is None:continue
        if price<1.5 or amt<1.2e8:continue
        if chg is not None and (chg < -4.5 or chg > 6.8):continue
        liq=math.log10(max(amt,1.0))*8
        turn_score=min(max(turn or 0,0),20)*1.2
        flow_score=max(-10,min(18,(flow or 0)*0.7))
        heat=liq+turn_score+flow_score-(max(0,(chg or 0)-4.0)*3.0)
        clean.append((heat,{'code':code,'name':name,'sector':'沪深市场形态扫描','sectorScore':50.0,
                            'price':price,'changePct':chg,'amount':amt,'turnover':turn,
                            'dayHigh':n(x.get('f15')),'dayLow':n(x.get('f16')),'open':n(x.get('f17')),
                            'prevClose':n(x.get('f18')),'mainNetFlow':n(x.get('f62')),'mainFlowPct':flow,'pools':[]}))
    clean.sort(key=lambda z:z[0],reverse=True)
    return [x[1] for x in clean[:cap]]

def setup_rank(p):
    h=((p.get('setup') or {}).get('historical') or {})
    samples=int(h.get('samples') or 0); win=float(h.get('win5D') or 0.5); avg=float(h.get('avg5D') or 0)
    return float((p.get('setup') or {}).get('score') or 0)+min(samples,12)*0.5+(win-0.5)*18+avg*80

def has_historical_edge(p):
    h=((p.get('setup') or {}).get('historical') or {})
    samples=int(h.get('samples') or 0); win=float(h.get('win5D') or 0); avg=float(h.get('avg5D') or 0)
    mfe=float(h.get('avgMFE5D') or 0); mae=abs(float(h.get('avgMAE5D') or 0))
    return samples>=3 and win>=0.55 and avg>0 and (mae==0 or mfe>=mae*0.8)

def main():
    if not OUT.exists():raise RuntimeError('trade plan latest missing')
    payload=json.loads(OUT.read_text(encoding='utf-8'))
    official=payload.get('officialPlans') or []
    live_buy=any(x.get('action')=='买入候选' for x in official)
    if live_buy:
        payload['setupCandidates']=[]
        payload.setdefault('summary',{})['expandedSetupCandidates']=0
        payload['marketSetupScan']={'state':'skipped','reason':'official-has-live-buy'}
        OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return

    today=payload.get('date') or datetime.now(base.CN).strftime('%Y-%m-%d')
    rows,reported_total,pages=all_a_rows(); pre=prefilter(rows)
    histories={}
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut={ex.submit(base.em_kline,x['code'],today,150):x['code'] for x in pre}
        for f in as_completed(fut):
            c=fut[f]
            try:histories[c]=f.result()
            except Exception:histories[c]=[]
    plans=[]
    for m in pre:
        hist=histories.get(m['code']) or []
        if len(hist)<55:continue
        p=base.plan_for(m,None,hist,today,False,False)
        if not p:continue
        setup=p.get('setup') or {}
        if setup.get('type') not in BUYABLE or float(setup.get('score') or 0)<68:continue
        p['source']='沪深市场历史形态精筛'
        if payload.get('phase')=='PREOPEN':p['action']='盘前形态候选'
        plans.append(p)
    plans.sort(key=setup_rank,reverse=True)
    edged=[p for p in plans if has_historical_edge(p)]
    chosen=edged[:8]
    payload['setupCandidates']=chosen
    sm=payload.setdefault('summary',{});sm['expandedSetupCandidates']=len(chosen);sm['marketPrefilterCount']=len(pre);sm['marketScannedCount']=len(histories)
    coverage=(len(rows)/reported_total if reported_total else None)
    payload['marketSetupScan']={'state':'ready' if not reported_total or len(rows)>=reported_total*0.95 else 'partial',
        'scope':'沪深A股；北交所未使用未验证的列表参数，单独留待补充','reportedTotal':reported_total,'uniqueRows':len(rows),'pagesRequested':pages,
        'coveragePct':round(coverage*100,2) if coverage is not None else None,'prefiltered':len(pre),'historyLoaded':sum(bool(v) for v in histories.values()),
        'setupMatches':len(plans),'historicalEdgeMatches':len(edged),'selected':len(chosen),
        'historicalGate':'样本>=3、5D胜率>=55%、平均5D>0、平均MFE不显著弱于MAE',
        'method':'沪深完整分页截面→流动性/不过热预筛→历史K线形态精筛→正历史优势门禁→历史5D/MFE/MAE排序'}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload['marketSetupScan'],ensure_ascii=False))

if __name__=='__main__':main()
