from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, validator

from ._timezone import apply_config_timezone


class FailureEventRead(BaseModel):
    id: int
    host_id: int
    failure_count: int
    camera_ids: List[str]
    failure_start: Optional[datetime]
    first_screenshot_path: Optional[str]
    second_screenshot_path: Optional[str]
    log_files: List[str]
    created_at: datetime

    class Config:
        orm_mode = True

    @validator("failure_start", "created_at", pre=False)
    def _set_failure_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        return apply_config_timezone(value)


class FailureStats(BaseModel):
    host_id: int
    total_failures: int
    total_cameras_impacted: int
    last_failure: Optional[datetime]

    @validator("last_failure", pre=False)
    def _set_stats_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        return apply_config_timezone(value)


class HostDashboard(BaseModel):
    host_id: int
    host_name: str
    total_failures: int
    recent_failures: List[FailureEventRead]

