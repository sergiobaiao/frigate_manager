from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import func, select

from ..database import get_session
from ..models import FailureEvent, Host, HostCheck, LogEntry
from ..schemas.checks import HostCheckRead
from ..schemas.failures import FailureEventRead, FailureStats
from ..schemas.logs import LogEntryRead
from ..utils.paths import DATA_DIR, LOG_DIR, SCREENSHOT_DIR

router = APIRouter(prefix="/failures", tags=["failures"])


def _public_media_path(raw_path: Optional[str]) -> Optional[str]:
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (DATA_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(DATA_DIR)
    except ValueError:
        return None
    return f"/media/{relative.as_posix()}"


def _serialize_failure(failure: FailureEvent) -> FailureEventRead:
    payload = FailureEventRead.from_orm(failure)
    payload.first_screenshot_path = _public_media_path(payload.first_screenshot_path)
    payload.second_screenshot_path = _public_media_path(payload.second_screenshot_path)
    payload.log_files = [
        path for raw in payload.log_files if (path := _public_media_path(raw))
    ]
    return payload


def _serialize_check(check: HostCheck) -> HostCheckRead:
    payload = HostCheckRead.from_orm(check)
    return payload


def _gather_recent_files(paths: Iterable[str], limit: int = 2) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()
    for raw in paths:
        if raw and raw not in seen:
            seen.add(raw)
            results.append(raw)
        if len(results) >= limit:
            break
    return results


def _latest_media(host: Host, failures: List[FailureEvent]) -> dict:
    screenshot_candidates: List[str] = []
    for failure in failures:
        screenshot_candidates.extend(
            [
                str(path)
                for path in [failure.second_screenshot_path, failure.first_screenshot_path]
                if path
            ]
        )

    if len(screenshot_candidates) < 2:
        pattern = f"{host.name}-*.png"
        recent_fs = sorted(
            SCREENSHOT_DIR.glob(pattern),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for item in recent_fs:
            screenshot_candidates.append(str(item))
            if len(screenshot_candidates) >= 2:
                break

    screenshot_paths = _gather_recent_files(screenshot_candidates, limit=2)
    captured_at: Optional[str] = None
    screenshots = []
    labels = ["Latest", "Previous"]
    for index, raw_path in enumerate(screenshot_paths):
        path_obj = Path(raw_path)
        if captured_at is None:
            try:
                timestamp = datetime.fromtimestamp(path_obj.stat().st_mtime, tz=timezone.utc)
                captured_at = timestamp.isoformat()
            except FileNotFoundError:
                captured_at = None
        if public := _public_media_path(raw_path):
            label = labels[index] if index < len(labels) else f"Screenshot {index + 1}"
            screenshots.append({"url": public, "label": label})

    log_candidates: List[str] = []
    for failure in failures:
        log_candidates.extend(failure.log_files or [])

    if not log_candidates:
        log_pattern = f"{host.name}-*.log"
        recent_logs = sorted(
            LOG_DIR.glob(log_pattern),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        log_candidates = [str(item) for item in recent_logs[:3]]

    logs = []
    for raw_path in _gather_recent_files(log_candidates, limit=5):
        if public := _public_media_path(raw_path):
            filename = Path(raw_path).name
            logs.append({"url": public, "label": filename})

    return {"screenshots": screenshots, "logs": logs, "captured_at": captured_at}


@router.get("", response_model=List[FailureEventRead])
def list_failures(host_id: Optional[int] = None, limit: int = Query(100, le=1000)) -> List[FailureEventRead]:
    with get_session() as session:
        query = select(FailureEvent).order_by(FailureEvent.created_at.desc())
        if host_id:
            query = query.where(FailureEvent.host_id == host_id)
        if limit:
            query = query.limit(limit)
        failures = session.exec(query).all()
    return [_serialize_failure(failure) for failure in failures]


@router.get("/stats", response_model=List[FailureStats])
def failure_stats() -> List[FailureStats]:
    with get_session() as session:
        stmt = (
            select(
                FailureEvent.host_id,
                func.count(FailureEvent.id),
                func.sum(FailureEvent.failure_count),
                func.max(FailureEvent.created_at),
            )
            .group_by(FailureEvent.host_id)
        )
        rows = session.exec(stmt).all()
        stats: List[FailureStats] = []
        for host_id, failures, total_cameras, last_failure in rows:
            stats.append(
                FailureStats(
                    host_id=host_id,
                    total_failures=failures,
                    total_cameras_impacted=total_cameras or 0,
                    last_failure=last_failure,
                )
            )
    return stats


@router.get("/{failure_id}", response_model=FailureEventRead)
def get_failure(failure_id: int) -> FailureEventRead:
    with get_session() as session:
        failure = session.get(FailureEvent, failure_id)
        if not failure:
            raise HTTPException(status_code=404, detail="Failure not found")
    return _serialize_failure(failure)


@router.get("/{failure_id}/logs", response_model=List[LogEntryRead])
def failure_logs(failure_id: int) -> List[LogEntryRead]:
    with get_session() as session:
        failure = session.get(FailureEvent, failure_id)
        if not failure:
            raise HTTPException(status_code=404, detail="Failure not found")
        query = (
            select(LogEntry)
            .where(LogEntry.host_id == failure.host_id)
            .order_by(LogEntry.timestamp.desc())
            .limit(500)
        )
        entries = session.exec(query).all()
    return entries


@router.get("/host/{host_id}/logs", response_model=List[LogEntryRead])
def host_logs(host_id: int, service: Optional[str] = None, limit: int = Query(200, le=2000)) -> List[LogEntryRead]:
    with get_session() as session:
        query = select(LogEntry).where(LogEntry.host_id == host_id)
        if service:
            query = query.where(LogEntry.service == service)
        query = query.order_by(LogEntry.timestamp.desc()).limit(limit)
        entries = session.exec(query).all()
    return entries


@router.get("/host/{host_id}/summary")
def host_summary(host_id: int) -> dict:
    with get_session() as session:
        host = session.get(Host, host_id)
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")
        failures = session.exec(
            select(FailureEvent)
            .where(FailureEvent.host_id == host_id)
            .order_by(FailureEvent.created_at.desc())
            .limit(25)
        ).all()
        active_check = session.exec(
            select(HostCheck)
            .where(
                HostCheck.host_id == host_id,
                HostCheck.status.in_(["pending", "running"]),
            )
            .order_by(HostCheck.created_at.desc())
            .limit(1)
        ).first()
        latest_check = session.exec(
            select(HostCheck)
            .where(HostCheck.host_id == host_id)
            .order_by(HostCheck.created_at.desc())
            .limit(1)
        ).first()
    serialized_failures = [_serialize_failure(failure) for failure in failures]
    return {
        "host": host,
        "failures": serialized_failures,
        "latest_media": _latest_media(host, failures),
        "current_check": _serialize_check(active_check) if active_check else None,
        "latest_check": _serialize_check(latest_check) if latest_check else None,
    }
