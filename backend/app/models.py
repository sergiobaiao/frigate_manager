from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class HostBase(BaseModel):
    name: str = Field(..., description="Human readable host name")
    address: HttpUrl = Field(..., description="Base URL for the Frigate instance")
    notes: Optional[str] = Field(None, description="Optional notes about the host")


class HostCreate(HostBase):
    id: str = Field(default_factory=lambda: uuid4().hex)


class HostUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[HttpUrl] = None
    notes: Optional[str] = None


class Host(HostBase):
    id: str


class Settings(BaseModel):
    telegram_bot_token: str
    telegram_chat_id: str
    container_filter: str
    mention_user_ids: List[str]
    mention_name: str
    check_interval_minutes: int = Field(ge=1)
    timezone: str = Field(default="America/Sao_Paulo")


class LogLocation(BaseModel):
    service: str
    path: str


class FailureRecord(BaseModel):
    id: str
    host_id: str
    host_name: str
    timestamp: datetime
    timezone: str
    status: str
    failing_count: int
    failing_cameras: List[int]
    failure_started_at: Optional[datetime] = None
    log_locations: List[LogLocation] = Field(default_factory=list)
    notes: Optional[str] = None


class HistoryResponse(BaseModel):
    entries: List[FailureRecord]


class SummaryBucket(BaseModel):
    period: str
    total_checks: int
    failures: int


class HostSummary(BaseModel):
    host: Host
    totals: SummaryBucket
    failure_counts_by_camera: Dict[str, int]
    history: List[FailureRecord]


class SummaryResponse(BaseModel):
    generated_at: datetime
    timezone: str
    hosts: List[HostSummary]


class ManualTriggerResponse(BaseModel):
    host: Host
    result: FailureRecord


class StatusResponse(BaseModel):
    generated_at: datetime
    timezone: str
    statuses: List[FailureRecord]
