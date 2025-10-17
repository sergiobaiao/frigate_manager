from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CheckLogEntry(BaseModel):
    timestamp: datetime
    message: str


class HostCheckRead(BaseModel):
    id: int
    host_id: int
    trigger: str
    status: str
    summary: Optional[str]
    log: List[CheckLogEntry]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    failure_event_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
