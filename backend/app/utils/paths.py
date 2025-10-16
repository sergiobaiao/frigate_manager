from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
CONFIG_PATH = DATA_DIR / "config" / "config.json"
DB_PATH = DATA_DIR / "monitor.db"
LOG_DIR = DATA_DIR / "logs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"

__all__ = ["DATA_DIR", "CONFIG_PATH", "DB_PATH", "LOG_DIR", "SCREENSHOT_DIR"]
