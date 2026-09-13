"""Validate returned date before accepting an old ETF share snapshot."""
import json
from pathlib import Path
from datetime import datetime, timezone
import requests

day = '2024-09-10'
url = 'https://query.sse.com.cn/commonQuery.do'
r = requests.get(url, params={'isPagination':'true','pageHelp.pageSize':'10000',
    'pageHelp.pageNo':'1','sqlId':'COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L',
    'STAT_DATE':day}, headers={'Referer':'https://www.sse.com.cn/','User-Agent':'Mozilla/5.0'}, timeout=30)
r.raise_for_status()
data = r.json()
rows = data.get('result') or []
valid = bool(rows) and all(str(x.get('STAT_DATE'))[:10] == day for x in rows)
out = Path(__file__).resolve().parents[1] / 'astock_factors/etf_history_probe'
out.mkdir(parents=True, exist_ok=True)
payload = {'requestedDate':day,'retrievedAt':datetime.now(timezone.utc).isoformat(),
           'source':url,'dateVerified':valid,'raw':data,'positionEligible':False}
(out / (day + '.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'requestedDate':day,'rows':len(rows),'dateVerified':valid}))
