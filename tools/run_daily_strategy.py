#!/usr/bin/env python3
import json, math, os, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / 'astock_snapshots' / 'index.json'
GATEWAY = ROOT / 'astock_gateway'
UA = 'Mozilla/5.0 AStockStrategy-Strategy/1.5'
STRATEGY_VERSION = 'v1.5-daily-scanner-public'


def get_json(url, timeout=12):
    req = Request(url, headers={
        'User-Agent': UA,
        'Accept': '*/*',
        'Cache-Control': 'no-cache',
        'Referer': 'https://quote.eastmoney.com/'
    })
    with urlopen(req, timeout=timeout) as r:
        if r.status < 200 or r.status >= 300:
            raise RuntimeError(f'HTTP {r.status}')
        return json.loads(r.read().decode('utf-8', errors='replace'))


def num(v):
    try:
        if v in (None, '', '-', '--'): return None
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def pct_rank(values, value, neutral=50.0):
    xs = sorted(x for x in values if x is not None and math.isfinite(x))
    if not xs or value is None: return neutral
    if len(xs) == 1: return 50.0
    below = sum(1 for x in xs if x < value)
    equal = sum(1 for x in xs if x == value)
    return 100.0 * (below + 0.5 * equal) / len(xs)


def eastmoney_clist(fs, fields, pz=200, fid='f6'):
    params = {'pn':1,'pz':pz,'po':1,'np':1,'fltt':2,'invt':2,'fid':fid,'fs':fs,'fields':fields,'ut':'bd1d9ddb04089700cf9c27f6f7426281'}
    last = None
    for host in ('push2.eastmoney.com','push2delay.eastmoney.com'):
        for attempt in range(3):
            try:
                url=f'https://{host}/api/qt/clist/get?'+urlencode({**params,'_':int(time.time()*1000)})
                diff=(get_json(url).get('data') or {}).get('diff') or []
                if diff: return diff
                last=RuntimeError(f'{host} empty')
            except Exception as e:
                last=e; time.sleep(0.4*(attempt+1))
    raise RuntimeError(str(last or '东方财富列表接口不可用'))


