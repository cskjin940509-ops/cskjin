#!/usr/bin/env python3
from datetime import datetime, time as dtime
import json
import os

import update_trade_execution_signals as engine


def main():
    now = datetime.now(engine.CN)
    dry = os.getenv("DRY_RUN", "0") == "1"
    allow_any = os.getenv("ALLOW_ANY_TIME", "0") == "1" or dry
    t = now.time()
    active = (dtime(9, 30) <= t <= dtime(11, 30)) or (dtime(13, 0) <= t <= dtime(15, 5))
    if not allow_any and not active:
        print(json.dumps({
            "state": "skip",
            "reason": "outside-strict-execution-window",
            "time": now.isoformat(timespec="seconds"),
        }, ensure_ascii=False))
        return
    engine.main()


if __name__ == "__main__":
    main()
