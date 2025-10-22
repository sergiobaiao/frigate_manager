from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import ConfigManager
from ..services.monitor import run_monitoring


class MonitorScheduler:
    def __init__(self, manager: ConfigManager) -> None:
        self.manager = manager
        self.scheduler = AsyncIOScheduler(timezone=manager.timezone)

    def start(self) -> None:
        interval = self.manager.get().check_interval_minutes
        self.scheduler.add_job(
            self._run_monitoring,
            "interval",
            minutes=interval,
            id="monitoring_job",
            replace_existing=True,
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
