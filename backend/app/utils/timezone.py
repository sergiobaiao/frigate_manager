from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from zoneinfo import ZoneInfo


def now_tz(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def to_timezone(value: Optional[datetime], tz: ZoneInfo) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.astimezone(tz)


__all__ = ["now_tz", "to_timezone"]
