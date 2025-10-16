from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config_manager import ConfigManager
from .history_manager import HistoryManager
from .models import FailureRecord, HostCreate, HostUpdate
from .monitor import MonitorService, SERVICE_ENDPOINTS
from .notifier import TelegramNotifier
from .utils import build_table, parse_json_lines

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"
HISTORY_PATH = DATA_DIR / "history.json"

config_manager = ConfigManager(CONFIG_PATH)
settings = config_manager.get_settings()
history_manager = HistoryManager(HISTORY_PATH, settings.get("timezone", "America/Sao_Paulo"))
notifier = TelegramNotifier()
monitor_service = MonitorService(config_manager, history_manager, notifier, DATA_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await monitor_service.start()
    yield
    await monitor_service.stop()
    await notifier.close()


app = FastAPI(title="Frigate Monitor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/hosts")
def list_hosts():
    hosts = monitor_service.list_hosts()
    return [host.model_dump() for host in hosts]


@app.post("/api/hosts")
def create_host(payload: HostCreate):
    host = monitor_service.create_host(payload.model_dump())
    return host.model_dump()


@app.put("/api/hosts/{host_id}")
def update_host(host_id: str, payload: HostUpdate):
    try:
        host = monitor_service.update_host(host_id, payload.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return host.model_dump()


@app.delete("/api/hosts/{host_id}")
def delete_host(host_id: str):
    monitor_service.delete_host(host_id)
    return {"status": "ok"}


@app.get("/api/settings")
def get_settings():
    return config_manager.get_settings()


@app.put("/api/settings")
async def update_settings(payload: Dict):
    updated = config_manager.update_settings(payload)
    history_manager.set_timezone(updated.get("timezone", "America/Sao_Paulo"))
    await monitor_service.restart()
    return updated


@app.post("/api/hosts/{host_id}/trigger")
async def trigger_host(host_id: str):
    try:
        result = await monitor_service.manual_trigger(host_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump()


@app.get("/api/history")
def history(host_id: str | None = None, limit: int | None = 100):
    entries = history_manager.get_entries(host_id=host_id, limit=limit)
    return [entry.model_dump() for entry in entries]


@app.get("/api/history/summary")
def history_summary():
    hosts = monitor_service.list_hosts()
    summary = history_manager.build_summary(hosts)
    return summary.model_dump()


@app.get("/api/history/host/{host_id}")
def host_history(host_id: str):
    entries = history_manager.get_entries(host_id=host_id, limit=None)
    if not entries:
        return {"entries": [], "aggregated": {}}
    aggregated = _aggregate_host_history(entries)
    return {
        "entries": [entry.model_dump() for entry in entries],
        "aggregated": aggregated,
    }


def _aggregate_host_history(entries: List[FailureRecord]):
    by_day: Dict[str, Dict[str, int]] = {}
    camera_counts: Dict[str, int] = {}
    for entry in entries:
        day = entry.timestamp.date().isoformat()
        stats = by_day.setdefault(day, {"checks": 0, "failures": 0})
        stats["checks"] += 1
        if entry.status == "failure":
            stats["failures"] += 1
            for camera in entry.failing_cameras:
                camera_counts[str(camera)] = camera_counts.get(str(camera), 0) + 1
    return {
        "by_day": [
            {"date": day, **stats}
            for day, stats in sorted(by_day.items())
        ],
        "by_camera": camera_counts,
    }


@app.get("/api/logs/{host_id}")
def read_logs(host_id: str):
    hosts = {host.id: host for host in monitor_service.list_hosts()}
    host = hosts.get(host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    logs_dir = DATA_DIR / "logs"
    results: Dict[str, Dict] = {}
    safe_name = host.name.replace(" ", "_")
    for service in SERVICE_ENDPOINTS.keys():
        file_path = logs_dir / f"{safe_name}-{service}.log"
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        records = parse_json_lines(text)
        columns, rows = build_table(records)
        results[service] = {
            "path": str(file_path),
            "columns": columns,
            "rows": rows,
        }
    return {
        "host": host.model_dump(),
        "logs": results,
    }


@app.get("/api/status")
def status():
    hosts = monitor_service.list_hosts()
    statuses: List[Dict] = []
    for host in hosts:
        records = history_manager.get_entries(host_id=host.id, limit=1)
        if records:
            statuses.append(records[0].model_dump())
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "statuses": statuses,
    }


