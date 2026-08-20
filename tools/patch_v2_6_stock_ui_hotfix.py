from pathlib import Path
root=Path('app/src/main/java/com/rui/astockstrategy/v6')
detail=root/'DetailScreens.kt'
ds=detail.read_text(encoding='utf-8')
if not (root/'V26StockTrading.kt').exists(): raise SystemExit('V26StockTrading.kt missing')
if 'StockTradingPanel26(' not in ds:
    fn=ds.find('fun StockDetailScreen(')
    if fn<0: raise SystemExit('StockDetailScreen missing')
    marker='        item { DetailBackHeader("个股详情",'
    pos=ds.find(marker,fn)
    if pos<0: raise SystemExit('stock detail header marker missing')
    line_end=ds.find('\n',pos)
    if line_end<0: raise SystemExit('stock detail header line incomplete')
    block='''
        item {
            StockTradingPanel26(
                code = code,
                name = name,
                fallbackPrice = null,
                sourceDate = date,
                poolLabels = pools,
                signal = null
            )
        }'''
    ds=ds[:line_end]+block+ds[line_end:]
ds=ds.replace('Daily Cohort','每日冻结批次').replace('· 点开详情','· 点开查看并交易')
detail.write_text(ds,encoding='utf-8')
radar=root/'V25RadarTracking.kt'
if radar.exists():
    rs=radar.read_text(encoding='utf-8')
    if 'import androidx.compose.foundation.clickable' not in rs: rs=rs.replace('import androidx.compose.foundation.background\n','import androidx.compose.foundation.background\nimport androidx.compose.foundation.clickable\n',1)
    rs=rs.replace('从开盘滚动识别 Emerging → Confirming，不等涨完才筛','从开盘滚动识别潜在形成 → 确认中，不等涨完才筛')
    rs=rs.replace('Mini25("MFE",','Mini25("最大有利涨幅",').replace('Mini25("MAE",','Mini25("最大不利跌幅",')
    rs=rs.replace('Text("固定成员组合NAV",','Text("固定成员组合净值",').replace('Mini25("今日NAV",','Mini25("今日组合",').replace('Mini25("累计NAV",','Mini25("累计组合",')
    old='''                    radar!!.early.take(4).forEach { s ->
                        Row(Modifier.fillMaxWidth()) {'''
    new='''                    radar!!.early.take(4).forEach { s ->
                        Row(Modifier.fillMaxWidth().clickable { DetailNav.openStock(s.code, null) }) {'''
    if old in rs: rs=rs.replace(old,new,1)
    rs=rs.replace('· 追高${chaseZh25(s.chase)}','· 追高风险${chaseZh25(s.chase)} · 点开查看并交易')
    radar.write_text(rs,encoding='utf-8')
journal=root/'TradeJournal.kt'
js=journal.read_text(encoding='utf-8')
js=js.replace('Text("我的交易日志"','Text("我的持仓与交易"').replace('Text("本地保存 · 覆盖升级不丢 · 可导出备份"','Text("持仓收益 · 成本 · 可卖数量 · 成交记录均保存在本机"')
js=js.replace('Button(onClick = { showAdd = true }) { Text("记一笔", fontSize = 10.sp) }','OutlinedButton(onClick = { showAdd = true }) { Text("补录成交", fontSize = 10.sp) }')
js=js.replace('item { Text("当前持仓", fontWeight = FontWeight.Bold) }','item { Text("当前持仓与收益", fontWeight = FontWeight.Bold) }').replace('item { Text("成交与收益记录", fontWeight = FontWeight.Bold) }','item { Text("历史成交与已实现收益", fontWeight = FontWeight.Bold) }')
journal.write_text(js,encoding='utf-8')
v6=root/'V6Activity.kt'; vs=v6.read_text(encoding='utf-8').replace('TRADES("交易", Icons.Default.ViewList)','TRADES("持仓", Icons.Default.ViewList)').replace('点开详情','点开查看并交易'); v6.write_text(vs,encoding='utf-8')
g=Path('app/build.gradle.kts'); gs=g.read_text(encoding='utf-8').replace('versionCode = 27','versionCode = 28').replace('versionName = "2.5.0"','versionName = "2.6.0"'); g.write_text(gs,encoding='utf-8')
assert 'StockTradingPanel26(' in detail.read_text(encoding='utf-8')
assert 'versionName = "2.6.0"' in g.read_text(encoding='utf-8')
print('v2.6 stock UI integration hotfix applied')