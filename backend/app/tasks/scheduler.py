from __future__ import annotations

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import ConfigManager
from ..services.monitor import run_monitoring


logger = logging.getLogger(__name__)


class MonitorScheduler:
    def __init__(self, manager: ConfigManager) -> None:
        self.manager = manager
        self.max_instances = self._load_max_instances()
        self.scheduler = AsyncIOScheduler(timezone=manager.timezone)

    def start(self) -> None:
        interval = self.manager.get().check_interval_minutes
        self.scheduler.add_job(
            self._run_monitoring,
            "interval",
            minutes=interval,
            id="monitoring_job",
            replace_existing=True,
            max_instances=self.max_instances,
        )
        if not self.scheduler.running:
            self.scheduler.start()

    def reload(self) -> None:
        if self.scheduler.get_job("monitoring_job"):
            self.scheduler.remove_job("monitoring_job")
        self.start()

    async def _run_monitoring(self) -> None:
        await run_monitoring(self.manager)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()

    def _load_max_instances(self) -> int:
        raw_value = os.getenv("MONITOR_MAX_INSTANCES")
        if raw_value is None:
            return 1
        try:
            parsed = int(raw_value)
        except ValueError:
            logger.warning(
                "Invalid MONITOR_MAX_INSTANCES value '%s'; defaulting to 1.", raw_value
            )
            return 1
        if parsed < 1:
            logger.warning(
                "MONITOR_MAX_INSTANCES must be at least 1; defaulting to 1 (got %s).",
                parsed,
            )
            return 1
        return parsed
