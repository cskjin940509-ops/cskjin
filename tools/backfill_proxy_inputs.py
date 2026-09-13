"""Backfill reproducible proxy inputs; never persist the access token."""
import gzip
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

token = os.getenv("STOCK_API_TOKEN", "").strip() or sys.stdin.readline().strip()
if not token:
    raise SystemExit('Token required on stdin')
out = Path(__file__).resolve().parents[1] / 'astock_factors/proxy_backfill'
out.mkdir(parents=True, exist_ok=True)
jobs = [('margin', {'start_date':'20240901','end_date':'20260911','limit':2000}),
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

# ETF share history is a cross-section. Fetch it one trading day at a time so
# the service's row limit cannot silently truncate a 485-day request.
margin_path = out / 'margin.json'
if margin_path.exists():
    margin_payload = json.loads(margin_path.read_text(encoding='utf-8'))
    body = margin_payload.get('data') or {}
    fields = body.get('fields') or []
    date_index = fields.index('trade_date')
    exchange_index = fields.index('exchange_id')
    trade_dates = sorted({str(row[date_index]) for row in body.get('items') or []
                          if str(row[exchange_index]) in ('SSE', 'SZSE')})
    etf_dir = out / 'etf_share_daily'
    etf_dir.mkdir(parents=True, exist_ok=True)
    completed = 0
    for trade_date in trade_dates:
        path = etf_dir / f'{trade_date}.json'
        if path.exists():
            completed += 1
            continue
        params = {'trade_date': trade_date, 'limit': 6000}
        req = urllib.request.Request('https://jiaoch.top/',
            data=json.dumps({'api_name':'fund_share','token':token,'params':params,'fields':''}).encode(),
            headers={'Content-Type':'application/json','Accept-Encoding':'gzip'})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                if response.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
            data = json.loads(raw)
            rows = ((data.get('data') or {}).get('items') or []) if data.get('code') == 0 else []
            if not rows:
                continue
            payload = {'source':'https://jiaoch.top/', 'classification':'THIRD_PARTY_SOURCE_RAW',
                       'retrievedAt':datetime.now(timezone.utc).isoformat(), 'api':'fund_share',
                       'params':params, 'data':data.get('data'), 'positionEligible':False}
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(path)
            completed += 1
            if completed % 25 == 0:
                print(json.dumps({'api':'fund_share','completedTradingDays':completed}),flush=True)
        except Exception as error:
            print(json.dumps({'api':'fund_share','tradeDate':trade_date,
                              'errorType':type(error).__name__}),flush=True)
    print(json.dumps({'api':'fund_share','completedTradingDays':completed,
                      'requestedTradingDays':len(trade_dates)}),flush=True)
