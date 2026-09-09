"""Slow evidence producer. Never writes portfolio state, ledger or latest valuation."""
from copy import deepcopy
import json
import run_ai_shadow_portfolio as base
import selection_data_v45 as feeds
import selection_research_v46 as study


def collect():
    state = base.read_json(base.STATE_PATH, base.new_state())
    previous = base.read_json(base.ROOT / 'astock_selection_evidence/latest.json', {})
    if previous.get('data'):
        state['selectionData45'] = deepcopy(previous['data'])
    radar = base.read_json(base.RADAR, {})
    codes = set(state.get('positions') or {}) | set(radar.get('stocks') or {}) | study.pending_codes(state)
    for key in ('noTControl', 'timingControl'):
        codes.update((((state.get('research46') or {}).get(key) or {}).get('state') or {}).get('positions') or {})
    quotes = base.fetch_tencent_quotes(sorted(codes))
    data = feeds.enrich(state, radar, quotes, base.now_cn())
    data['secondaryQuoteRefresh'] = feeds.refresh_secondary(radar, sorted(codes), base.now_cn())
    result = {'schemaVersion': 1, 'updatedAt': base.iso(), 'data': data, 'radar': radar}
    base.write_json(base.ROOT / 'astock_selection_evidence/latest.json', result)
    base.write_json(base.RADAR, radar)
    print(json.dumps({'state': 'evidence-ready', 'updatedAt': result['updatedAt'], 'symbols': len(codes)}))


if __name__ == '__main__':
    collect()
