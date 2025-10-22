import asyncio
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.services import monitor


class RunMonitoringConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_respects_concurrency_override(self) -> None:
        hosts = [SimpleNamespace(id=i, enabled=True) for i in range(5)]

        class _DummySession:
            def exec(self, _query):
                return SimpleNamespace(all=lambda: hosts)

        @contextmanager
        def _session_factory():
            yield _DummySession()

        active: int = 0
        peak: int = 0

        async def _fake_run_host_check(*_args, **_kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.01)
                return {}
            finally:
                active -= 1

        with patch.object(monitor, "get_session", _session_factory), patch.object(
            monitor, "create_host_check", lambda host_id, *_: SimpleNamespace(id=host_id)
        ), patch.object(
            monitor, "run_host_check", _fake_run_host_check
        ):
            await monitor.run_monitoring(
                SimpleNamespace(), max_concurrent_checks=2
            )

        self.assertEqual(peak, 2)