def kline(secid, limit=90):
    params={'secid':secid,'klt':101,'fqt':1,'lmt':limit,'end':'20500101','iscca':1,'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','ut':'fa5fd1943c7b386f172d6893dbfba10b'}
    data=(get_json('https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(params)).get('data') or {})
    out=[]
    for row in data.get('klines') or []:
        f=row.split(',')
        if len(f)<11: continue
        out.append({'date':f[0],'open':num(f[1]),'close':num(f[2]),'high':num(f[3]),'low':num(f[4]),'volume':num(f[5]),'amount':num(f[6]),'turnover':num(f[10])})
    if not out: raise RuntimeError('历史K线不可用')
    return out


def secid_stock(code): return ('1.' if code.startswith(('5','6','9')) else '0.')+code

def ret(closes,n):
    if len(closes)<=n or closes[-1] is None or closes[-1-n] in (None,0): return None
    return closes[-1]/closes[-1-n]-1.0

def ma(closes,n):
    xs=[x for x in closes[-n:] if x is not None]
    return statistics.fmean(xs) if len(xs)>=max(3,n//2) else None


def trend_features(rows):
    closes=[r['close'] for r in rows if r.get('close') is not None]
    if len(closes)<12: return {'r5':None,'r20':None,'r60':None,'mtaScore':50.0,'mta':'数据不足'}
    r5,r20,r60=ret(closes,5),ret(closes,20),ret(closes,60)
    daily=closes[-1]>(ma(closes,20) or closes[-1])
    weekly_closes=closes[4::5] if len(closes)>=10 else closes
    monthly_closes=closes[19::20] if len(closes)>=20 else closes
    weekly=weekly_closes[-1]>(ma(weekly_closes,4) or weekly_closes[-1]) if len(weekly_closes)>=4 else daily
    monthly=monthly_closes[-1]>(ma(monthly_closes,3) or monthly_closes[-1]) if len(monthly_closes)>=3 else weekly
    count=int(daily)+int(weekly)+int(monthly)
    return {'r5':r5,'r20':r20,'r60':r60,'mtaScore':[35,55,75,92][count],'mta':{3:'日周月共振',2:'双周期共振',1:'单周期趋势',0:'趋势偏弱'}[count]}


def load_payload(target_date):
    p=GATEWAY/'history'/f'{target_date}.json'
    if p.exists(): return json.loads(p.read_text(encoding='utf-8'))
    p=GATEWAY/'latest.json'
    obj=json.loads(p.read_text(encoding='utf-8'))
    source=(obj.get('marketSnapshot') or {}).get('sourceDate')
    if source!=target_date: raise RuntimeError(f'市场快照日期 {source} 与目标日期 {target_date} 不一致')
    return obj


def board_history_features(board_code, bench):
    try:
        f=trend_features(kline('90.'+board_code,90)); b20=bench.get('r20'); b60=bench.get('r60')
        f['rs20']=(f['r20']-b20) if f['r20'] is not None and b20 is not None else f['r20']
        f['rs60']=(f['r60']-b60) if f['r60'] is not None and b60 is not None else f['r60']
        return f
    except Exception:
        return {'r5':None,'r20':None,'r60':None,'rs20':None,'rs60':None,'mtaScore':50.0,'mta':'历史趋势未同步'}


def choose_sectors(payload):
    heat=payload.get('boardHeatmap') or {}; rows=[]
    for kind in ('industry','concept'):
        for b in heat.get(kind) or []:
            if b.get('boardCode') and b.get('name'):
                x=dict(b); x['kind']=kind; rows.append(x)
    if not rows: raise RuntimeError('板块热力图为空，无法筛选主线')
    try: bench=trend_features(kline('1.000300',90))
    except Exception: bench={'r20':0.0,'r60':0.0}
    hist={}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(board_history_features,b['boardCode'],bench):b['boardCode'] for b in rows}
        for fut in as_completed(futs): hist[futs[fut]]=fut.result()
    rs20_vals=[hist[b['boardCode']].get('rs20') for b in rows]; rs60_vals=[hist[b['boardCode']].get('rs60') for b in rows]
    amount_vals=[num(b.get('amount')) for b in rows]; flow_vals=[num(b.get('mainFlowPct')) for b in rows]; change_vals=[num(b.get('changePct')) for b in rows]
    scored=[]
    for b in rows:
        h=hist[b['boardCode']]; br=num(b.get('breadthPct'))
        if br is None:
            u,d,f=int(b.get('up') or 0),int(b.get('down') or 0),int(b.get('flat') or 0); br=100*u/(u+d+f) if (u+d+f)>0 else 50.0
        rs=0.65*pct_rank(rs20_vals,h.get('rs20'))+0.35*pct_rank(rs60_vals,h.get('rs60'))
        mom=0.55*pct_rank(change_vals,num(b.get('changePct')))+0.45*pct_rank(rs20_vals,h.get('rs20'))
        flow=pct_rank(flow_vals,num(b.get('mainFlowPct'))); vol=pct_rank(amount_vals,num(b.get('amount')))
        score=0.25*rs+0.20*flow+0.15*br+0.15*mom+0.15*vol+0.10*h.get('mtaScore',50)
        state='确认主线' if score>=78 and br>=55 else ('候选主线' if score>=68 else '观察')
        scored.append({'boardCode':b['boardCode'],'name':b['name'],'type':'行业' if b['kind']=='industry' else '概念','score':round(score,2),'status':state,'changePct':num(b.get('changePct')),'amount':num(b.get('amount')),'mainNetFlow':num(b.get('mainNetFlow')),'mainFlowPct':num(b.get('mainFlowPct')),'breadthPct':round(br,2),'RS20':round(100*h['rs20'],2) if h.get('rs20') is not None else None,'RS60':round(100*h['rs60'],2) if h.get('rs60') is not None else None,'MTA':h.get('mta'),'reason':f"综合强度{score:.1f}；上涨扩散{br:.0f}%；当日涨跌{num(b.get('changePct')) or 0:+.2f}%；主力资金占比{num(b.get('mainFlowPct')) or 0:+.2f}%",'confidence':'高' if h.get('rs20') is not None else '中'})
    scored.sort(key=lambda x:x['score'],reverse=True); selected=[]
    for x in scored:
        normalized=x['name'].replace('Ⅱ','').replace('Ⅲ','').replace('行业','').replace('概念','')
        if any(normalized in y['name'] or y['name'].replace('Ⅱ','').replace('Ⅲ','') in normalized for y in selected): continue
        if x['score']<65 and len(selected)>=3: continue
        selected.append(x)
        if len(selected)>=5: break
    return selected


def board_members(board):
    rows=eastmoney_clist('b:'+board['boardCode'],'f2,f3,f6,f8,f12,f14,f20,f21,f62,f184',150,'f6'); out=[]
    for x in rows:
        code=str(x.get('f12') or ''); name=str(x.get('f14') or '')
        if not code or not name or 'ST' in name.upper(): continue
        price=num(x.get('f2')); amount=num(x.get('f6'))
        if price is None or price<=0 or amount is None or amount<5e7: continue
        out.append({'code':code,'name':name,'sector':board['name'],'sectorScore':board['score'],'price':price,'changePct':num(x.get('f3')),'amount':amount,'turnover':num(x.get('f8')),'marketCap':num(x.get('f20')),'floatCap':num(x.get('f21')),'mainNetFlow':num(x.get('f62')),'mainFlowPct':num(x.get('f184'))})
    return out


def stock_hist(stock,bench):
    try:
        f=trend_features(kline(secid_stock(stock['code']),90)); f['rs20']=(f['r20']-bench.get('r20')) if f.get('r20') is not None and bench.get('r20') is not None else f.get('r20'); f['rs60']=(f['r60']-bench.get('r60')) if f.get('r60') is not None and bench.get('r60') is not None else f.get('r60'); return f
    except Exception:
        return {'r5':None,'r20':None,'r60':None,'rs20':None,'rs60':None,'mtaScore':50.0,'mta':'历史趋势未同步'}


def choose_stocks(selected):
    candidates=[]
    for board in selected:
        try: candidates.extend(board_members(board))
        except Exception: continue
    if not candidates: raise RuntimeError('主线板块成分股读取失败')
    dedup={}
    for s in candidates:
        if s['code'] not in dedup or s['sectorScore']>dedup[s['code']]['sectorScore']: dedup[s['code']]=s
    candidates=sorted(dedup.values(),key=lambda x:x.get('amount') or 0,reverse=True)[:100]
    try: bench=trend_features(kline('1.000300',90))
    except Exception: bench={'r20':0.0,'r60':0.0}
    hist={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(stock_hist,s,bench):s['code'] for s in candidates}
        for fut in as_completed(futs): hist[futs[fut]]=fut.result()
    rs20_vals=[hist[s['code']].get('rs20') for s in candidates]; rs60_vals=[hist[s['code']].get('rs60') for s in candidates]; flow_vals=[s.get('mainFlowPct') for s in candidates]; amount_vals=[s.get('amount') for s in candidates]; turnover_vals=[s.get('turnover') for s in candidates]; change_vals=[s.get('changePct') for s in candidates]; sector_vals=[s.get('sectorScore') for s in candidates]
    scored=[]
    for s in candidates:
        h=hist[s['code']]; rs=0.7*pct_rank(rs20_vals,h.get('rs20'))+0.3*pct_rank(rs60_vals,h.get('rs60')); flow=pct_rank(flow_vals,s.get('mainFlowPct')); liquidity=0.7*pct_rank(amount_vals,s.get('amount'))+0.3*pct_rank(turnover_vals,s.get('turnover')); momentum=pct_rank(change_vals,s.get('changePct')); sector=pct_rank(sector_vals,s.get('sectorScore'))
        base=0.25*rs+0.15*flow+0.15*liquidity+0.15*momentum+0.15*h.get('mtaScore',50)+0.15*sector; flow_aug=0.65*base+0.35*flow
        x=dict(s); x.update(h); x['score']=round(base,2); x['flowScore']=round(flow_aug,2); x['confidence']='高' if h.get('rs20') is not None else '中'; x['reason']=f"综合强度{base:.1f}；{h.get('mta')}；20日相对强弱{(100*h['rs20']):+.1f}%" if h.get('rs20') is not None else f"综合强度{base:.1f}；{h.get('mta')}；历史趋势数据不足"; scored.append(x)
    scored.sort(key=lambda x:x['score'],reverse=True)
    b0=[x['code'] for x in scored[:10]]; b3=[x['code'] for x in sorted(scored,key=lambda x:x['flowScore'],reverse=True)[:10]]; b4=[x['code'] for x in sorted(scored,key=lambda x:0.65*x['score']+0.35*x['flowScore'],reverse=True)[:10]]
    return scored,{'B0':b0,'B1':[],'B2':[],'B3':b3,'B4':b4}


def stock_meta(scored,pools):
    pool_members={c:[p for p,codes in pools.items() if c in codes] for c in {c for codes in pools.values() for c in codes}}; out={}
    for s in scored:
        code=s['code']
        if code not in pool_members: continue
        out[code]={'name':s['name'],'sector':s['sector'],'RS':round(100*s['rs20'],2) if s.get('rs20') is not None else None,'RS60':round(100*s['rs60'],2) if s.get('rs60') is not None else None,'MTA':s.get('mta'),'score':s.get('score'),'reason':s.get('reason'),'selectionPrice':s.get('price'),'confidence':'低' if 'B4' in pool_members[code] else s.get('confidence','中'),'pools':pool_members[code],'changePct':s.get('changePct'),'amount':s.get('amount'),'turnover':s.get('turnover'),'mainNetFlow':s.get('mainNetFlow'),'mainFlowPct':s.get('mainFlowPct')}
    return out


def freeze_snapshot(target_date,payload,selected,scored_stocks,pools):
    arr=json.loads(SNAPS.read_text(encoding='utf-8')) if SNAPS.exists() else []; idx=next((i for i,x in enumerate(arr) if x.get('date')==target_date),None); existing=arr[idx] if idx is not None else {'date':target_date}; previous=next((x for x in sorted(arr,key=lambda z:z.get('date',''),reverse=True) if x.get('date','')<target_date and x.get('status')=='Official'),None); prev_b4=((previous or {}).get('pools') or {}).get('B4') or []; b4=pools['B4']; now=datetime.now(CN).isoformat(timespec='seconds')
    official=dict(existing); official.update({'date':target_date,'status':'Official','regime':existing.get('regime') or '结构性主升/轮动','strategyVersion':STRATEGY_VERSION,'selectedSectors':selected,'mainlines':[x['name'] for x in selected if x['status'] in ('确认主线','候选主线')],'pools':pools,'stocks':stock_meta(scored_stocks,pools),'added':[c for c in b4 if c not in prev_b4],'removed':[c for c in prev_b4 if c not in b4],'upgraded':[],'downgraded':[],'factorAvailability':{'B0':'可用：价格/趋势/相对强弱/流动性/板块强度','B1':'未同步：两融时点数据，正式池留空','B2':'未同步：ETF份额+净值真实申赎，正式池留空','B3':'可用：东方财富主力资金口径','B4':'低置信度：仅基于当前可用B0+B3合成，未计入B1/B2'},'confidence':'中低','availableAt':now,'poolPerformance':existing.get('poolPerformance') or existing.get('performance') or {},'sectorPerformance':existing.get('sectorPerformance') or {},'stockPerformance':existing.get('stockPerformance') or {},'note':'日终扫描已冻结。板块与B0/B3由当日收盘市场截面动态计算；B1两融与B2 ETF真实申赎尚未接入，因此正式池留空；B4为当前可用因子合成并标低置信度，后续不得用未来数据改写当日名单。'})
    official['marketSnapshot']=existing.get('marketSnapshot') or payload.get('marketSnapshot'); official['boardHeatmap']=existing.get('boardHeatmap') or payload.get('boardHeatmap'); sync=official.setdefault('syncStatus',{}); sync.update({'officialCohort':'ready','officialUpdatedAt':now,'strategyVersion':STRATEGY_VERSION})
    if idx is None: arr.append(official)
    else: arr[idx]=official
    arr.sort(key=lambda x:x.get('date','')); SNAPS.parent.mkdir(parents=True,exist_ok=True); SNAPS.write_text(json.dumps(arr,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return official


def main():
    target=os.environ.get('TARGET_DATE')
    if not target:
        latest=GATEWAY/'latest.json'; target=((json.loads(latest.read_text(encoding='utf-8')).get('marketSnapshot') or {}).get('sourceDate'))
    if not target: raise SystemExit('无法确定目标交易日')
    payload=load_payload(target); selected=choose_sectors(payload); scored_stocks,pools=choose_stocks(selected); official=freeze_snapshot(target,payload,selected,scored_stocks,pools)
    print(json.dumps({'date':target,'status':official['status'],'strategyVersion':STRATEGY_VERSION,'mainlines':official['mainlines'],'pools':{k:len(v) for k,v in pools.items()},'B4':pools['B4'],'confidence':official['confidence']},ensure_ascii=False))

if __name__=='__main__': main()
