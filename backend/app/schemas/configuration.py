from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel


class ConfigRead(BaseModel):
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    CONTAINER_FILTER: str
    MENTION_USER_IDS: str
    MENTION_NAME: str
    CHECK_INTERVAL_MINUTES: int
    RETRY_DELAY_MINUTES: int
    DEBUG_MODE: bool
    USE_GPU_FOR_OCR: bool


class ConfigUpdate(BaseModel):
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    CONTAINER_FILTER: str | None = None
    MENTION_USER_IDS: str | None = None
    MENTION_NAME: str | None = None
    CHECK_INTERVAL_MINUTES: int | None = None
    RETRY_DELAY_MINUTES: int | None = None
    DEBUG_MODE: bool | None = None
    USE_GPU_FOR_OCR: bool | None = None


class ScreenshotTestRequest(BaseModel):
    url: AnyHttpUrl


class ScreenshotTestResponse(BaseModel):
    image_data_url: str

