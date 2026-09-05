"""Start close-based tracking when final evidence exists, with legacy fallback."""
from datetime import datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from ensure_daily_close_snapshot import CORE, hhmmss, readiness

ROOT = Path(__file__).resolve().parents[1]


def ready(now: datetime, root: Path = ROOT) -> bool:
    now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5 or now.time() < time(15):
        return False
    # Preserve the old fallback for providers whose close evidence arrives late.
    if now.time() >= time(15, 20):
        return True
    day = now.date().isoformat()
    try:
        data = json.loads((root / "astock_gateway/history" / f"{day}.json").read_text())
        frozen = data.get("closeFreeze") or {}
        indices = (data.get("marketSnapshot") or {}).get("indices") or {}
        # Earlier execution needs stronger evidence than the old 14:59 freeze:
        # four final (15:00 or later) core-index timestamps, plus same-day audit.
        closes = sum((hhmmss((indices.get(k) or {}).get("quoteTime")) or 0) >= 150000 for k in CORE)
        return (frozen.get("state") == "ready" and frozen.get("date") == day
                and readiness(data, day)[0] and closes >= 4)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


if __name__ == "__main__":
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    print("run=" + ("true" if ready(now) else "false"))
    print("china_time=" + now.isoformat(timespec="seconds"))
