"""Forward-only evidence: frozen opportunity cohorts and decision explanations.

Observed price returns are diagnostics, not executable/total returns. No tuning,
production promotion, synthetic historical freezes or changes to the live ledger.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from datetime import time
import selection_rules_v45 as rules

VERSION = 'v4.6-forward-evidence'
PROTOCOL = {
    'version': VERSION, 'ruleVersion': rules.VERSION, 'parameters': deepcopy(rules.PARAMETERS),
    'sourceHashes': {name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                     for name in ('selection_rules_v45.py', 'selection_engine_v45.py', 'selection_data_v45.py', 'selection_research_v46.py')},
    'primaryHorizon': 10, 'exploratoryHorizons': [5, 20],
    'minimumSignalDatesForReview': 60,
    'selectionBenchmark': '当时完整板块成员等权；B0基线按当时涨幅前20%等权',
    'returnDefinition': '原始价格观察收益；未扣交易成本及除权分红，不代表可成交收益',
    'stageOrder': ['SELECTION', 'ENTRY_EXIT', 'T_INCREMENT'],
    'timingBenchmark': '相同候选筛选与执行风控；取消回踩买点及阻力空间过滤，首次可行窗口建仓，持仓起始日起满10个完整交易日退出；保留硬止损和组合风险。',
    'noteZh': '固定10日主检验、5/20日辅助观察；60个信号日仅是复核门槛，不是盈利认证。'
}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def research(state, now):
    current_hash = digest(PROTOCOL)
    obj = state.get('research46')
    if not obj:
        obj = {'version': VERSION, 'activatedAt': now.isoformat(),
               'protocol': deepcopy(PROTOCOL), 'protocolHash': current_hash, 'cohorts': {}}
        state['research46'] = obj
    elif obj.get('protocolHash') != current_hash:
        # A strategy revision starts a new, independently measured study.  The
        # previous cohorts remain immutable in the archive, but research state
        # must never pause the production selector indefinitely.
        old_hash = str(obj.get('protocolHash') or 'unknown')
        archive = state.setdefault('research46Archive', {})
        archive.setdefault(old_hash, deepcopy(obj))
        obj = {'version': VERSION, 'activatedAt': now.isoformat(),
               'protocol': deepcopy(PROTOCOL), 'protocolHash': current_hash,
               'cohorts': {}, 'previousProtocolHash': old_hash,
               'rolloverAt': now.isoformat(),
               'rolloverReasonZh': '策略版本变化，旧样本已归档；新版研究自动开始，不影响生产筛选。'}
        state['research46'] = obj
    return obj


def pending_codes(state):
    result = set()
    for row in (state.get('research46') or {}).get('cohorts', {}).values():
        if not row.get('trackingClosed'):
            result.update(row['frozen']['members'])
    return result


def quote_price(q, now, closing=False):
    price = rules.finite(q.get('price'))
    at = rules.stamp(q.get('quoteTimestamp') or q.get('quoteTime'), now.date().isoformat())
    if not price or price <= 0 or not at or at > now or at.date() != now.date():
        return None
    if closing:
        return price if at.time() >= time(15) else None
    return price if rules.fresh(at.isoformat(), now) else None


def factor_audit(stock, today, now):
    checks = []
    for key in ('marginData', 'etfData'):
        source = stock.get(key) or {}
        # Missing publication times cannot be certified just from T+1 date lag.
        if not source:
            continue
        at = rules.stamp(source.get('availableAt'))
        day = str(source.get('dataDate') or '')
        checks.append(bool(at and at <= now and rules.stamp(day) and day < today))
    return bool(checks) and all(checks)


def freeze_candidates(state, targets, radar, quotes, now):
    obj = research(state, now); today = now.date().isoformat()
    captured = rules.stamp(radar.get('capturedAt'))
    if not captured or not rules.fresh(captured.isoformat(), now, 900) or radar.get('date') != today:
        return
    ranks = (state.get('selectionData45') or {}).get('sectorRanks') or {}
    groups = {}
    for t in targets:
        if t.get('stage') in ('EMERGING', 'CONFIRMING'):
            groups.setdefault(t['sector'], []).append(t)
    for sector, candidates in groups.items():
        key = today + ':' + sector
        if key in obj['cohorts']:
            continue  # First observation is immutable, even if the ranking later improves.
        universe = ranks.get(sector) or {}
        members = {code: rules.finite(row.get('price')) for code, row in (universe.get('rows') or {}).items()}
        at = rules.stamp(universe.get('availableAt'))
        if (not universe.get('complete') or len(members) != universe.get('total') or not at or not rules.fresh(at.isoformat(), now)
                or not members or any(not p or p <= 0 for p in members.values())):
            continue
        selected = [t for t in candidates if t['code'] in members and quote_price(quotes.get(t['code']) or {}, now)]
        if not selected:
            continue
        # Capture all early candidates, including rejected buy setups, to separate selection from timing.
        b0 = sorted(members, key=lambda c: (-rules.finite(universe['rows'][c].get('changePct'), -999), c))
        b0 = b0[:max(1, (len(b0) + 4) // 5)]
        frozen = {'signalDate': today, 'frozenAt': now.isoformat(), 'radarAt': radar['capturedAt'],
            'sector': sector, 'members': members, 'memberCount': len(members),
            'reportedMemberCount': universe.get('total'), 'b0Codes': b0,
            'candidates': deepcopy(selected), 'protocolHash': obj['protocolHash'],
            'factorTimingChecked': all(factor_audit((radar.get('stocks') or {}).get(t['code']) or {}, today, now) for t in selected)}
        obj['cohorts'][key] = {'frozen': frozen, 'freezeHash': digest(frozen), 'outcomes': {}, 'sessions': []}


def mark_cohorts(state, quotes, now):
    obj = research(state, now); today = now.date().isoformat()
    calendar = (state.get('selectionData45') or {}).get('marketSessions') or []
    for row in obj['cohorts'].values():
        frozen = row['frozen']
        row['integrityOk'] = digest(frozen) == row['freezeHash']
        if not row['integrityOk'] or row.get('trackingClosed'):
            continue
        # Persist exchange dates across the rolling daily-bar cache.
        sessions = set(row.get('sessions', [])) | {d for d in calendar if frozen['signalDate'] < d <= today}
        if now.time() >= time(15) and any(quote_price(quotes.get(c) or {}, now, True) for c in frozen['members']):
            if today > frozen['signalDate']:
                sessions.add(today)
        row['sessions'] = sorted(sessions)
        age = len(sessions)
        if age > 20:
            row['trackingClosed'] = True
            continue
        if now.time() < time(15) or today not in sessions or age not in (5, 10, 20):
            continue
        horizon = str(age)
        if horizon in row['outcomes']:
            continue
        marks = {c: quote_price(quotes.get(c) or {}, now, True) for c in frozen['members']}
        missing = [c for c, p in marks.items() if p is None]
        if missing:
            row['pendingReasonZh'] = f'{age}日评估缺少{len(missing)}只原始成员收盘价；不删除缺失成员提高成绩'
            continue
        returns = {c: (marks[c] / p - 1) * 100 for c, p in frozen['members'].items()}
        selected = [returns[t['code']] for t in frozen['candidates']]
        full = mean(returns.values()); b0 = mean(returns[c] for c in frozen['b0Codes'])
        row['outcomes'][horizon] = {'date': today, 'observedAt': now.isoformat(),
            'candidateReturnPct': mean(selected), 'sectorEqualWeightReturnPct': full,
            'b0ReturnPct': b0, 'excessVsSectorPp': mean(selected) - full,
            'excessVsB0Pp': mean(selected) - b0, 'candidateCount': len(selected),
            'marks': marks, 'returnDefinition': PROTOCOL['returnDefinition']}
        row.pop('pendingReasonZh', None)
        if age == 20:
            row['trackingClosed'] = True


def stage_summary(obj):
    grouped = {}
    for row in obj['cohorts'].values():
        point = row['outcomes'].get('10')
        if point and digest(row['frozen']) == row['freezeHash']:
            grouped.setdefault(row['frozen']['signalDate'], []).append(point)
    dates = len(grouped)
    excess = [mean(x['excessVsB0Pp'] for x in rows) for rows in grouped.values()]
    return {'id': 'SELECTION', 'titleZh': '第一步：潜力板块与个股',
        'status': 'READY_FOR_REVIEW' if dates >= PROTOCOL['minimumSignalDatesForReview'] else 'COLLECTING',
        'statusZh': '观察样本达到复核门槛' if dates >= 60 else '积累前向证据',
        'matureSignalDates': dates, 'requiredSignalDates': 60,
        'meanObservedExcessVsB0Pp': mean(excess) if excess else None,
        'reasonZh': '按信号日汇总，重叠窗口仍相关；需补除权、可成交成本、全市场基准与独立样本外验证。',
        'nextActionZh': '先验证提前候选相对当时板块及B0基线是否有增量；不因样本数够或平均收益为正自动认定有效。'}


def entry_plan(target):
    setup = target.get('setup') or {}; tech = target.get('technical') or {}
    price = rules.finite(target.get('referencePrice'))
    support = rules.finite(setup.get('support'))
    atr = rules.finite(tech.get('atr14'))
    risk_pct = rules.finite(setup.get('riskDistancePct'))
    reasons = target.get('rejections') or []
    gaps = target.get('missingOptionalEvidence') or []
    ranked = target.get('entryPolicy') == 'RANKED_STAGED_ENTRY'
    statuses = {'FILLED': '本轮已模拟买入', 'PARTIAL_WAIT': '已部分买入，余量分批执行',
                'WAIT_NEW_SNAPSHOT': '本次行情已检查，等待下一笔新行情',
                'OUTSIDE_ENTRY_SESSION': '候选已排序，等待下一有效买入时段',
                'WAIT_FRESH_QUOTE': '候选保留，等待有效行情',
                'WAIT_BUDGET_OR_LOT': '等待仓位额度或整手金额',
                'WAIT_CAPACITY_OR_LIMIT': '等待成交容量或涨跌停解除',
                'WAIT_WINDOW_OR_EXIT': '等待加仓窗口或退出处理',
                'BLOCKED_CONDITIONS_OR_RISK': '风险条件不允许买入',
                'BELOW_REBALANCE_THRESHOLD': '持仓已接近目标，暂不加仓',
                'WAIT_ROTATION_PLAN': '等待现有换仓计划处理'}
    action = '不符合买入条件' if reasons else statuses.get(target.get('executionStatus'))
    if not action:
        action = ('按排名小仓建仓' if gaps or target.get('rankingWarnings') else '按排名分批建仓') if ranked else ('降级小仓候选' if gaps else '个股条件通过，等待组合与执行许可')
    protection = rules.stop_lines({'avgCost': price}, price, tech)['hardStopPrice'] if ranked and price and price > 0 else None
    return {'actionZh': action,
        'buyZoneLow': round(support - (.6 if setup.get('kind') == 'PULLBACK_RECOVERY' else .3) * atr, 4) if support and atr else (price if ranked else None),
        'buyZoneHigh': round(support + .5 * atr, 4) if support and atr else (price if ranked else None),
        'initialProtectionPrice': protection if ranked else (round(price * (1 - risk_pct / 100), 4) if price and risk_pct else None),
        'resistanceReference': tech.get('high20') if tech.get('ready') else None,
        'thesisZh': target.get('reasonZh'), 'waitReasons': reasons,
        'dataGaps': gaps,
        'rankingWarnings': target.get('rankingWarnings', []),
        'executionReasonZh': target.get('executionReasonZh'),
        'entryPolicy': target.get('entryPolicy'),
        'referencePriceAt': target.get('dataAt'),
        'priceMeaningZh': '所列价格为候选采集时的参考；实际买入须重新检查新行情、容量和仓位，保护线按实际成交成本更新。' if ranked else None,
        'invalidationZh': '板块转弱、资金证据失效或触及保护线时重新评估；不因单纯下跌补仓。',
        'forecastZh': '相对区间研究；未验证涨跌概率，不预测绝对最低/最高点。'}


def holding_plan(pos, pending, quote_ok):
    if pending:
        action, reason = '等待执行退出', pending['reasonZh']
    elif not quote_ok:
        action, reason = '等待新行情', '报价未通过时点检查，无法确认当前持有或卖出信号'
    elif pos.get('invalidDayStreak', 0):
        action, reason = '观察转弱信号', f"连续失效{pos['invalidDayStreak']}日，按既定退出条件处理"
    else:
        action, reason = '继续持有并跟踪', '当前未触发退出；掉出候选名单只停止加仓'
    plan = pos.get('profitPlan50') or {}
    profit_text = ('主动止盈目标一 %.4f、目标二 %.4f；进入区间并确认滞涨转弱后分两档兑现；已提交档位 %s。' % (plan['target1'], plan['target2'], plan.get('queuedStages', []))) if plan else '完整日线到达后冻结主动止盈目标。'
    return {'actionZh': action, 'reasonZh': reason,
        'hardStopPrice': pos.get('hardStopPrice'), 'trailingStopPrice': pos.get('trailingStopPrice'),
        'takeProfitZh': profit_text + '趋势延续保留剩余仓位；峰值盈利15%/25%后移动保护距离上限收紧至5%/3%。',
        'tPolicyZh': '震荡才研究小比例做T；总收益须与独立无T组合对比，趋势强时保留底仓。'}


def report(state, now, comparison=None, simple_comparison=None):
    obj = research(state, now); cohorts = list(obj['cohorts'].values())
    intact = sum(digest(x['frozen']) == x['freezeHash'] for x in cohorts)
    timing = sum(x['frozen']['factorTimingChecked'] for x in cohorts)
    complete = sum(x['frozen']['memberCount'] == x['frozen'].get('reportedMemberCount') for x in cohorts)
    stage1 = stage_summary(obj)
    comparison = comparison or {'statusZh': '等待同起点对照初始化', 'closeSampleDays': 0}
    simple_comparison = simple_comparison or {}
    matched = bool(comparison.get('asOfDate') and comparison.get('asOfDate') == simple_comparison.get('asOfDate'))
    timing_comparison = {'statusZh': '积累同起点买卖规则对照',
        'closeSampleDays': min(comparison.get('closeSampleDays', 0), simple_comparison.get('closeSampleDays', 0)),
        'asOfDate': comparison.get('asOfDate') if matched else None,
        'managedReturnPct': comparison.get('withoutTReturnPct') if matched else None,
        'simpleReturnPct': simple_comparison.get('withoutTReturnPct') if matched else None,
        'incrementalReturnPp': comparison['withoutTReturnPct'] - simple_comparison['withoutTReturnPct'] if matched else None,
        'noteZh': PROTOCOL['timingBenchmark'] + '两组均关闭做T，独立现金/仓位；结果仅从启用时点开始，不代表单个参数的因果贡献。'}
    stages = [stage1,
        {'id': 'ENTRY_EXIT', 'titleZh': '第二步：买点与止盈退出', 'status': 'COLLECTING',
         'statusZh': '积累独立简单持有对照', 'matureSignalDates': timing_comparison['closeSampleDays'],
         'reasonZh': '两组均关闭做T，对比现有买卖管理与固定10日简单规则；同样计费用、滑点和成交限制。',
         'nextActionZh': '先复核选股，再检验买卖规则增益、回撤和跨行情稳定性；禁止用事后最低/最高价成交。'},
        {'id': 'T_INCREMENT', 'titleZh': '第三步：做T是否增加总收益', 'status': 'COLLECTING',
         'statusZh': comparison['statusZh'], 'matureSignalDates': comparison.get('closeSampleDays', 0),
         'reasonZh': '与同起点、独立现金和持仓、执行同样核心规则的无T组合比较；选股与买卖未验证前不推广做T。',
         'nextActionZh': '观察扣费总收益、回撤与卖飞损失；不用账面成本下降代替超额收益。'}]
    def gate(key, title, count, reason):
        status = 'CHECKED' if cohorts and count == len(cohorts) else ('PARTIAL' if count else 'MISSING')
        return {'id': key, 'titleZh': title, 'status': status, 'completed': count, 'total': len(cohorts),
                'checkedAt': now.isoformat(), 'reasonZh': reason,
                'evidencePath': 'astock_ai_portfolio/state.json#research46.cohorts'}
    return {'schemaVersion': 1, 'version': VERSION, 'updatedAt': now.isoformat(),
        'activatedAt': obj['activatedAt'], 'objectiveZh': '提前发现潜力，优化买入与退出，最后验证做T增益；以扣费超额收益和回撤衡量。',
        'productionStatusZh': '生产策略正常运行；新版研究样本独立累计，不阻断选股、仓位或模拟交易。',
        'protocol': obj['protocol'], 'protocolHash': obj['protocolHash'], 'stages': stages,
        'currentPriorityZh': '优先完成第一步的选股领先性验证；后续实验可积累，不能越级宣称有效。',
        'audits': [
            gate('coverage', '当前前向样本覆盖', complete, '仅统计本次启用后的完整成员样本；不等于2017年至今历史覆盖审计。'),
            gate('members', '当时板块成员冻结', complete, '使用首次观察时保存的成员；后续不以今天成员替换。'),
            gate('availableAt', '因子可得时间', timing, '两融/ETF必须具备真实availableAt且不晚于决策；仅写T+1不能通过。'),
            {'id': 'walkForward', 'titleZh': '滚动样本外验证', 'status': 'PENDING_REVIEW',
             'completed': stage1['matureSignalDates'], 'total': 60, 'checkedAt': now.isoformat(),
             'reasonZh': stage1['reasonZh'], 'evidencePath': 'astock_ai_portfolio/state.json#research46'},
            gate('frozen', '前向样本完整性', intact, '校验首次冻结内容哈希；仅证明未改写，不等于策略有效。')],
        'cohortCount': len(cohorts), 'tComparison': comparison, 'timingComparison': timing_comparison,
        'pendingReasons': sorted({x['pendingReasonZh'] for x in cohorts if x.get('pendingReasonZh')})[:20]}
