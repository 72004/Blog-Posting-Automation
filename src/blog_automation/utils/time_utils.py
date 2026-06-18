from __future__ import annotations

from datetime import datetime, timedelta, timezone

PAKISTAN_TZ = timezone(timedelta(hours=5))


def pakistan_now_iso() -> str:
    return datetime.now(PAKISTAN_TZ).isoformat()
