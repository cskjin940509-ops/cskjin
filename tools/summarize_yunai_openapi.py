#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'astock_gateway'/'yunai_openapi.json'
OUT=ROOT/'astock_gateway'/'yunai_endpoint_catalog.json'


def req_schema(ep):
    body=ep.get('requestBody') or {}
    content=body.get('content') or {}
    for v in content.values():
        if not isinstance(v,dict): continue
        ref=v.get('$ref')
        if ref: return ref.rsplit('/',1)[-1]
        typ=v.get('type')
        if typ: return typ
    return None


def cats(ep):
    text=(' '.join([str(ep.get('path') or ''),str(ep.get('summary') or ''),str(ep.get('operationId') or '')])).lower()
    groups=[
      ('两融',('margin','financing','securities-lending','融券','融资','两融')),
      ('ETF',('etf','fund-share','fund share','nav','份额','申购','赎回')),
      ('资金流',('capital-distribution','money-flow','fund-flow','capital-flow','资金分布','资金流')),
      ('财务',('financial','fundamental','财务','基本面')),
      ('公司行动',('dividend','split','分红','拆分')),
      ('期货',('futures','期货')),
      ('指数',('global-index','指数')),
      ('K线',('bars','kline','k线')),
      ('逐笔/盘口',('trade-ticks','order-book','盘口','逐笔')),
      ('行情',('quotes','quote','market-status','行情')),
      ('证券基础',('symbol','security','instrument','calendar','证券','代码')),
      ('WebSocket',('websocket','ws')),
    ]
    out=[n for n,ks in groups if any(k in text for k in ks)]
    return out or ['其他']


def main():
    doc=json.loads(SRC.read_text(encoding='utf-8'))
    eps=[]
    for i,ep in enumerate(doc.get('endpoints') or [],1):
        eps.append({
          'no':i,'method':ep.get('method'),'path':ep.get('path'),'summary':ep.get('summary'),
          'operationId':ep.get('operationId'),'requestSchema':req_schema(ep),
          'categories':cats(ep),
          'queryParameters':[{'name':p.get('name'),'required':p.get('required'),'description':p.get('description')} for p in (ep.get('parameters') or [])],
        })
    counts={}
    for e in eps:
        for c in e['categories']: counts[c]=counts.get(c,0)+1
    out={'source':doc.get('source'),'endpointCount':len(eps),'methodCounts':doc.get('methodCounts'),'categoryCounts':counts,'endpoints':eps}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for e in eps:
        print(f"{e['no']:02d} {e['method']:<4} {e['path']} | {e['summary']} | req={e['requestSchema'] or '-'} | {','.join(e['categories'])}")

if __name__=='__main__': main()
