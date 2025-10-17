from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel


class Host(SQLModel, table=True):
    __tablename__ = "hosts"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    base_url: str
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    failures: List["FailureEvent"] = Relationship(back_populates="host")
    checks: List["HostCheck"] = Relationship(back_populates="host")


class FailureEvent(SQLModel, table=True):
    __tablename__ = "failure_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    host_id: int = Field(foreign_key="hosts.id")
    failure_count: int
    camera_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    failure_start: Optional[datetime] = None
    first_screenshot_path: Optional[str] = None
    second_screenshot_path: Optional[str] = None
    log_files: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    host: "Host" = Relationship(back_populates="failures")
    checks: List["HostCheck"] = Relationship(back_populates="failure")


class LogEntry(SQLModel, table=True):
    __tablename__ = "log_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    host_id: int = Field(foreign_key="hosts.id")
    service: str
    timestamp: Optional[datetime]
    level: Optional[str] = None
    message: Optional[str] = None
    raw: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HostCheck(SQLModel, table=True):
    __tablename__ = "host_checks"

    id: Optional[int] = Field(default=None, primary_key=True)
    host_id: int = Field(foreign_key="hosts.id")
    trigger: str = Field(default="scheduled")
    status: str = Field(default="pending")
    summary: Optional[str] = None
    log: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    failure_event_id: Optional[int] = Field(default=None, foreign_key="failure_events.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    host: "Host" = Relationship(back_populates="checks")
    failure: Optional["FailureEvent"] = Relationship(back_populates="checks")


__all__ = ["Host", "FailureEvent", "LogEntry", "HostCheck"]
