#!/usr/bin/env python3
"""本地调度器：替代 GitHub Actions 的全部定时任务。

在本地仓库根目录运行。每个 30 秒检查一次到点任务，按组互斥执行：
  1. git fetch + reset 到 origin/main（与云端保持一致，可断点续跑）
  2. 顺序执行任务内的 python 命令
  3. 按通道 commit（bot 身份）+ push

任务时间表与 .github/workflows 下的 cron 对齐（北京时间）：
  - update-slow-money-factors: 工作日 08:20/08:40/08:55/09:10/09:20/09:35（早间慢资金+premarket）
  - update-market-gateway:     交易时段 09:30-11:30 / 13:00-15:00 每 5 分钟 + 15:02/15:06/15:10/15:20/15:30 补抓
  - run-intraday-radar:        交易时段每 5 分钟 + 15:30/15:35/15:45/16:00 收盘后冻结
  - run-trade-plan:            交易时段每 5 分钟
  - run-execution-assistant:   交易时段每 5 分钟
  - run-tail-decision:         14:30-14:55 每 5 分钟 + 15:00/15:03/15:06/15:10/15:15/15:20/15:35 兜底
  - run-daily-strategy:        15:05/15:15/15:25 生成 Official 池
  - run-ai-shadow-auto:        交易时段每 5 分钟 + 15:32/15:42/15:52 收盘后结算
  - collect-astock-close:      每交易日 16:30 收盘快照

用法:
  python tools/local_scheduler.py              # 常驻调度
  python tools/local_scheduler.py --list       # 只打印下一批待执行任务
  python tools/local_scheduler.py --run-now <name>   # 立即执行指定任务
  python tools/local_scheduler.py --no-push    # 只本地生成不推送（调试用）

凭证：STOCK_API_TOKEN 从 tools/.stock_api_token 文件（单行）读取，
      找不到则降级：跳过需要该 token 的命令，走免费源兜底（与云端一致）。
"""
from __future__ import annotations

import argparse
import os
import re
from contextlib import contextmanager
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CN = timezone(timedelta(hours=8))
LOG = ROOT / "tools" / "local_scheduler.log"
TOKEN_FILE = ROOT / "tools" / ".stock_api_token"
LOCK_DIR = ROOT / "tools" / ".locks"

BOT_NAME = "astock-local-bot"
BOT_EMAIL = "local@astock.invalid"
PY = sys.executable


# ---------------------------------------------------------------- schedule
def trading_window_minutes(now_cn: datetime) -> set[int]:
    """交易时段每 5 分钟的分钟集合（周一到周五 09:30-11:30 / 13:00-15:00）。"""
    mins = set()
    if now_cn.weekday() >= 5:
        return mins
    for start, end in ((9 * 60 + 30, 11 * 60 + 30), (13 * 60, 15 * 60)):
        m = start
        while m <= end:
            mins.add(m)
            m += 5
    return mins


def due(name: str, now_cn: datetime) -> bool:
    wd = now_cn.weekday() < 5
    mm = now_cn.hour * 60 + now_cn.minute
    intraday5 = wd and mm in trading_window_minutes(now_cn)
    table = {
        # 早间慢资金 + 四项情绪 + premarket（替代 update-slow-money-factors.yml）
        "slow_money": wd and mm in (8 * 60 + 20, 8 * 60 + 40, 8 * 60 + 55, 9 * 60 + 10, 9 * 60 + 20, 9 * 60 + 35),
        # 行情网关（替代 update-market-gateway.yml）
        "gateway": intraday5 or (wd and mm in (15 * 60 + 2, 15 * 60 + 6, 15 * 60 + 10, 15 * 60 + 20, 15 * 60 + 30, 21 * 60 + 30)),
        # 盘中主线雷达（替代 run-intraday-radar.yml）
        "radar": intraday5 or (wd and mm in (15 * 60 + 30, 15 * 60 + 35, 15 * 60 + 45, 16 * 60)),
        # 交易计划（替代 run-trade-plan.yml）
        "trade_plan": intraday5,
        # 实盘执行辅助（替代 run-execution-assistant.yml）
        "execution": intraday5,
        # 尾盘决策（替代 run-tail-decision.yml）
        "tail": wd and mm in (14 * 60 + 30, 14 * 60 + 35, 14 * 60 + 40, 14 * 60 + 45, 14 * 60 + 50, 14 * 60 + 55,
                              15 * 60, 15 * 60 + 3, 15 * 60 + 6, 15 * 60 + 10, 15 * 60 + 15, 15 * 60 + 20, 15 * 60 + 35),
        # 日终 Official 池（替代 run-daily-strategy.yml）
        "daily_strategy": wd and mm in (15 * 60 + 5, 15 * 60 + 15, 15 * 60 + 25),
        # AI 影子组合（替代 run-ai-shadow-auto.yml）
        "ai_shadow": intraday5 or (wd and mm in (15 * 60 + 32, 15 * 60 + 42, 15 * 60 + 52)),
        # 收盘快照收集（替代 collect-astock-close.yml）
        "close_snapshot": wd and mm == 16 * 60 + 30,
    }
    return table.get(name, False)


