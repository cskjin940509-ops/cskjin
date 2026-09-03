# A股分层研究 v4.2 数据架构

## 运行边界

- GitHub Actions 是当前生产计算后端。交易日按计划抓取行情、两融、ETF和跟踪数据，计算板块状态、候选股票、交易计划、尾盘判断及2000万元自动模拟影子组合。
- `astock_gateway`、`astock_radar`、`astock_snapshots` 等目录是版本化云端数据存储。APK不写入这些结果，也不会因打开软件而生成新的策略结果。
- APK优先读取云端已计算快照。每次成功响应都写入本机 SQLite `astock_backend_cache.db`；云端短暂失败时读取最后一次成功数据并明确标记“本地缓存”。
- 腾讯、东方财富手机直连只用于补齐用户自定义股票，或云端与SQLite同时不可用时的展示降级。直连结果不得触发正式股票池、状态机或历史绩效计算。

## 主要接口

| 数据 | 云端路径 | 生产频率 |
|---|---|---|
| 行情与板块网关 | `astock_gateway/latest.json` | 交易时段约5分钟 |
| 潜在主线雷达 | `astock_radar/latest.json` | 交易时段滚动 |
| 正式冻结与历史 | `astock_snapshots/index.json` | 收盘冻结及后续跟踪 |
| 交易计划 | `astock_trade/latest.json` | 交易时段滚动 |
| 执行辅助 | `astock_execution/latest.json` | 交易时段约5分钟 |
| 尾盘判断 | `astock_tail/latest.json` | 14:30–15:00滚动并最终冻结 |
| 影子组合 | `astock_ai_portfolio/latest.json` | 云端约5分钟自动检查 |
| 自动运行心跳 | `astock_ai_portfolio/automation.json` | 每轮后台任务落盘 |
| 完整成交账本 | `astock_ai_portfolio/ledger.json` | 仅发生模拟成交时追加 |
| 决策周期审计 | `astock_ai_portfolio/cycle_log.json` | 区分成交、无动作和数据阻断 |
| 两融/ETF慢资金 | `astock_factors/latest.json` | 开盘前及兜底任务 |
| 历史研究 | `astock_history/latest.json` | 收盘后更新 |

## 失败处理

1. 请求主云端地址，校验HTTP状态、24MB上限和JSON格式。
2. 主地址失败后请求独立GitHub下载路径。
3. 两条云端路径都失败时读取SQLite最后成功版本。
4. 云端与缓存均不存在时显示具体错误，不停留在无限加载状态。
5. `tools/verify_backend_contract.py` 在APK构建前检查全部生产数据契约。

## 尚未等同于关系型数据库

当前生产存储是Git版本化JSON，计算由云端定时任务完成，APK关闭时仍持续运行；手机SQLite只保存最后一次成功读取的缓存。它适合个人只读APK和可审计时间序列，但不是关系型数据库。若要多用户写入、复杂SQL查询或更高刷新频率，应将同一接口契约迁移至 PostgreSQL/Supabase、Cloudflare D1 或其他托管数据库；APK的数据访问层无需重写页面逻辑。
