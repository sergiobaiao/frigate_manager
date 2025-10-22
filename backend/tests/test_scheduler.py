import asyncio
import os
import unittest
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch

from backend.app.tasks.scheduler import MonitorScheduler


class _DummyConfigManager:
    timezone = ZoneInfo("UTC")

    def get(self):
        return SimpleNamespace(check_interval_minutes=5)


class MonitorSchedulerMaxInstancesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = _DummyConfigManager()

    def test_defaults_to_one_when_variable_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            scheduler = MonitorScheduler(self.manager)
            self.assertEqual(scheduler.max_instances, 1)

    def test_reads_monitor_specific_environment_variable(self) -> None:
        with patch.dict(os.environ, {"MONITOR_MAX_INSTANCES": "5"}, clear=True):
            scheduler = MonitorScheduler(self.manager)
            self.assertEqual(scheduler.max_instances, 5)

    def test_falls_back_to_legacy_variable_name(self) -> None:
        with patch.dict(os.environ, {"MAX_INSTANCES": "3"}, clear=True):
            scheduler = MonitorScheduler(self.manager)
            self.assertEqual(scheduler.max_instances, 3)

    def test_monitor_variable_takes_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {"MONITOR_MAX_INSTANCES": "7", "MAX_INSTANCES": "4"},
            clear=True,
        ):
            scheduler = MonitorScheduler(self.manager)
            self.assertEqual(scheduler.max_instances, 7)

    def test_invalid_values_default_to_one(self) -> None:
        with patch.dict(os.environ, {"MONITOR_MAX_INSTANCES": "invalid"}, clear=True):
            scheduler = MonitorScheduler(self.manager)
            self.assertEqual(scheduler.max_instances, 1)

    def test_passes_concurrency_limit_to_monitoring(self) -> None:
        async def _run(scheduler: MonitorScheduler) -> None:
            await scheduler._run_monitoring()

        with patch.dict(os.environ, {"MONITOR_MAX_INSTANCES": "4"}, clear=True):
            scheduler = MonitorScheduler(self.manager)
            with patch(
                "backend.app.tasks.scheduler.run_monitoring",
                new_callable=AsyncMock,
            ) as mock_monitor:
                asyncio.run(_run(scheduler))
        mock_monitor.assert_awaited_once_with(
            self.manager, max_concurrent_checks=4
        )


if __name__ == "__main__":
    unittest.main()