TASKS: dict[str, dict] = {
    "slow_money": {
        "label": "早间慢资金 + 四项情绪 + 盘前预测池",
        "group": "slow-money",
        "channel": "factors",
        "commit_msg": "Publish slow-money factors and premarket pool (local)",
        "cmds_dynamic": True,  # 有 token 用 v2（含 jiaoch 代理），没有则用纯免费 akshare 版
        "cmds": [
            [PY, "tools/collect_slow_money_factors_v2.py"],
            [PY, "tools/publish_four_sentiment_daily.py"],
            [PY, "tools/generate_premarket_prediction.py"],
        ],
    },
    "gateway": {
        "label": "行情网关刷新",
        "group": "gateway",
        "channel": "gateway",
        "commit_msg": "Publish gateway data on arrival",
        "cmds": [
            [PY, "tools/update_market_gateway.py"],
            [PY, "tools/sanitize_market_gateway.py"],
            [PY, "tools/ensure_market_snapshot_core_indices.py"],
            [PY, "tools/publish_data_on_arrival.py", "gateway"],
        ],
    },
    "radar": {
        "label": "盘中主线雷达 + 慢资金确认 + 证据采集",
        "group": "radar-shadow",
        "channel": "radar",
        "commit_msg": "Publish radar data on arrival",
        "cmds": [
            [PY, "tools/run_intraday_radar.py"],
            [PY, "tools/enrich_slow_money_factors.py"],
            [PY, "tools/collect_selection_evidence_v51.py"],
            [PY, "tools/publish_data_on_arrival.py", "radar"],
        ],
    },
    "trade_plan": {
        "label": "正式池实时交易计划",
        "group": "trade-plan",
        "channel": "trade-plan",
        "commit_msg": "Publish trade-plan data on arrival",
        "cmds": [
            [PY, "tools/run_trade_plan_resilient.py"],
            [PY, "tools/augment_trade_plan_market_setups.py"],
            [PY, "tools/publish_data_on_arrival.py", "trade-plan"],
        ],
    },
    "execution": {
        "label": "实盘执行辅助",
        "group": "execution",
        "channel": "execution",
        "commit_msg": "Publish execution data on arrival",
        "cmds": [
            [PY, "tools/update_trade_execution_signals_strict.py"],
            [PY, "tools/publish_data_on_arrival.py", "execution"],
        ],
    },
    "tail": {
        "label": "尾盘滚动决策",
        "group": "tail",
        "channel": "tail",
        "commit_msg": "Publish tail data on arrival",
        "cmds": [
            [PY, "tools/run_tail_rolling_reliable.py"],
            [PY, "tools/publish_data_on_arrival.py", "tail"],
        ],
    },
    "daily_strategy": {
        "label": "日终 Official 正式池",
        "group": "daily-strategy",
        "channel": "official",
        "commit_msg": "Publish official cohort data on arrival",
        "cmds": [
            [PY, "tools/ensure_daily_close_snapshot.py"],
            [PY, "tools/run_daily_strategy_resilient_bse.py"],
            [PY, "tools/augment_pairwise_pools.py"],
            [PY, "tools/publish_data_on_arrival.py", "official"],
        ],
    },
    "ai_shadow": {
        "label": "AI 影子组合",
        "group": "radar-shadow",
        "channel": "portfolio",
        "commit_msg": "Publish portfolio data on arrival",
        "cmds": [
            [PY, "tools/run_ai_shadow_portfolio_flexible.py"],
            [PY, "tools/publish_data_on_arrival.py", "portfolio"],
        ],
    },
    "close_snapshot": {
        "label": "收盘快照收集",
        "group": "gateway",
        "channel": None,
        "commit_msg": "Collect A-share close snapshot",
        "cmds": [[PY, "tools/update_market_gateway.py"]],
    },
}


