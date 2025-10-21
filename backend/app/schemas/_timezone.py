from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Optional

from ..config import ConfigManager
from ..utils.timezone import to_timezone


@lru_cache()
def _config_timezone():
    return ConfigManager().timezone


def apply_config_timezone(value: Optional[datetime]) -> Optional[datetime]:
    return to_timezone(value, _config_timezone())


__all__ = ["apply_config_timezone"]
