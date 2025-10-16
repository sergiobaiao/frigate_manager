from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from dateutil import parser as date_parser
from pytz import timezone as tz_get


def ensure_timezone(dt: datetime, tz_name: str) -> datetime:
    tz = tz_get(tz_name)
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt.astimezone(tz)


def parse_json_lines(log_text: str) -> List[Dict]:
    records: List[Dict] = []
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"message": line})
    return records


def extract_failure_start(records: Iterable[Dict]) -> Optional[datetime]:
    timestamps: List[datetime] = []
    for record in records:
        for key in ("ts", "time", "timestamp", "date"):
            value = record.get(key)
            if value:
                try:
                    timestamps.append(date_parser.isoparse(str(value)))
                except (ValueError, TypeError):
                    continue
    if not timestamps:
        return None
    return min(timestamps)


def build_table(records: List[Dict]) -> Tuple[List[str], List[Dict[str, str]]]:
    keys = set()
    for record in records:
        keys.update(record.keys())
    columns = sorted(keys)
    rows: List[Dict[str, str]] = []
    for record in records:
        row = {column: str(record.get(column, "")) for column in columns}
        rows.append(row)
    return columns, rows
