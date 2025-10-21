from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, validator

from ._timezone import apply_config_timezone


class CheckLogEntry(BaseModel):
    timestamp: datetime
    message: str

    @validator("timestamp", pre=False)
    def _set_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        localized = apply_config_timezone(value)
        return localized if localized is not None else value


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

    @validator(
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
        pre=False,
    )
    def _set_host_check_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        return apply_config_timezone(value)
