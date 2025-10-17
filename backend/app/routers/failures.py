from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import func, select

from ..database import get_session
from ..models import FailureEvent, Host, LogEntry
from ..schemas.failures import FailureEventRead, FailureStats
from ..schemas.logs import LogEntryRead

router = APIRouter(prefix="/failures", tags=["failures"])


@router.get("", response_model=List[FailureEventRead])
def list_failures(host_id: Optional[int] = None, limit: int = Query(100, le=1000)) -> List[FailureEventRead]:
    with get_session() as session:
        query = select(FailureEvent).order_by(FailureEvent.created_at.desc())
        if host_id:
            query = query.where(FailureEvent.host_id == host_id)
        if limit:
            query = query.limit(limit)
        failures = session.exec(query).all()
    return failures


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
    return failure


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
    return {
        "host": host,
        "failures": failures,
    }
