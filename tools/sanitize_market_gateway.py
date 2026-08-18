#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / 'astock_gateway' / 'latest.json'
SNAPS = ROOT / 'astock_snapshots' / 'index.json'


def sanitize_market(m):
    if not isinstance(m, dict):
        return False
    n = int(m.get('sampleCount') or 0)
    if n >= 1000:
        m['breadthStatus'] = '全市场统计可用'
        return False
    changed = False
    for k in ('totalAmount', 'up', 'down', 'flat', 'medianChangePct'):
        if m.get(k) is not None:
            m[k] = None
            changed = True
    m['breadthStatus'] = '全市场统计待同步'
    m['breadthSampleCount'] = n
    m['breadthNote'] = '当前备用接口返回样本不足，不将样本统计冒充全市场。'
    return changed


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if LATEST.exists():
    root = json.loads(LATEST.read_text(encoding='utf-8'))
    if sanitize_market(root.get('marketSnapshot')):
        write_json(LATEST, root)
    # Even if values were already null, ensure metadata persists.
    elif isinstance(root.get('marketSnapshot'), dict):
        write_json(LATEST, root)

if SNAPS.exists():
    arr = json.loads(SNAPS.read_text(encoding='utf-8'))
    touched = False
    for item in arr:
        m = item.get('marketSnapshot')
        if isinstance(m, dict) and int(m.get('sampleCount') or 0) < 1000:
            sanitize_market(m)
            touched = True
    if touched:
        write_json(SNAPS, arr)

hist = ROOT / 'astock_gateway' / 'history'
if hist.exists():
    for path in hist.glob('*.json'):
        try:
            root = json.loads(path.read_text(encoding='utf-8'))
            m = root.get('marketSnapshot')
            if isinstance(m, dict) and int(m.get('sampleCount') or 0) < 1000:
                sanitize_market(m)
                write_json(path, root)
        except Exception:
            pass
