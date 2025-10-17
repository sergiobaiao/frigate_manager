from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from sqlmodel import Session

from ..models import LogEntry

TIMESTAMP_PATTERN = re.compile(
    r"(\\d{4}-\\d{2}-\\d{2}[T\s]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?)"
)


def save_log_file(hostname: str, service: str, content: str, base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{hostname}-{service}.log"
    path = base_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def parse_timestamp(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_timestamp_from_line(line: str) -> Optional[datetime]:
    match = TIMESTAMP_PATTERN.search(line)
    if not match:
        return None
    return parse_timestamp(match.group(1))


def parse_log_entries(content: str) -> List[dict]:
    entries: List[dict] = []
    for raw_line in content.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        parsed: Optional[dict] = None
        if raw_line.startswith("{"):
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                parsed = None
        if parsed is None:
            timestamp = extract_timestamp_from_line(raw_line)
            parsed = {
                "message": raw_line,
                "timestamp": timestamp.isoformat() if timestamp else None,
            }
        entries.append(parsed)
    return entries


def persist_log_entries(
    session: Session,
    host_id: int,
    service: str,
    entries: Iterable[dict],
) -> List[LogEntry]:
    stored: List[LogEntry] = []
    for entry in entries:
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = parse_timestamp(timestamp)
        log = LogEntry(
            host_id=host_id,
            service=service,
            timestamp=timestamp,
            level=entry.get("level") or entry.get("severity"),
            message=entry.get("message") or entry.get("msg"),
            raw=entry,
        )
        session.add(log)
        stored.append(log)
    session.commit()
    for log in stored:
        session.refresh(log)
    return stored


def estimate_failure_start(entries: Iterable[dict], tz) -> Optional[datetime]:
    interesting: List[datetime] = []
    for entry in entries:
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str):
            parsed = parse_timestamp(timestamp)
        else:
            parsed = timestamp
        if parsed:
            interesting.append(parsed.astimezone(tz) if parsed.tzinfo else parsed.replace(tzinfo=tz))
    if not interesting:
        return None
    return min(interesting)

