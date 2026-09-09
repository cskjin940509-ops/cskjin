"""Original handwritten hierarchy and research-only sentiment candidates.

No candidate score is a verified replica or permission to change positions.
Evidence reference: production feasibility report 2026-09-01, pages 3, 5, 6.
"""
import math
from datetime import datetime

WINDOWS = [1, 3, 5, 7, 10, 20, 30, 60, 120, 250]


def sentiment_candidate(rows, kind, as_of, universe):
    """Require 485 unique, comparable, point-in-time observations; never pad.

Rows: dataDate, availableAt (timezone required), source, universe, verified,
plus up/down or financingBalance/previousFinancingBalance. Caller must supply
actual trading observations; this function does not invent a calendar/history.
"""
    if kind not in ('profit', 'margin'):
        raise ValueError('Only documented profit/margin candidates are supported')
    now = datetime.fromisoformat(as_of)
    if now.tzinfo is None:
        raise ValueError('as_of requires timezone')
    observations = {}
    for row in rows:
        try:
            available = datetime.fromisoformat(row['availableAt'])
            day = datetime.strptime(row['dataDate'], '%Y-%m-%d').date()
            if (available.tzinfo is None or available > now or day > available.date()
                    or row.get('verified') is not True or not row.get('source')
                    or row.get('universe') != universe):
                continue
            if kind == 'profit':
                up, down = float(row['up']), float(row['down'])
                if min(up, down) < 0 or up + down < 2000:
                    continue
                value = math.log((up + .5) / (down + .5))
            else:
                current, previous = float(row['financingBalance']), float(row['previousFinancingBalance'])
                if min(current, previous) < 0:
                    continue
                value = current - previous
            if not math.isfinite(value):
                continue
            # Conflicting duplicates cannot silently alter a historical observation.
            if day in observations and observations[day] != value:
                return dict(status='CONFLICTING_OBSERVATIONS', score=None, productionEligible=False)
            observations[day] = value
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    values = [observations[d] for d in sorted(observations)][-485:]
    result = dict(status='INSUFFICIENT_HISTORY', score=None, observations=len(values),
                  requiredObservations=485, productionEligible=False,
                  formulaVersion='research-candidate-20260901', universe=universe)
    if len(values) == 485:
        target = values[-1]
        less = sum(v < target for v in values)
        equal = sum(v == target for v in values)
        result.update(status='RESEARCH_CANDIDATE', score=100 * (less + (equal - 1) / 2) / 484,
                      dataDate=max(observations).isoformat())
    return result


def alignment_report():
    """Explicit implementation boundary; no data or validation is presumed ready."""
    return {
        'source': 'handwritten-42489.jpg',
        'topLevel': [
            {'id': 'market', 'labelZh': '大盘', 'outputZh': '仓位',
             'inputsZh': ['市场情绪', '宽基ETF', '两融', '美股', '美债30年', '国债10年']},
            {'id': 'sector', 'labelZh': '板块', 'outputZh': '趋势', 'obeys': 'market',
             'inputsZh': ['板块ETF', '板块两融']},
            {'id': 'stock', 'labelZh': '选股', 'outputZh': '涨跌与买卖点', 'obeys': 'sector',
             'inputsZh': ['成交量']}],
        'execution': {'origin': 'LATER_SEPARATION_OF_BUY_SELL_RULES',
                      'priorityZh': '风险与主策略买卖优先；做T仅辅助降成本'},
        'marketSentiment': {
            'referenceReplication': 'NOT_VERIFIED',
            'activeRiskModel': 'INDEX_CHANGE_AND_BREADTH_PROXY',
            'activeRiskModelLabelZh': '临时市场强弱风控（非原综合情绪指数）',
            'profitAndMargin': 'RESEARCH_CANDIDATE_IMPLEMENTED_NOT_CONNECTED',
            'etfReference': 'OUT_OF_SAMPLE_VALIDATION_FAILED_IN_RESEARCH_REPORT',
            'aggregateReference': 'VERSION_WEIGHTS_UNRESOLVED',
            'sentimentToPosition': 'NOT_VALIDATED'},
        'research': {'windowsTradingDays': WINDOWS,
                     'leadLag': 'NOT_FULLY_VALIDATED',
                     'historicalLevel3Membership': 'NOT_FULLY_VERIFIED'},
        'complete': False,
    }
