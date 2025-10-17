from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import AppConfig, ConfigManager
from ..schemas.configuration import ConfigRead, ConfigUpdate

router = APIRouter(prefix="/config", tags=["config"])


def get_manager() -> ConfigManager:
    from ..main import config_manager

    return config_manager


def get_scheduler():
    from ..main import scheduler

    return scheduler


@router.get("", response_model=ConfigRead)
def read_config(manager: ConfigManager = Depends(get_manager)) -> ConfigRead:
    config = manager.get()
    return ConfigRead(**config.dict(by_alias=True))


@router.put("", response_model=ConfigRead)
def update_config(
    payload: ConfigUpdate,
    manager: ConfigManager = Depends(get_manager),
    monitor_scheduler=Depends(get_scheduler),
) -> ConfigRead:
    config = manager.update(payload.dict(exclude_unset=True))
    monitor_scheduler.reload()
    return ConfigRead(**config.dict(by_alias=True))
