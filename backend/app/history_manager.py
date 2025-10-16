from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dateutil import parser as date_parser
from pytz import timezone as tz_get

from .models import FailureRecord, Host, HostSummary, LogLocation, SummaryBucket, SummaryResponse


class HistoryManager:
    def __init__(self, history_path: Path, tz_name: str) -> None:
        self._history_path = history_path
        self._lock = threading.Lock()
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._history_path.exists():
            self._write([])
        self._tz_name = tz_name

    def set_timezone(self, tz_name: str) -> None:
        self._tz_name = tz_name

    def _write(self, data: List[Dict]) -> None:
        with self._history_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    def _read(self) -> List[Dict]:
        with self._history_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _normalize_datetime(self, value: str) -> datetime:
        dt = date_parser.isoparse(value)
        return dt

    def add_entry(self, record: FailureRecord) -> FailureRecord:
        payload = record.model_dump()
        payload["timestamp"] = record.timestamp.isoformat()
        if record.failure_started_at:
            payload["failure_started_at"] = record.failure_started_at.isoformat()
        with self._lock:
            history = self._read()
            history.append(payload)
            self._write(history)
        return record

    def get_entries(self, host_id: Optional[str] = None, limit: Optional[int] = None) -> List[FailureRecord]:
        data = self._read()
        if host_id:
            data = [row for row in data if row["host_id"] == host_id]
        data = sorted(data, key=lambda item: item["timestamp"], reverse=True)
        if limit:
            data = data[:limit]
        return [self._to_record(item) for item in data]

    def _to_record(self, item: Dict) -> FailureRecord:
        timestamp = self._normalize_datetime(item["timestamp"])
        failure_started_at = item.get("failure_started_at")
        if failure_started_at:
            failure_started_at = self._normalize_datetime(failure_started_at)
        logs = [LogLocation(**entry) for entry in item.get("log_locations", [])]
        return FailureRecord(
            id=item["id"],
            host_id=item["host_id"],
            host_name=item["host_name"],
            timestamp=timestamp,
            timezone=item.get("timezone", self._tz_name),
            status=item.get("status", "unknown"),
            failing_count=item.get("failing_count", 0),
            failing_cameras=item.get("failing_cameras", []),
            failure_started_at=failure_started_at,
            log_locations=logs,
            notes=item.get("notes"),
        )

    def build_summary(self, hosts: List[Host]) -> SummaryResponse:
        entries = self.get_entries()
        aggregated: Dict[str, Dict] = defaultdict(lambda: {
            "total_checks": 0,
            "failures": 0,
            "camera_counts": defaultdict(int),
        })
        latest_per_host: Dict[str, List[FailureRecord]] = defaultdict(list)

        for entry in entries:
            aggregated[entry.host_id]["total_checks"] += 1
            if entry.status == "failure":
                aggregated[entry.host_id]["failures"] += 1
                for camera in entry.failing_cameras:
                    aggregated[entry.host_id]["camera_counts"][str(camera)] += 1
            latest_per_host[entry.host_id].append(entry)

        summaries: List[HostSummary] = []
        for host in hosts:
            meta = aggregated.get(host.id, {"total_checks": 0, "failures": 0, "camera_counts": {}})
            summaries.append(
                HostSummary(
                    host=host,
                    totals=SummaryBucket(
                        period="lifetime",
                        total_checks=meta.get("total_checks", 0),
                        failures=meta.get("failures", 0),
                    ),
                    failure_counts_by_camera=dict(meta.get("camera_counts", {})),
                    history=latest_per_host.get(host.id, [])[:50],
                )
            )

        return SummaryResponse(
            generated_at=datetime.now(tz_get(self._tz_name)),
            timezone=self._tz_name,
            hosts=summaries,
        )


__all__ = ["HistoryManager"]
