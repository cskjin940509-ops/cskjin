from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V33PersonalAi.kt')
s = p.read_text(encoding='utf-8')

old = 'val a = data?.optJSONArray("targetPortfolio") ?: return emptyList()'
new = '''val rawTarget = data?.opt("targetPortfolio")
    val a = when (rawTarget) {
        is JSONArray -> rawTarget
        is JSONObject -> rawTarget.optJSONArray("members")
        else -> null
    } ?: return emptyList()'''
if old not in s and 'val rawTarget = data?.opt("targetPortfolio")' not in s:
    raise SystemExit('v3.3 targetPortfolio parsing anchor missing')
s = s.replace(old, new, 1)

old = 'd33(data,"targetGrossPct")?:0.0'
new = 'd33(data,"targetGrossPct") ?: d33(data?.optJSONObject("targetPortfolio"),"grossTargetPct") ?: 0.0'
if old not in s and 'optJSONObject("targetPortfolio"),"grossTargetPct"' not in s:
    raise SystemExit('v3.3 target gross anchor missing')
s = s.replace(old, new, 1)

old = 'state=applyCapital33(state,v);PersonalStore33.save(ctx,state);status=if(trading33())"资金已调整，本轮将自动再平衡" else "资金已调整，下个交易时段自动再平衡"'
new = 'state=applyCapital33(state,v); if(trading33()) state=rebalance33(ctx,state,data); PersonalStore33.save(ctx,state); status=if(trading33())"资金已调整，并已按当前实时目标立即再平衡" else "资金已调整，下个交易时段自动再平衡"'
if old not in s and new not in s:
    raise SystemExit('v3.3 capital apply anchor missing')
s = s.replace(old, new, 1)

s = s.replace(
    'Text("本金可调 · 每30秒读取最新模型目标 · 自动买入/加仓/减仓/卖出 · 本机模拟账本",color=P33Muted,fontSize=9.sp)',
    'Text("本金可调 · 持股数不设上限 · 允许满仓 · 按实时目标自动买入/加仓/减仓/卖出",color=P33Muted,fontSize=9.sp)',
    1
)

p.write_text(s, encoding='utf-8')
assert 'val rawTarget = data?.opt("targetPortfolio")' in s
assert '并已按当前实时目标立即再平衡' in s
print('v3.3 dynamic target schema compatibility fixed')
