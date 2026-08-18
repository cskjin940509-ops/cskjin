#!/usr/bin/env python3
import json, math, os, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
CN=timezone(timedelta(hours=8)); ROOT=Path(__file__).resolve().parents[1]
SNAPS=ROOT/'astock_snapshots'/'index.json'; GATEWAY=ROOT/'astock_gateway'; VERSION='v1.5.1-daily-scanner'
def get_json(url,timeout=8):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 AStockStrategy/1.5','Accept':'*/*','Referer':'https://quote.eastmoney.com/'})
    with urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
def n(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except:return None
def rank(vals,v):
    xs=sorted(x for x in vals if x is not None)
    if v is None or not xs:return 50.0
    return 100*(sum(x<v for x in xs)+0.5*sum(x==v for x in xs))/len(xs)
def em_clist(fs,fields,pz=120,fid='f6'):
    q={'pn':1,'pz':pz,'po':1,'np':1,'fltt':2,'invt':2,'fid':fid,'fs':fs,'fields':fields,'ut':'bd1d9ddb04089700cf9c27f6f7426281'}
    last=None
    for host in ('push2.eastmoney.com','push2delay.eastmoney.com'):
        try:
            d=(get_json(f'https://{host}/api/qt/clist/get?'+urlencode(q)).get('data') or {}).get('diff') or []
            if d:return d
        except Exception as e:last=e
    raise RuntimeError(last or '东方财富列表不可用')
def kline(secid,lmt=80):
    q={'secid':secid,'klt':101,'fqt':1,'lmt':lmt,'end':'20500101','fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61','ut':'fa5fd1943c7b386f172d6893dbfba10b'}
    d=(get_json('https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(q)).get('data') or {});out=[]
    for row in d.get('klines') or []:
        f=row.split(',')
        if len(f)>=7 and n(f[2]) is not None:out.append({'date':f[0],'close':n(f[2]),'amount':n(f[6])})
    return out
def ret(c,k):return c[-1]/c[-1-k]-1 if len(c)>k and c[-1-k] else None
def trend(rows):
    c=[x['close'] for x in rows if x.get('close') is not None]
    if len(c)<21:return {'r20':None,'r60':None,'mta':'数据不足','mtaScore':50}
    r20=ret(c,20);r60=ret(c,60) if len(c)>60 else None;d=c[-1]>(statistics.fmean(c[-20:]) if len(c)>=20 else c[-1]);wc=c[4::5];w=wc[-1]>(statistics.fmean(wc[-4:]) if len(wc)>=4 else wc[-1]);mc=c[19::20];m=mc[-1]>(statistics.fmean(mc[-3:]) if len(mc)>=3 else mc[-1]) if mc else w;cnt=int(d)+int(w)+int(m);return {'r20':r20,'r60':r60,'mta':{3:'日周月共振',2:'双周期共振',1:'单周期趋势',0:'趋势偏弱'}[cnt],'mtaScore':[35,55,75,92][cnt]}
def load(day):
    p=GATEWAY/'history'/f'{day}.json'
    if not p.exists():p=GATEWAY/'latest.json'
    o=json.loads(p.read_text(encoding='utf-8'))
    if (o.get('marketSnapshot') or {}).get('sourceDate')!=day:raise RuntimeError('市场快照日期不匹配')
    return o
def preselect_boards(payload):
    rows=[]
    for kind in ('industry','concept'):
        for b in (payload.get('boardHeatmap') or {}).get(kind) or []:
            if not b.get('boardCode') or not b.get('name'):continue
            u,d,f=int(b.get('up') or 0),int(b.get('down') or 0),int(b.get('flat') or 0);br=n(b.get('breadthPct'));br=br if br is not None else (100*u/(u+d+f) if u+d+f else 50);rows.append({**b,'kind':kind,'breadthPct':br})
    ch=[n(x.get('changePct')) for x in rows];fl=[n(x.get('mainFlowPct')) for x in rows];am=[n(x.get('amount')) for x in rows]
    for x in rows:x['quick']=0.35*rank(ch,n(x.get('changePct')))+0.25*x['breadthPct']+0.20*rank(fl,n(x.get('mainFlowPct')))+0.20*rank(am,n(x.get('amount')))
    return sorted(rows,key=lambda x:x['quick'],reverse=True)[:60]
def board_hist(b,bench):
    try:
        h=trend(kline('90.'+b['boardCode']));h['rs20']=(h['r20']-bench['r20']) if h['r20'] is not None and bench.get('r20') is not None else h['r20'];h['rs60']=(h['r60']-bench['r60']) if h['r60'] is not None and bench.get('r60') is not None else h['r60'];return h
    except:return {'r20':None,'r60':None,'rs20':None,'rs60':None,'mta':'历史趋势未同步','mtaScore':50}
def choose_sectors(payload):
    top=preselect_boards(payload)
    try:bench=trend(kline('1.000300'))
    except:bench={'r20':0,'r60':0}
    hist={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs={ex.submit(board_hist,b,bench):b['boardCode'] for b in top}
        for f in as_completed(fs):hist[fs[f]]=f.result()
    rs=[hist[b['boardCode']].get('rs20') for b in top];scored=[]
    for b in top:
        h=hist[b['boardCode']];score=0.45*b['quick']+0.35*rank(rs,h.get('rs20'))+0.20*h.get('mtaScore',50);st='确认主线' if score>=78 and b['breadthPct']>=55 else ('候选主线' if score>=68 else '观察');scored.append({'boardCode':b['boardCode'],'name':b['name'],'type':'行业' if b['kind']=='industry' else '概念','score':round(score,2),'status':st,'changePct':n(b.get('changePct')),'amount':n(b.get('amount')),'mainNetFlow':n(b.get('mainNetFlow')),'mainFlowPct':n(b.get('mainFlowPct')),'breadthPct':round(b['breadthPct'],2),'RS20':round(100*h['rs20'],2) if h.get('rs20') is not None else None,'RS60':round(100*h['rs60'],2) if h.get('rs60') is not None else None,'MTA':h.get('mta'),'confidence':'高' if h.get('rs20') is not None else '中','reason':f"综合强度{score:.1f}；上涨扩散{b['breadthPct']:.0f}%；涨跌{n(b.get('changePct')) or 0:+.2f}%；主力资金占比{n(b.get('mainFlowPct')) or 0:+.2f}%"})
    scored.sort(key=lambda x:x['score'],reverse=True);sel=[]
    for x in scored:
        base=x['name'].replace('Ⅱ','').replace('Ⅲ','').replace('行业','').replace('概念','')
        if any(base in y['name'] or y['name'].replace('Ⅱ','').replace('Ⅲ','') in base for y in sel):continue
        if x['score']<65 and len(sel)>=3:continue
        sel.append(x)
        if len(sel)>=5:break
    return sel
def members(b):
    out=[]
    for x in em_clist('b:'+b['boardCode'],'f2,f3,f6,f8,f12,f14,f20,f21,f62,f184',100,'f6'):
        code=str(x.get('f12') or '');name=str(x.get('f14') or '');price=n(x.get('f2'));amt=n(x.get('f6'))
        if not code or not name or 'ST' in name.upper() or price is None or amt is None or amt<5e7:continue
        out.append({'code':code,'name':name,'sector':b['name'],'sectorScore':b['score'],'price':price,'changePct':n(x.get('f3')),'amount':amt,'turnover':n(x.get('f8')),'mainNetFlow':n(x.get('f62')),'mainFlowPct':n(x.get('f184'))})
    return out
def sid(code):return ('1.' if code.startswith(('5','6','9')) else '0.')+code
def shist(s,bench):
    try:
        h=trend(kline(sid(s['code'])));h['rs20']=(h['r20']-bench['r20']) if h['r20'] is not None and bench.get('r20') is not None else h['r20'];h['rs60']=(h['r60']-bench['r60']) if h['r60'] is not None and bench.get('r60') is not None else h['r60'];return h
    except:return {'r20':None,'r60':None,'rs20':None,'rs60':None,'mta':'历史趋势未同步','mtaScore':50}
def choose_stocks(sel):
    cand=[]
    for b in sel:
        try:cand+=members(b)
        except:pass
    de={}
    for s in cand:
        if s['code'] not in de or s['sectorScore']>de[s['code']]['sectorScore']:de[s['code']]=s
    cand=sorted(de.values(),key=lambda x:x['amount'],reverse=True)[:60]
    if not cand:raise RuntimeError('主线成分股为空')
    try:bench=trend(kline('1.000300'))
    except:bench={'r20':0,'r60':0}
    hs={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs={ex.submit(shist,s,bench):s['code'] for s in cand}
        for f in as_completed(fs):hs[fs[f]]=f.result()
    rv=[hs[s['code']].get('rs20') for s in cand];fv=[s.get('mainFlowPct') for s in cand];av=[s['amount'] for s in cand];tv=[s.get('turnover') for s in cand];cv=[s.get('changePct') for s in cand];sv=[s['sectorScore'] for s in cand];sc=[]
    for s in cand:
        h=hs[s['code']];rs=rank(rv,h.get('rs20'));flow=rank(fv,s.get('mainFlowPct'));liq=.7*rank(av,s['amount'])+.3*rank(tv,s.get('turnover'));mom=rank(cv,s.get('changePct'));sec=rank(sv,s['sectorScore']);score=.25*rs+.18*flow+.17*liq+.12*mom+.15*h.get('mtaScore',50)+.13*sec;flowScore=.65*score+.35*flow;z={**s,**h,'score':round(score,2),'flowScore':round(flowScore,2),'confidence':'高' if h.get('rs20') is not None else '中'};z['reason']=f"综合强度{score:.1f}；{h.get('mta')}；20日相对强弱{100*h['rs20']:+.1f}%" if h.get('rs20') is not None else f"综合强度{score:.1f}；{h.get('mta')}";sc.append(z)
    sc.sort(key=lambda x:x['score'],reverse=True);b0=[x['code'] for x in sc[:10]];b3=[x['code'] for x in sorted(sc,key=lambda x:x['flowScore'],reverse=True)[:10]];b4=[x['code'] for x in sorted(sc,key=lambda x:.65*x['score']+.35*x['flowScore'],reverse=True)[:10]];return sc,{'B0':b0,'B1':[],'B2':[],'B3':b3,'B4':b4}
def freeze(day,payload,sel,sc,pools):
    arr=json.loads(SNAPS.read_text(encoding='utf-8')) if SNAPS.exists() else [];idx=next((i for i,x in enumerate(arr) if x.get('date')==day),None);old=arr[idx] if idx is not None else {'date':day};prev=next((x for x in sorted(arr,key=lambda z:z.get('date',''),reverse=True) if x.get('date','')<day and x.get('status')=='Official'),{});prevb=((prev.get('pools') or {}).get('B4') or []);pm={c:[p for p,v in pools.items() if c in v] for c in {q for v in pools.values() for q in v}};sm={}
    for s in sc:
        if s['code'] not in pm:continue
        sm[s['code']]={'name':s['name'],'sector':s['sector'],'RS':round(100*s['rs20'],2) if s.get('rs20') is not None else None,'RS60':round(100*s['rs60'],2) if s.get('rs60') is not None else None,'MTA':s['mta'],'score':s['score'],'reason':s['reason'],'selectionPrice':s['price'],'confidence':'低' if 'B4' in pm[s['code']] else s['confidence'],'pools':pm[s['code']],'changePct':s.get('changePct'),'amount':s.get('amount'),'turnover':s.get('turnover'),'mainNetFlow':s.get('mainNetFlow'),'mainFlowPct':s.get('mainFlowPct')}
    now=datetime.now(CN).isoformat(timespec='seconds');o=dict(old);o.update({'date':day,'status':'Official','regime':old.get('regime') or '结构性主升/轮动','strategyVersion':VERSION,'selectedSectors':sel,'mainlines':[x['name'] for x in sel if x['status']!='观察'],'pools':pools,'stocks':sm,'added':[c for c in pools['B4'] if c not in prevb],'removed':[c for c in prevb if c not in pools['B4']],'factorAvailability':{'B0':'可用','B1':'两融数据未同步，正式池留空','B2':'ETF真实申赎未同步，正式池留空','B3':'可用：主力资金口径','B4':'低置信度：仅B0+B3合成'},'confidence':'中低','availableAt':now,'poolPerformance':old.get('poolPerformance') or old.get('performance') or {},'sectorPerformance':old.get('sectorPerformance') or {},'stockPerformance':old.get('stockPerformance') or {},'note':'日终扫描已冻结；B1/B2缺失不伪造，B4按当前可用因子合成并标低置信度。'});o['marketSnapshot']=old.get('marketSnapshot') or payload.get('marketSnapshot');o['boardHeatmap']=old.get('boardHeatmap') or payload.get('boardHeatmap');o.setdefault('syncStatus',{}).update({'officialCohort':'ready','officialUpdatedAt':now,'strategyVersion':VERSION})
    if idx is None:arr.append(o)
    else:arr[idx]=o
    arr.sort(key=lambda x:x.get('date',''));SNAPS.write_text(json.dumps(arr,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return o
def main():
    day=os.environ.get('TARGET_DATE') or ((json.loads((GATEWAY/'latest.json').read_text(encoding='utf-8')).get('marketSnapshot') or {}).get('sourceDate'))
    if not day:raise SystemExit('无法确定交易日')
    p=load(day);sel=choose_sectors(p);sc,pools=choose_stocks(sel);o=freeze(day,p,sel,sc,pools);print(json.dumps({'date':day,'mainlines':o['mainlines'],'B0':pools['B0'],'B3':pools['B3'],'B4':pools['B4'],'B1':[],'B2':[]},ensure_ascii=False))
if __name__=='__main__':main()
