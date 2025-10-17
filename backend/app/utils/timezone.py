from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def now_tz(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


__all__ = ["now_tz"]
