"""Explain evaluated outcomes without altering execution decisions."""

def explain(latest):
    s = latest.get('selection45') or {}; risk = s.get('portfolioRisk') or {}; market = s.get('market') or {}
    pending = s.get('pendingExits') or []; candidates = s.get('candidates') or []
    reasons = []
    if market.get('state') == 'UNKNOWN': reasons.append(market.get('reasonZh') or '大盘证据缺失')
    if risk.get('dailyRiskDataReady') is False: reasons.append('缺少上一交易日可靠收盘基准，禁止新增风险')
    if risk.get('paused'): reasons.append('组合风控暂停新增风险')
    if not risk.get('allowNew') and not reasons and risk: reasons.append('大盘或组合风险条件不允许新增买入')
    labels = {'WAIT_WINDOW':'等待普通交易窗口', 'WAIT_FRESH_QUOTE':'等待有效行情', 'WAIT_T_PLUS_ONE':'受T+1约束',
              'WAIT_TURNOVER':'达到当日换手限制', 'WAIT_CAPACITY_OR_LIMIT':'容量或涨跌停限制', 'PARTIAL_WAIT':'部分成交后等待余量执行', 'PENDING':'等待执行'}
    pending_reasons = [f"{x.get('code')}：{labels.get(x.get('state'), x.get('state','待执行'))}" for x in pending]
    rejected = [x for x in candidates if x.get('rejections')]
    if pending: code='PENDING_EXECUTION'; text='已有退出信号；'+'；'.join(pending_reasons[:3])
    elif reasons: code='BLOCKED_EVIDENCE_OR_RISK'; text='本轮未成交；'+'；'.join(reasons)
    elif candidates and len(rejected)==len(candidates): code='ENTRY_CONDITIONS_NOT_MET'; text='本轮无退出成交；候选买入条件未通过'
    else: code='NO_FILL_AFTER_EVALUATION'; text='本轮已评估但未成交；需结合个股确认次数、交易窗口、仓位和执行限制查看'
    return {'reasonCode':code,'reasonZh':text,'entryBlocks':reasons,'pendingExits':pending_reasons,
            'candidateCount':len(candidates),'rejectedCandidateCount':len(rejected),
            'candidateReasons':[{'code':x.get('code'),'reasons':x.get('rejections',[]), 'executionStatus':x.get('executionStatus')} for x in candidates]}
