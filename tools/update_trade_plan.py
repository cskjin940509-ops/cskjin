#!/usr/bin/env python3
from __future__ import annotations

import json, math, statistics, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT/'astock_snapshots'/'index.json'
TAIL = ROOT/'astock_tail'/'latest.json'
OUTDIR = ROOT/'astock_trade'
UA = 'Mozilla/5.0 AStockStrategy-TradePlan/1.0'

def num(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def get_bytes(url, timeout=12, referer='https://quote.eastmoney.com/'):
    req=Request(url,headers={'User-Agent':UA,'Accept':'*/*','Referer':referer,'Cache-Control':'no-cache'})
    with urlopen(req,timeout=timeout) as r:return r.read()

def get_json(url, timeout=12): return json.loads(get_bytes(url,timeout).decode('utf-8','replace'))

def secid(code): return ('1.' if code.startswith(('5','6')) else '0.')+code

def symbol(code):
    if code.startswith(('8','9')): return 'bj'+code
    return ('sh' if code.startswith(('5','6')) else 'sz')+code

def tencent_quotes(codes):
    syms=[symbol(c) for c in codes]
    if not syms:return {}
    text=get_bytes('https://qt.gtimg.cn/q='+','.join(syms),referer='https://gu.qq.com/').decode('gbk','replace')
    import re
    out={}
    for sym,payload in re.findall(r'v_([A-Za-z0-9]+)="([^"]*)"',text):
        f=payload.split('~')
        if len(f)<=37:continue
        code=f[2] if len(f)>2 else sym[-6:]
        stamp=f[30] if len(f)>30 else ''
        out[code]={
            'code':code,'name':f[1] if len(f)>1 else code,
            'price':num(f[3]),'prevClose':num(f[4]),'open':num(f[5]),
            'changePct':num(f[32]),'high':num(f[33]),'low':num(f[34]),
            'amount':(num(f[37])*10000.0) if num(f[37]) is not None else None,
            'quoteTimeRaw':stamp,'quoteDate':stamp[:8] if len(stamp)>=8 else None,
            'source':'腾讯行情'}
    return out

def em_kline(code, end_day, limit=140):
    q={'secid':secid(code),'klt':101,'fqt':1,'lmt':limit,'end':end_day.replace('-',''),
       'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
       'ut':'fa5fd1943c7b386f172d6893dbfba10b'}
    d=(get_json('https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(q)).get('data') or {})
    out=[]
    for raw in d.get('klines') or []:
        f=raw.split(',')
        if len(f)<7:continue
        o,c,h,l,a=num(f[1]),num(f[2]),num(f[3]),num(f[4]),num(f[6])
        if o is None or c is None or h is None or l is None:continue
        out.append({'date':f[0],'open':o,'close':c,'high':h,'low':l,'amount':a})
    return out

def em_members(board_code, sector_name, sector_score):
    q={'pn':1,'pz':100,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f6','fs':'b:'+board_code,
       'fields':'f2,f3,f6,f8,f12,f14,f15,f16,f17,f18,f62,f184','ut':'bd1d9ddb04089700cf9c27f6f7426281'}
    last=None
    for host in ('push2.eastmoney.com','push2delay.eastmoney.com'):
        try:
            rows=((get_json('https://'+host+'/api/qt/clist/get?'+urlencode(q)).get('data') or {}).get('diff') or [])
            if rows:
                out=[]
                for x in rows:
                    code=str(x.get('f12') or ''); name=str(x.get('f14') or '')
                    price,amt=num(x.get('f2')),num(x.get('f6'))
                    if not code or not name or 'ST' in name.upper() or price is None or amt is None or amt<5e7:continue
                    out.append({'code':code,'name':name,'sector':sector_name,'sectorScore':sector_score,
                                'price':price,'changePct':num(x.get('f3')),'amount':amt,'turnover':num(x.get('f8')),
                                'dayHigh':num(x.get('f15')),'dayLow':num(x.get('f16')),'open':num(x.get('f17')),
                                'prevClose':num(x.get('f18')),'mainNetFlow':num(x.get('f62')),'mainFlowPct':num(x.get('f184'))})
                return out
        except Exception as e:last=e
    if last: raise last
    return []

def latest_official():
    arr=json.loads(SNAPS.read_text(encoding='utf-8')) if SNAPS.exists() else []
    xs=[x for x in arr if x.get('status')=='Official']
    return max(xs,key=lambda x:x.get('date','')) if xs else None

def tail_codes(today):
    if not TAIL.exists():return set()
    try:
        x=json.loads(TAIL.read_text(encoding='utf-8'))
        if x.get('date')!=today:return set()
        return set(((x.get('pools') or {}).get('TailCore') or []))
    except Exception:return set()

def mean_last(xs,n): return statistics.fmean(xs[-n:]) if len(xs)>=n else None

def atr14(rows):
    if len(rows)<15:return None
    trs=[]
    for i in range(1,len(rows)):
        r,p=rows[i],rows[i-1]
        trs.append(max(r['high']-r['low'],abs(r['high']-p['close']),abs(r['low']-p['close'])))
    return statistics.fmean(trs[-14:]) if len(trs)>=14 else None

def limit_pct(code):
    if code.startswith(('8','9')): return 30.0
    if code.startswith(('30','68')): return 20.0
    return 10.0

def calc_context(rows, asof, price, day_high, day_low, change_pct):
    prior=[r for r in rows if r['date']<asof]
    if len(prior)<50 or not price:return None
    closes=[r['close'] for r in prior]
    ma5,ma10,ma20,ma50=(mean_last(closes,n) for n in (5,10,20,50))
    a=atr14(prior)
    if None in (ma5,ma10,ma20,ma50,a) or not a:return None
    h20=max(r['high'] for r in prior[-20:]); l10=min(r['low'] for r in prior[-10:])
    ch=change_pct or 0.0; high=day_high or price; low=day_low or price
    trend=ma10>ma20 and ma20>=ma50*0.985
    ext=(price-ma20)/a
    kind='NONE'; label='暂无可买形态'; score=45.0
    if high>=h20*1.002 and h20*0.995<=price<=h20*1.018 and -2.0<=ch<=6.0 and ext<=2.1:
        kind='BREAKOUT_RETEST'; label='突破回踩'; score=84.0
    elif trend and ma10*0.985<=price<=ma10*1.018 and price>=ma20*0.995 and -3.0<=ch<=4.0 and ext<=1.8:
        kind='TREND_PULLBACK'; label='趋势回踩'; score=79.0
    elif trend and h20*0.982<=price<h20*1.003 and -2.0<=ch<=4.0 and ext<=1.8:
        kind='BREAKOUT_READY'; label='临界突破'; score=72.0
    if ext>2.35 or ch>min(7.0,limit_pct('600000')-1):
        kind='OVEREXTENDED'; label='过度延伸/追高风险'; score=min(score,42.0)
    if price<ma20*0.975:
        kind='BROKEN'; label='跌破趋势支撑'; score=min(score,35.0)
    return {'kind':kind,'label':label,'baseScore':score,'ma5':ma5,'ma10':ma10,'ma20':ma20,'ma50':ma50,
            'atr14':a,'high20':h20,'low10':l10,'extensionATR':ext,'trend':trend,'dayHigh':high,'dayLow':low}

def hist_kind(rows,i):
    if i<50:return None
    day=rows[i]; prior=rows[:i]; price=day['close']; prev=prior[-1]['close']
    ch=(price/prev-1)*100 if prev else 0
    c=calc_context(rows[:i+1],day['date'],price,day['high'],day['low'],ch)
    return c['kind'] if c else None

def historical_stats(rows, kind):
    if kind not in {'BREAKOUT_RETEST','TREND_PULLBACK','BREAKOUT_READY'}:return {}
    vals=[]
    end=max(50,len(rows)-130)
    for i in range(end,len(rows)-6):
        if hist_kind(rows,i)!=kind:continue
        entry=rows[i]['close']; future=rows[i+1:i+6]
        if not entry or len(future)<5:continue
        ret=future[-1]['close']/entry-1
        mfe=max(x['high'] for x in future)/entry-1
        mae=min(x['low'] for x in future)/entry-1
        vals.append((ret,mfe,mae))
    if not vals:return {'samples':0}
    return {'samples':len(vals),'win5D':round(sum(x[0]>0 for x in vals)/len(vals),4),
            'avg5D':round(statistics.fmean(x[0] for x in vals),4),
            'avgMFE5D':round(statistics.fmean(x[1] for x in vals),4),
            'avgMAE5D':round(statistics.fmean(x[2] for x in vals),4)}

def plan_for(meta,q,rows,today,is_official,is_tail):
    price=q.get('price') if q else meta.get('price'); ch=q.get('changePct') if q else meta.get('changePct')
    high=q.get('high') if q else meta.get('dayHigh'); low=q.get('low') if q else meta.get('dayLow')
    ctx=calc_context(rows,today,price,high,low,ch)
    if not ctx:return None
    score=ctx['baseScore'] + (4 if is_official else 0) + (5 if is_tail else 0)
    flow=num(meta.get('mainFlowPct'))
    if flow is not None: score += max(-5,min(5,flow/5))
    hist=historical_stats([r for r in rows if r['date']<today],ctx['kind'])
    if hist.get('samples',0)>=3:
        score += max(-4,min(5,(hist.get('win5D',0.5)-0.5)*20))
    score=max(0,min(100,score))
    kind=ctx['kind']; a=ctx['atr14']
    if kind=='BREAKOUT_RETEST': support=ctx['high20']; loz=support*0.997; hiz=support*1.012
    elif kind=='TREND_PULLBACK': support=max(ctx['ma20'],ctx['ma10']*0.99); loz=support; hiz=ctx['ma10']*1.01
    elif kind=='BREAKOUT_READY': support=ctx['high20']; loz=support*0.992; hiz=support*1.005
    else: support=ctx['ma20']; loz=hiz=None
    stop=tp1=tp2=rr1=None
    in_zone=False
    if loz and hiz:
        mid=(loz+hiz)/2
        stop=max(support-0.8*a,mid*0.94)
        risk=max(0.01,mid-stop)
        tp1=mid+1.5*risk; tp2=mid+2.5*risk
        rr1=(tp1-mid)/(mid-stop) if mid>stop else None
        in_zone=loz<=price<=hiz
    near_limit=(ch or 0)>=limit_pct(meta['code'])-0.6
    phase='PREOPEN' if (q or {}).get('quoteDate')!=today.replace('-','') else 'LIVE'
    if phase!='LIVE': action='盘前观察'
    elif near_limit or kind in {'OVEREXTENDED','BROKEN','NONE'}: action='不建议买'
    elif in_zone and score>=80: action='买入候选'
    elif score>=68: action='等待触发'
    else: action='不建议买'
    if is_tail and action=='买入候选': window='14:30-14:50'
    elif kind=='BREAKOUT_RETEST': window='09:35-10:45 / 13:30-14:50'
    elif kind=='TREND_PULLBACK': window='09:40-11:00 / 13:15-14:45'
    else: window='触发价出现后再评估'
    day_range=(high/low-1)*100 if high and low and low>0 else None
    reasons=[ctx['label'],f"形态分 {score:.0f}",f"距MA20 {ctx['extensionATR']:+.2f} ATR"]
    if flow is not None:reasons.append(f"主力资金占比 {flow:+.2f}%")
    if near_limit:reasons.append('接近涨停，按追高风险处理')
    return {'code':meta['code'],'name':meta.get('name') or (q or {}).get('name') or meta['code'],'sector':meta.get('sector'),
            'official':is_official,'tailCore':is_tail,'poolTags':meta.get('pools') or [],'action':action,
            'setup':{'type':kind,'label':ctx['label'],'score':round(score,1),'historical':hist},
            'quote':{'price':price,'changePct':ch,'open':(q or {}).get('open'),'high':high,'low':low,'dayLowToHighPct':round(day_range,2) if day_range is not None else None,'quoteTime':(q or {}).get('quoteTimeRaw')},
            'entryZone':[round(loz,3),round(hiz,3)] if loz and hiz else None,'triggerPrice':round(ctx['high20'],3) if kind in {'BREAKOUT_RETEST','BREAKOUT_READY'} else round(ctx['ma10'],3),
            'stopLoss':round(stop,3) if stop else None,'takeProfit1':round(tp1,3) if tp1 else None,'takeProfit2':round(tp2,3) if tp2 else None,
            'riskReward1':round(rr1,2) if rr1 else None,'preferredWindow':window,
            'sellRule':'买入当日仅预警；次一交易日起：跌破失效位退出；到TP1可减仓，TP2或跌破10日趋势线继续减/退出。',
            'tPlusOne':True,'invalidation':f"收盘/有效价格跌破 {stop:.3f}" if stop else '未形成可执行入场，不设交易止损',
            'reasons':reasons}

def main():
    snap=latest_official()
    if not snap: raise RuntimeError('no Official cohort')
    now=datetime.now(CN); today=now.strftime('%Y-%m-%d')
    official_codes=sorted({c for v in (snap.get('pools') or {}).values() for c in (v or [])})
    official_meta={c:{'code':c,**((snap.get('stocks') or {}).get(c) or {})} for c in official_codes}
    expanded={}
    sectors=sorted((snap.get('selectedSectors') or []),key=lambda x:float(x.get('score') or 0),reverse=True)[:5]
    with ThreadPoolExecutor(max_workers=5) as ex:
        fs={ex.submit(em_members,str(b.get('boardCode') or ''),str(b.get('name') or ''),num(b.get('score')) or 0):b for b in sectors if b.get('boardCode')}
        for f in as_completed(fs):
            try:
                for x in f.result():
                    old=expanded.get(x['code'])
                    if old is None or x['sectorScore']>old['sectorScore']:expanded[x['code']]=x
            except Exception: pass
    candidates=dict(expanded); candidates.update(official_meta)
    codes=sorted(candidates)
    quotes={}
    for i in range(0,len(codes),40):
        try: quotes.update(tencent_quotes(codes[i:i+40]))
        except Exception: pass
    histories={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs={ex.submit(em_kline,c,today,140):c for c in codes}
        for f in as_completed(fs):
            try: histories[fs[f]]=f.result()
            except Exception: histories[fs[f]]=[]
    tails=tail_codes(today)
    plans=[]
    for c,m in candidates.items():
        p=plan_for(m,quotes.get(c),histories.get(c) or [],today,c in official_meta,c in tails)
        if p:plans.append(p)
    official_plans=sorted([p for p in plans if p['official']],key=lambda p:(p['action']=='买入候选',p['setup']['score']),reverse=True)
    setup_candidates=sorted([p for p in plans if not p['official'] and p['action'] in {'买入候选','等待触发'}],key=lambda p:(p['action']=='买入候选',p['setup']['score']),reverse=True)[:10]
    live_count=sum(1 for q in quotes.values() if q.get('quoteDate')==today.replace('-',''))
    phase='LIVE' if live_count else ('PREOPEN' if now.hour<9 else 'CLOSED_OR_STALE')
    payload={'schemaVersion':1,'date':today,'generatedAt':now.isoformat(timespec='seconds'),'phase':phase,'officialDate':snap.get('date'),
             'officialPlans':official_plans,'setupCandidates':setup_candidates,
             'summary':{'official':len(official_plans),'officialBuy':sum(p['action']=='买入候选' for p in official_plans),'officialWatch':sum(p['action']=='等待触发' for p in official_plans),'expandedSetupCandidates':len(setup_candidates)},
             'rules':{'entry':'只在形态+价格区间同时满足时给“买入候选”；过度延伸、破位或接近涨停默认不追。','exit':'止损/TP为条件式计划；A股普通股票T+1，买入日不生成可执行卖出。','dayRange':'当日低点→高点仅作行情描述，不视为可实现收益；真实信号MFE需按信号发生后的分钟序列计算。','history':'历史形态统计只使用当前日期之前的数据，当前信号不看未来。'},
             'sources':['腾讯实时行情','东方财富板块成分/前复权日线','Official冻结池','TailCore（如当日存在）']}
    OUTDIR.mkdir(parents=True,exist_ok=True)
    (OUTDIR/'latest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    intra=OUTDIR/'intraday'/today; intra.mkdir(parents=True,exist_ok=True)
    if phase=='LIVE' or os.getenv('FORCE_SNAPSHOT','0')=='1':
        slot=now.strftime('%H%M'); (intra/f'{slot}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if now.hour>=15 and phase!='PREOPEN':
        hist=OUTDIR/'history'; hist.mkdir(parents=True,exist_ok=True)
        final=hist/f'{today}.json'
        if not final.exists(): final.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'date':today,'phase':phase,**payload['summary']},ensure_ascii=False))

if __name__=='__main__': main()
