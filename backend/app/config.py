from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .utils.paths import CONFIG_PATH


class AppConfig(BaseModel):
    telegram_bot_token: str = Field("", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field("", alias="TELEGRAM_CHAT_ID")
    container_filter: str = Field("frigate", alias="CONTAINER_FILTER")
    mention_user_ids: str = Field("", alias="MENTION_USER_IDS")
    mention_name: str = Field("", alias="MENTION_NAME")
    check_interval_minutes: int = Field(10, alias="CHECK_INTERVAL_MINUTES")
    retry_delay_minutes: int = Field(5, alias="RETRY_DELAY_MINUTES")

    class Config:
        allow_population_by_field_name = True
        orm_mode = True


class ConfigManager:
    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        self._config_path = config_path
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._config_path.exists():
            default = AppConfig()
            self.write_config(default)
        self._config = self.read_config()

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo("Etc/GMT+3")

    def read_config(self) -> AppConfig:
        with self._config_path.open("r", encoding="utf-8") as fh:
            payload: Dict[str, Any] = json.load(fh)
        return AppConfig.parse_obj(payload)

    def write_config(self, config: AppConfig) -> None:
        with self._config_path.open("w", encoding="utf-8") as fh:
            json.dump(config.dict(by_alias=True), fh, indent=2)

    def reload(self) -> AppConfig:
        self._config = self.read_config()
        return self._config

    def get(self) -> AppConfig:
        return self._config

    def update(self, payload: Dict[str, Any]) -> AppConfig:
        normalized: Dict[str, Any] = {}
        for field_name, model_field in AppConfig.__fields__.items():
            alias = model_field.alias or field_name
            if alias in payload and payload[alias] is not None:
                normalized[field_name] = payload[alias]
            elif field_name in payload and payload[field_name] is not None:
                normalized[field_name] = payload[field_name]
        config = self._config.copy(update=normalized)
        self.write_config(config)
        self._config = config
        return config


__all__ = ["AppConfig", "ConfigManager"]
