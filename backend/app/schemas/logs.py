from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class LogEntryRead(BaseModel):
    id: int
    host_id: int
    service: str
    timestamp: Optional[datetime]
    level: Optional[str]
    message: Optional[str]
    raw: Dict[str, Any]
    created_at: datetime

    class Config:
        orm_mode = True


class LogQueryParams(BaseModel):
    service: Optional[str]
    host_id: Optional[int]
    limit: int = 100

