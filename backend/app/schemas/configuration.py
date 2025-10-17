from __future__ import annotations

from pydantic import BaseModel


class ConfigRead(BaseModel):
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    CONTAINER_FILTER: str
    MENTION_USER_IDS: str
    MENTION_NAME: str
    CHECK_INTERVAL_MINUTES: int
    RETRY_DELAY_MINUTES: int


class ConfigUpdate(BaseModel):
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    CONTAINER_FILTER: str | None = None
    MENTION_USER_IDS: str | None = None
    MENTION_NAME: str | None = None
    CHECK_INTERVAL_MINUTES: int | None = None
    RETRY_DELAY_MINUTES: int | None = None

