from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import httpx
from pytz import timezone as tz_get

from .config_manager import ConfigManager
from .history_manager import HistoryManager
from .models import FailureRecord, Host, HostCreate, HostUpdate, LogLocation
from .notifier import TelegramNotifier
from .playwright_manager import PlaywrightManager
from .utils import ensure_timezone, extract_failure_start, parse_json_lines

SERVICE_ENDPOINTS = {
    "go2rtc": "/api/logs/go2rtc",
    "nginx": "/api/logs/nginx",
    "frigate": "/api/logs/frigate",
}


class MonitorService:
    def __init__(
        self,
        config: ConfigManager,
        history: HistoryManager,
        notifier: TelegramNotifier,
        data_dir: Path,
    ) -> None:
        self._config = config
        self._history = history
        self._notifier = notifier
        self._data_dir = data_dir
        self._playwright = PlaywrightManager()
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._http = httpx.AsyncClient(timeout=60)
        self._last_signatures: Dict[str, str] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        await self._playwright.close()
        await self._http.aclose()

    async def restart(self) -> None:
        await self.stop()
        self._http = httpx.AsyncClient(timeout=60)
        await self.start()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            settings = self._config.get_settings()
            hosts = [Host(**host) for host in self._config.get_hosts()]
            interval = max(1, settings.get("check_interval_minutes", 10))
            if not hosts:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval * 60)
                except asyncio.TimeoutError:
                    pass
                continue
            await self._run_cycle(settings, hosts)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval * 60)
            except asyncio.TimeoutError:
                continue

    async def _run_cycle(self, settings: Dict, hosts: List[Host]) -> None:
        tasks = [self._check_host(host, settings) for host in hosts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, FailureRecord):
                self._history.add_entry(result)
            elif isinstance(result, Exception):
                tz_name = settings.get("timezone", "America/Sao_Paulo")
                tz = tz_get(tz_name)
                entry = FailureRecord(
                    id=uuid4().hex,
                    host_id="unknown",
                    host_name="unknown",
                    timestamp=datetime.now(tz),
                    timezone=tz_name,
                    status="error",
                    failing_count=0,
                    failing_cameras=[],
                    log_locations=[],
                    notes=str(result),
                )
                self._history.add_entry(entry)

    async def _check_host(self, host: Host, settings: Dict) -> FailureRecord:
        tz_name = settings.get("timezone", "America/Sao_Paulo")
        tz = tz_get(tz_name)
        timestamp = datetime.now(tz)
        status = "ok"
        log_locations: List[Dict[str, str]] = []
        failure_started: Optional[datetime] = None
        failing_cameras: List[int] = []
        notes: Optional[str] = None

        try:
            failing_cameras = await self._find_failing_cameras(host.address)
            if len(failing_cameras) > 1:
                await asyncio.sleep(300)
                failing_cameras = await self._find_failing_cameras(host.address)
                if len(failing_cameras) > 1:
                    status = "failure"
                    log_locations, failure_started = await self._collect_logs(host, tz_name)
                    signature = f"{host.id}:{sorted(failing_cameras)}"
                    if self._last_signatures.get(host.id) != signature:
                        await self._notify_failure(host, failing_cameras, log_locations, failure_started, settings)
                        self._last_signatures[host.id] = signature
            else:
                self._last_signatures.pop(host.id, None)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            failure_started = None
            log_locations = []
            self._last_signatures.pop(host.id, None)
            notes = str(exc)

        record = FailureRecord(
            id=uuid4().hex,
            host_id=host.id,
            host_name=host.name,
            timestamp=timestamp,
            timezone=tz_name,
            status=status,
            failing_count=len(failing_cameras),
            failing_cameras=failing_cameras,
            failure_started_at=failure_started,
            log_locations=[
                LogLocation(service=item["service"], path=item["path"])
                for item in log_locations
            ] if log_locations else [],
            notes=notes,
        )
        return record

    async def _find_failing_cameras(self, base_url: str) -> List[int]:
        context, page = await self._playwright.open_page()
        failing_indices: List[int] = []
        try:
            await page.goto(base_url, wait_until="networkidle", timeout=60000)
            cards = await page.evaluate(
                """
                () => {
                    const failureText = "No frames have been received, check error logs";
                    const allCards = Array.from(document.querySelectorAll('[data-camera-id], .camera-card, .camera, .card'));
                    if (allCards.length === 0) {
                        return Array.from(document.body.querySelectorAll('*'))
                            .filter(el => el.textContent && el.textContent.includes(failureText))
                            .map((el, index) => ({ index, label: '', text: el.textContent }));
                    }
                    return allCards.map((node, index) => ({
                        index,
                        label: node.getAttribute('data-camera-id') || node.getAttribute('data-camera') || node.id || '',
                        text: node.textContent || ''
                    }));
                }
                """
            )
            cards = cards or []
            failing_indices = [
                idx + 1
                for idx, card in enumerate(cards)
                if "No frames have been received, check error logs" in (card.get("text") or "")
            ]
        finally:
            await context.close()
        return failing_indices

    async def _collect_logs(self, host: Host, tz_name: str) -> tuple[List[Dict[str, str]], Optional[datetime]]:
        tz = tz_get(tz_name)
        timestamp = datetime.now(tz)
        base_url = host.address.rstrip("/")
        log_entries: List[Dict[str, str]] = []
        candidate_times: List[datetime] = []
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", host.name)

        for service, endpoint in SERVICE_ENDPOINTS.items():
            url = f"{base_url}{endpoint}"
            try:
                response = await self._http.get(url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            text = response.text
            logs_dir = self._data_dir / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            file_path = logs_dir / f"{safe_name}-{service}.log"
            with file_path.open("a", encoding="utf-8") as fh:
                fh.write(f"\n# --- snapshot {timestamp.isoformat()} ---\n")
                fh.write(text)
                fh.write("\n")
            log_entries.append({"service": service, "path": str(file_path)})
            records = parse_json_lines(text)
            failure_start = extract_failure_start(records)
            if failure_start:
                candidate_times.append(failure_start)

        failure_started = min(candidate_times) if candidate_times else None
        if failure_started:
            failure_started = ensure_timezone(failure_started, tz_name)
        return log_entries, failure_started

    async def _notify_failure(
        self,
        host: Host,
        failing_cameras: List[int],
        log_locations: List[Dict[str, str]],
        failure_started: Optional[datetime],
        settings: Dict,
    ) -> None:
        tz_name = settings.get("timezone", "America/Sao_Paulo")
        tz = tz_get(tz_name)
        now = datetime.now(tz)
        bot_token = settings.get("telegram_bot_token")
        chat_id = settings.get("telegram_chat_id")
        mention_ids = settings.get("mention_user_ids", [])
        mention_name = settings.get("mention_name", "")
        mentions = ""
        if mention_ids and mention_name:
            mentions = TelegramNotifier.format_mentions(mention_ids, mention_name)

        camera_list = ", ".join(str(idx) for idx in failing_cameras)
        lines = [
            "<b>Frigate Monitor - Falhas detectadas</b>",
            f"<b>Host:</b> <code>{host.name}</code>",
            f"<b>Quantidade de câmeras em falha:</b> {len(failing_cameras)}",
            f"<b>Câmeras:</b> {camera_list}",
        ]
        if failure_started:
            lines.append(f"<b>Início estimado:</b> {failure_started.strftime('%Y-%m-%d %H:%M:%S')} GMT-3")
        lines.append(f"<b>Detectado em:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} GMT-3")
        if log_locations:
            for item in log_locations:
                lines.append(f"<b>Log {item['service']}:</b> {item['path']}")
        if mentions:
            lines.append(mentions)
        message = "\n".join(lines)
        if bot_token and chat_id:
            await self._notifier.send_message(bot_token, chat_id, message)

    async def manual_trigger(self, host_id: str) -> FailureRecord:
        hosts = [Host(**host) for host in self._config.get_hosts()]
        host = next((item for item in hosts if item.id == host_id), None)
        if not host:
            raise ValueError("Host not found")
        settings = self._config.get_settings()
        result = await self._check_host(host, settings)
        self._history.add_entry(result)
        return result

    def list_hosts(self) -> List[Host]:
        return [Host(**host) for host in self._config.get_hosts()]

    def create_host(self, payload: Dict) -> Host:
        host = HostCreate(**payload)
        self._config.add_host(host.model_dump())
        return Host(**host.model_dump())

    def update_host(self, host_id: str, payload: Dict) -> Host:
        host = self._config.update_host(host_id, HostUpdate(**payload).model_dump(exclude_none=True))
        return Host(**host)

    def delete_host(self, host_id: str) -> None:
        self._config.delete_host(host_id)

