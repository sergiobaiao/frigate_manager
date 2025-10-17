from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, HttpUrl


class HostBase(BaseModel):
    name: str
    base_url: HttpUrl
    enabled: bool = True


class HostCreate(HostBase):
    pass


class HostUpdate(BaseModel):
    name: Optional[str]
    base_url: Optional[HttpUrl]
    enabled: Optional[bool]


class HostRead(HostBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class FailureSummary(BaseModel):
    id: int
    failure_count: int
    camera_ids: List[str]
    failure_start: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True


class HostWithFailures(HostRead):
    failures: List[FailureSummary] = []

