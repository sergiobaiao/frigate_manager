from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..database import get_session
from ..models import Host
from ..schemas.hosts import HostCreate, HostRead, HostUpdate

router = APIRouter(prefix="/hosts", tags=["hosts"])


@router.get("", response_model=List[HostRead])
def list_hosts() -> List[HostRead]:
    with get_session() as session:
        hosts = session.exec(select(Host)).all()
    return hosts


@router.post("", response_model=HostRead)
def create_host(payload: HostCreate) -> HostRead:
    host = Host.from_orm(payload)
    now = datetime.utcnow()
    host.created_at = now
    host.updated_at = now
    with get_session() as session:
        session.add(host)
        session.commit()
        session.refresh(host)
    return host


@router.put("/{host_id}", response_model=HostRead)
def update_host(host_id: int, payload: HostUpdate) -> HostRead:
    with get_session() as session:
        host = session.get(Host, host_id)
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")
        data = payload.dict(exclude_unset=True)
        for key, value in data.items():
            setattr(host, key, value)
        host.updated_at = datetime.utcnow()
        session.add(host)
        session.commit()
        session.refresh(host)
    return host


@router.delete("/{host_id}")
def delete_host(host_id: int) -> dict:
    with get_session() as session:
        host = session.get(Host, host_id)
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")
        session.delete(host)
        session.commit()
    return {"status": "deleted"}
