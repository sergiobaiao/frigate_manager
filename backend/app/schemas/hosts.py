from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, HttpUrl, validator

from ._timezone import apply_config_timezone


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

    @validator("created_at", "updated_at", pre=False)
    def _set_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        localized = apply_config_timezone(value)
        return localized if localized is not None else value


class FailureSummary(BaseModel):
    id: int
    failure_count: int
    camera_ids: List[str]
    failure_start: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True

    @validator("failure_start", "created_at", pre=False)
    def _set_failure_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        return apply_config_timezone(value)


class HostWithFailures(HostRead):
    failures: List[FailureSummary] = []

