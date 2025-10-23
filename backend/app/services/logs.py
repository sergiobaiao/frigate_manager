from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from sqlmodel import Session

from ..models import LogEntry

TIMESTAMP_PATTERN = re.compile(
    r"(\\d{4}-\\d{2}-\\d{2}[T\s]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?)"
)


def save_log_file(hostname: str, service: str, content: str, base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{hostname}-{service}.log"
    path = base_dir / filename
    try:
        path.write_text(content, encoding="utf-8")
    except FileNotFoundError:
        # Ensure intermediary directories exist if the base directory was changed dynamically.
        path.parent.mkdir(parents=True, exist_ok=True)
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


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _parse_plaintext_entries(content: str) -> List[dict]:
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


def _normalize_line_entry(payload: dict) -> dict:
    entry = dict(payload)

    message = entry.get("message") or entry.get("msg") or entry.get("line")
    if message is not None:
        entry.setdefault("message", message)

    timestamp = (
        entry.get("timestamp")
        or entry.get("time")
        or entry.get("ts")
        or entry.get("datetime")
    )
    if timestamp is not None:
        entry.setdefault("timestamp", timestamp)

    level = entry.get("level") or entry.get("severity") or entry.get("log_level")
    if level is not None:
        entry.setdefault("level", level)

    return entry


def _determine_columns(entries: Sequence[dict]) -> List[str]:
    preferred = ["timestamp", "level", "message"]
    columns: List[str] = []
    for key in preferred:
        if any(key in entry for entry in entries):
            columns.append(key)
    extras: List[str] = []
    for entry in entries:
        for key in entry.keys():
            if key not in columns and key not in extras:
                extras.append(key)
    columns.extend(sorted(extras))
    return columns


def render_log_lines_as_table(lines: Sequence[dict]) -> str:
    normalized = [_normalize_line_entry(line) for line in lines if isinstance(line, dict)]
    if not normalized:
        return ""
    columns = _determine_columns(normalized)
    header = "\t".join(columns)
    rows = [
        "\t".join(_stringify(entry.get(column, "")) for column in columns)
        for entry in normalized
    ]
    return "\n".join([header, *rows])


def parse_log_entries(content: str) -> List[dict]:
    content = content.strip()
    if not content:
        return []
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("lines"), list):
        lines = [line for line in payload.get("lines", []) if isinstance(line, dict)]
        if not lines:
            return []
        return [_normalize_line_entry(line) for line in lines]
    return _parse_plaintext_entries(content)


def prepare_log_content(content: str) -> tuple[str, List[dict]]:
    content = content or ""
    stripped = content.strip()
    if not stripped:
        return "", []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("lines"), list):
        lines = [line for line in payload.get("lines", []) if isinstance(line, dict)]
        table = render_log_lines_as_table(lines)
        entries = [_normalize_line_entry(line) for line in lines]
        return table, entries
    entries = _parse_plaintext_entries(content)
    return content, entries


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

