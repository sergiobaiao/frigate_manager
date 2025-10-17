from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


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


class FailureStats(BaseModel):
    host_id: int
    total_failures: int
    total_cameras_impacted: int
    last_failure: Optional[datetime]


class HostDashboard(BaseModel):
    host_id: int
    host_name: str
    total_failures: int
    recent_failures: List[FailureEventRead]

