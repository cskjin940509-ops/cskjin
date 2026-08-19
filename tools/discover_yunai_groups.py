#!/usr/bin/env python3
# Public Knife4j group discovery for quant.yunai.com.cn
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE='https://quant.yunai.com.cn'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'astock_gateway'/'yunai_groups.json'
CANDIDATES=['/v3/api-docs/swagger-config','/swagger-resources','/v3/api-docs','/v2/api-docs','/quant-market/v3/api-docs']

def get(path):
    req=Request(BASE+path,headers={'Accept':'application/json,*/*','User-Agent':'Mozilla/5.0','Referer':BASE+'/doc.html'})
    with urlopen(req,timeout=20) as r:
        raw=r.read().decode('utf-8','replace')
        try: body=json.loads(raw)
        except Exception: body=raw[:1000]
        return r.status,r.headers.get('Content-Type',''),body

def main():
    attempts=[]; groups=[]
    for path in CANDIDATES:
        try:
            status,ctype,body=get(path)
            item={'path':path,'status':status,'contentType':ctype,'type':type(body).__name__}
            if isinstance(body,dict):
                item['keys']=sorted(body.keys())[:50]
                if isinstance(body.get('urls'),list):
                    for x in body['urls']:
                        if isinstance(x,dict) and x.get('url'):
                            groups.append({'name':x.get('name'),'url':x.get('url')})
                elif isinstance(body.get('url'),str):
                    groups.append({'name':'default','url':body.get('url')})
                if isinstance(body.get('paths'),dict):
                    item['endpointCount']=sum(sum(1 for m in v if m.lower() in {'get','post','put','delete','patch'}) for v in body['paths'].values() if isinstance(v,dict))
            elif isinstance(body,list):
                item['items']=body[:100]
                for x in body:
                    if isinstance(x,dict):
                        u=x.get('location') or x.get('url')
                        if u: groups.append({'name':x.get('name'),'url':u})
            attempts.append(item)
        except HTTPError as e:
            attempts.append({'path':path,'status':e.code})
        except Exception as e:
            attempts.append({'path':path,'error':e.__class__.__name__})
    dedup=[]; seen=set()
    for g in groups:
        key=g.get('url')
        if key and key not in seen:
            seen.add(key); dedup.append(g)
    if '/quant-market/v3/api-docs' not in seen:
        dedup.append({'name':'quant-market','url':'/quant-market/v3/api-docs','source':'confirmed-doc-page'})
    OUT.write_text(json.dumps({'base':BASE,'groups':dedup,'attempts':attempts},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'groups':dedup,'attempts':attempts},ensure_ascii=False))

if __name__=='__main__': main()
