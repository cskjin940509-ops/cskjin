"""Read token from stdin; preserve third-party raw data without secrets."""
import gzip
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

token = sys.stdin.readline().strip()
if not token:
    raise SystemExit('Token required on stdin')
out = Path(__file__).resolve().parents[1] / 'astock_factors/proxy_backfill'
out.mkdir(parents=True, exist_ok=True)
jobs = [('margin', {'start_date':'20240901','end_date':'20260911','limit':2000}),
        ('fund_share', {'ts_code':'510300.SH','start_date':'20240901','end_date':'20260911','limit':2000}),
        ('daily', {'ts_code':'000001.SZ','start_date':'20240901','end_date':'20260911','limit':2000})]
for name, params in jobs:
    req = urllib.request.Request('https://jiaoch.top/',
        data=json.dumps({'api_name':name,'token':token,'params':params,'fields':''}).encode(),
        headers={'Content-Type':'application/json','Accept-Encoding':'gzip'})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
            if response.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
        data = json.loads(raw)
        if data.get('code') != 0:
            print(json.dumps({'api':name,'code':data.get('code')}),flush=True)
            continue
        body = data.get('data') or {}
        payload = {'source':'https://jiaoch.top/', 'classification':'THIRD_PARTY_UNVERIFIED',
                   'retrievedAt':datetime.now(timezone.utc).isoformat(), 'api':name,
                   'params':params,'data':body,'positionEligible':False}
        path = out / (name + '.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)
        print(json.dumps({'api':name,'rows':len(body.get('items') or []),'fields':body.get('fields')}),flush=True)
    except Exception as error:
        print(json.dumps({'api':name,'errorType':type(error).__name__}),flush=True)