# ---------------------------------------------------------------- git
def git(*args: str, ok_fail=False) -> subprocess.CalledProcess:
    return subprocess.run(["git", *args], cwd=ROOT, check=not ok_fail,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def sync_from_remote() -> bool:
    """拉取云端最新状态并对齐本地工作区（与 Actions 每次 checkout 等价）。"""
    try:
        git("fetch", "origin", "main")
        git("reset", "--hard", "origin/main")
        return True
    except subprocess.CalledProcessError:
        log("WARN: git 同步失败，使用本地现状继续")
        return False


def push_changes(task: dict) -> bool:
    st = git("status", "--porcelain")
    changed = [l for l in st.stdout.splitlines() if l.strip()]
    if not changed:
        return False
    git("config", "user.name", BOT_NAME)
    git("config", "user.email", BOT_EMAIL)
    git("add", "-A")
    git("commit", "-m", task["commit_msg"])
    for attempt in range(1, 4):
        r = git("push", "origin", "HEAD:main", ok_fail=True)
        if r.returncode == 0:
            return True
        time.sleep(attempt * 2)
        git("pull", "--rebase", "origin", "main", ok_fail=True)
    log("ERROR: push 三次失败")
    return False


# ---------------------------------------------------------------- run
def env_with_token() -> dict:
    env = dict(os.environ)
    if TOKEN_FILE.exists():
        tok = re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,128}(?![0-9a-fA-F])",
                         TOKEN_FILE.read_text(encoding="utf-8").strip())
        if tok:
            env["STOCK_API_TOKEN"] = max(tok, key=len)
        env["STOCK_API_URL"] = "https://jiaoch.top/"
    return env


def effective_cmds(task: dict) -> list:
    cmds = [c for c in task["cmds"]]
    if task.get("cmds_dynamic"):
        # 没有配置 jiaoch 代理 token 时，改用纯免费 akshare 通道
        has_token = TOKEN_FILE.exists() and re.findall(
            r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,128}(?![0-9a-fA-F])",
            TOKEN_FILE.read_text(encoding="utf-8").strip())
        if not has_token:
            cmds[0] = [PY, "tools/collect_slow_money_factors.py"]
    return cmds


def run_task(name: str, push: bool = True) -> int:
    task = TASKS[name]
    log(f"=== [{name}] {task['label']} 开始")
    with lock(task["group"]):
        sync_from_remote()
        rc = 0
        for cmd in effective_cmds(task):
            step = subprocess.run(cmd, cwd=ROOT, env=env_with_token(),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
            out = (step.stdout or "").strip()
            err = (step.stderr or "").strip().splitlines()
            tail = (out[-400:] if out else "") + ((" | " + err[-1]) if err else "")
            log(f"  [{'OK' if step.returncode == 0 else 'FAIL'}] {' '.join(cmd[1:])} {tail}")
            if step.returncode != 0:
                rc = step.returncode
                break
        if rc == 0 and push and not os.environ.get("LOCAL_SCHED_NO_PUSH"):
            pushed = push_changes(task)
            log(f"  [push] {'OK' if pushed else 'no-change/fail'}")
    log(f"=== [{name}] 结束 rc={rc}")
    return rc


@contextmanager
def lock(group: str):
    """同组任务互斥（对齐 workflow concurrency group，cancel-in-progress: false）。"""
    LOCK_DIR.mkdir(exist_ok=True)
    f = LOCK_DIR / f"{group}.lock"
    for _ in range(120):
        try:
            fh = open(f, "x")
            fh.write(str(os.getpid()))
            fh.close()
            break
        except FileExistsError:
            time.sleep(5)
    else:
        raise SystemExit(f"锁 {group} 占用超过 10 分钟，放弃本轮")
    try:
        yield
    finally:
        try:
            f.unlink()
        except FileNotFoundError:
            pass


def log(msg: str) -> None:
    line = f"[{datetime.now(CN).isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    LOG.open("a", encoding="utf-8").write(line + "\n")


def now_cn() -> datetime:
    return datetime.now(CN)


def list_due() -> None:
    now = now_cn()
    print(f"当前时间 {now.isoformat(timespec='minutes')}（北京时间）")
    for name in TASKS:
        mark = "待执行" if due(name, now) else "-"
        print(f"  [{mark}] {name:14s} {TASKS[name]['label']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出当前到点任务")
    ap.add_argument("--run-now", metavar="NAME", help="立即执行指定任务")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    if args.list:
        list_due()
        return 0
    if args.run_now:
        if args.run_now not in TASKS:
            raise SystemExit(f"未知任务 {args.run_now}，可选: {', '.join(TASKS)}")
        return run_task(args.run_now, push=not args.no_push)

    log("本地调度器启动")
    fired: dict[str, datetime] = {}
    while True:
        now = now_cn()
        for name in TASKS:
            if due(name, now) and fired.get(name, datetime.min) < now.replace(second=0, microsecond=0):
                fired[name] = now
                run_task(name, push=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
