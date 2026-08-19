#!/usr/bin/env python3
import json, os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SNAPS=ROOT/'astock_snapshots'/'index.json'
OUT=ROOT/'astock_gateway'/'validation'
code=os.getenv('SYMBOL','002371').strip()
entry_day=os.getenv('TARGET_DATE','2026-08-18').strip()
arr=json.loads(SNAPS.read_text(encoding='utf-8'))
refs=[]
for s in arr:
    meta=(s.get('stocks') or {}).get(code)
    perf=(s.get('stockPerformance') or {}).get(code)
    in_pools=[p for p,codes in (s.get('pools') or {}).items() if code in (codes or [])]
    if meta or perf or in_pools:
        ref={'cohortDate':s.get('date'),'status':s.get('status'),'strategyVersion':s.get('strategyVersion'),'pools':in_pools}
        if meta:
            ref['selection']={k:meta.get(k) for k in ['name','sector','selectionPrice','changePct','score','RS','RS60','MTA','reason','confidence','mainNetFlow','mainFlowPct'] if k in meta}
        if perf:
            ref['performance']={k:perf.get(k) for k in ['entryRule','entryDate','entryPrice','asOf','1D','current','MFE','MAE','source'] if k in perf}
        refs.append(ref)
report={'symbol':code,'targetEntryDate':entry_day,'references':refs}
OUT.mkdir(parents=True,exist_ok=True)
path=OUT/f'audit-{entry_day}-{code}.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
