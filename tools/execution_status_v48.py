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
    # Missing optional evidence is deliberately not a rejection.  Keep the
    # published execution summary tri-state as well, otherwise the Android
    # client can show an old all-blocked reason even though the engine has
    # already classified the same candidate as a degraded small entry.
    rejected = [x for x in candidates if x.get('rejections')]
    degraded = [x for x in candidates if not x.get('rejections') and x.get('missingOptionalEvidence')]
    filled = [x for x in candidates if x.get('executionStatus') in ('FILLED', 'PARTIAL_WAIT')]
    ranked = [x for x in candidates if x.get('entryPolicy') == 'RANKED_STAGED_ENTRY' and not x.get('rejections')]
    if filled: code='ENTRY_FILLED'; text=f'本轮已模拟买入{len(filled)}只；部分成交余量按仓位和容量继续分批处理'
    elif pending: code='PENDING_EXECUTION'; text='已有退出信号；'+'；'.join(pending_reasons[:3])
    elif reasons: code='BLOCKED_EVIDENCE_OR_RISK'; text='本轮未成交；'+'；'.join(reasons)
    elif candidates and len(rejected)==len(candidates): code='ENTRY_CONDITIONS_NOT_MET'; text='本轮无退出成交；全部候选均有明确不支持买入的证据'
    elif ranked:
        code='RANKED_ENTRY_WAITING'
        blocks = list(dict.fromkeys(x.get('executionReasonZh') or
                      (x.get('decisionPlan') or {}).get('actionZh') or x.get('executionStatus') or '等待下一次执行检查' for x in ranked))
        text=f'{len(ranked)}只候选按排名保留建仓资格；'+'；'.join(blocks[:3])
    elif degraded: code='DEGRADED_CANDIDATES_WAITING'; text=f'本轮已评估；{len(degraded)}只候选仅缺可选证据，保留降级小仓资格并等待执行条件'
    else: code='NO_FILL_AFTER_EVALUATION'; text='本轮已评估但未成交；需结合个股确认次数、交易窗口、仓位和执行限制查看'
    rotation = s.get('opportunityRotation') or {}
    plan = rotation.get('active') or {}
    if plan.get('status') and plan['status'] not in ('DONE','CANCELLED','EXPIRED'):
        code='OPPORTUNITY_ROTATION_PENDING'; text='择优换仓：'+rotation.get('statusZh',plan['status'])
    elif rotation and not pending and not reasons and code=='NO_FILL_AFTER_EVALUATION':
        text += '；择优换仓：'+rotation.get('statusZh','等待评估')
    return {'opportunityRotation': rotation, 'reasonCode':code,'reasonZh':text,'entryBlocks':reasons,'pendingExits':pending_reasons,
            'candidateCount':len(candidates),'rejectedCandidateCount':len(rejected),
            'degradedCandidateCount':len(degraded),
            'filledCandidateCount':len(filled), 'rankedCandidateCount':len(ranked),
            'candidateReasons':[{'code':x.get('code'),
                                 'reasons':x.get('rejections',[]),
                                 'missingOptionalEvidence':x.get('missingOptionalEvidence',[]),
                                 'dataConfidence':x.get('dataConfidence'),
                                 'rankingWarnings':x.get('rankingWarnings', []),
                                 'executionReasonZh':x.get('executionReasonZh') or (x.get('decisionPlan') or {}).get('actionZh'),
                                 'executionStatus':x.get('executionStatus')} for x in candidates]}
