# astock_data — 离线数据底座

把 `E:\天翼云盘\天翼云盘下载\量化数据\alpha_rank_export`（聚宽 A 股全量 Parquet，
约 33.9 GB / 12 数据集 / 2015~2026）接入 cskjin 管线的**只读、无未来函数、
离线**数据底座。目标只有一个：让回测和因子计算不再依赖在线拉数，且数值口径可信。

## 装依赖（一次性，隔离 venv，不污染你的环境）

venv 已建好：`C:\Users\曹书恺\.workbuddy\binaries\python\envs\quantdata`
（pandas 3.0.6 + pyarrow 26.0.0）。跑本包任何命令都用这个解释器：

```bash
cd cskjin
"C:/Users/曹书恺/.workbuddy/binaries/python/envs/quantdata/Scripts/python.exe" -m astock_data.cli smoke
```

数据根路径默认指向 E 盘导出目录；换机器用环境变量覆盖：
`set ALPHA_RANK_DATA_ROOT=D:\path\to\alpha_rank_export`。

## 模块一览

| 文件 | 职责 |
|---|---|
| `config.py` | 解析数据根、数据集清单（日线 6 套 + 2020 起 4 套 + 单文件） |
| `mapping.py` | 代码互转：聚宽 `000001.XSHE` ↔ tushare `000001.SZ` ↔ 纯 6 位；指数映射表 |
| `store.py` | `ParquetStore`：`pyarrow.dataset` 按文件名裁日期、按列裁列、按 code 裁行；进程内 LRU。`get_daily/get_kline/get_index_kline/index_constituents/stock_list/industries/margin/cross_section/calendar` |
| `bridge.py` | `patch_module()` / `local_fetch_kline()`：零改动顶替 `tools/update_strategy_backtest.fetch_kline` |
| `stock_margin.py` | 个股两融明细读取（supplements/tushare `margin_detail`，含北交所 345/346 只） |

## 核心 API

```python
from astock_data import DataFoundation
df = DataFoundation()
s = df.store

s.get_kline("600000", 620, end="2026-09-30")            # 个股 K 线，喂现有回测
s.get_index_kline("000300", 620, end="2026-09-30")       # 指数 K 线（000300=沪深300）
s.get_daily(["600000","000001"], "2026-09-01","2026-09-30", adjust="qfq")  # 截面行情面板
s.cross_section("jq_valuation", "2026-09-30", columns=["code","pe_ratio","market_cap"])  # 估值截面
s.cross_section("jq_indicator", "2026-09-30")            # 财务指标截面
s.margin(["600000"], "2026-09-30")                       # 两融截面（null=当日无数据，非 0）
s.industries(["600000"], "2026-09-30")                   # 申万/聚宽/证监会行业标签
s.index_constituents("000300", "2026-09-30")             # 指数成分股（月度快照，取 ≤date 最近一期）
s.stock_list("2026-09-30")                               # 当日在市全部 A 股（含停牌）
s.calendar("2026-09-01","2026-09-30")                     # 交易日历
s.stock_margin("2026-09-30")["600000"]                    # 个股两融明细（含北交所）
```

### 个股两融明细（`stock_margin`，补 cskjin 缺口）

`supplements/tushare/margin_detail` 提供 tushare 代理补采的全市场个股两融明细
（每交易日全市场约 4454 只，含北交所 345+ 只；`jq_extra.mtss_*` 不含北交所，且
2026-09-30 / 2026-10-09 缺全部两融列，本模块正好补上这两天）：

```python
from astock_data import load_day, available_dates, day_audit
day = load_day("2026-09-30")          # {bare_code: 记录}
day["600000"]
# -> code/ts_code/exchange/balance(融资余额)/buyAmount(融资买入)/repayAmount(融资偿还)
#    netBuyExact(买入-偿还, 精确)/secLending(融券余额)/secLendingQty/total(两融合计)
day_audit("2026-09-30")               # 审计状态；CROSS_SOURCE_RECONCILED=已通过
                                       # 官方源交叉核对（SSE 官方 2000 行逐值比对，0 差异）
```

口径与 `astock_factors/latest.json` 的 margin 块（慢资金采集）对齐：6 位纯代码、
`balance`/`buyAmount`/`repayAmount`/`netBuyExact` 同义。**缺失股票不填 0**，
不在当日名单里就没有记录（无两融资格或未发布）。

### 复权口径（`get_daily` / `get_kline` 的 `adjust` 参数）

- `"hfq"`：后复权，直接读导出里的 `*_post` 列（= 未复权 × factor），最稳，跨除权不断裂。
- `"qfq"`：前复权，`价×factor ÷ 该股窗口内最后一日 factor`，末根恒等于未复权收盘，**对齐在线 qfq 行情**。默认值，`get_kline` 用它。
- `"none"`：未复权原始价。

## 口径保证（已校验）

`python -m astock_data.cli smoke` 之外，跑过一组数值自洽校验（3 只股 × 2 个月）：

1. `close_post == close × factor` 最大相对偏差 = **0**（复权数学自洽）
2. qfq 末根 = 未复权收盘，偏差 = **0**（复权方向正确）
3. 交易日收盘价全部落在当日 `[low_limit, high_limit]` 带内（**126/126**）
4. 复权因子随时间单调不降（**无未来函数**）
5. `get_kline(end=...)` 点时截取零泄漏（**future-leak = 0**）

`bridge` 层已实测：patch 后 `fetch_kline` 喂进现有 `performance_for`，
600519 相对沪深300 的 T+1~T+60 收益 / alpha / MFE / MAE / 命中率全出，benchmark 零泄漏。

## 边界与注意

- **覆盖区间**：`jq_daily/valuation/indicator/三大报表` 从 **2015-01-05** 起；
  `jq_minute/extra/index_daily/index_comp` 从 **2020-01-02** 起。更早区间查这些会拿到空表。
- `jq_minute` 是**未复权**价（每交易日每股 240 根），做日内策略时跨除权日要自己套 factor。
- 财务表是"当日已披露"快照口径，**不是**财报原始披露日，做事件研究注意这点。
- `jq_extra` 两融列：43 个交易日缺沪深港通、2026-09-30 与 10-09 缺全部 `mtss_*`（读出来是 null，**不要填 0**）。
  要这两天的个股两融（以及北交所两融），用 `stock_margin` 模块读 `margin_detail` 补充。
- `supplements/` 里另有 tushare 代理补采的两融明细（margin_detail）与 ETF 历史/份额/净值，
  可直接补 cskjin 之前"两融情绪 FORMAL"那块的数据缺口；ETF 数据需按基金属性筛选后再用。
- 代码是聚宽格式，接 tushare/在线接口时统一用 `mapping.to_tushare` 转。

## 自检

```bash
python -m astock_data.cli smoke          # 全量冒烟（含 stock_margin 明细自检）
python -m astock_data.cli kline 600000 2026-09-30
python -m astock_data.cli index 000300 2026-09-30
python -m astock_data.cli cross 2026-09-30
python -m astock_data.cli calendar 2026-09
python -m astock_data.cli recon_official 2026-09-30   # 官方 SSE 源交叉核对（需 akshare，已装进 venv）
```

## 依赖

- 最小依赖：`pandas` + `pyarrow`（已在 venv）
- 可选：`akshare`（仅 `recon_official` 交叉核对需要，已装进同一 venv）
