from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

import httpx

from ..config import AppConfig

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


async def send_message(config: AppConfig, message: str) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            TELEGRAM_API.format(token=config.telegram_bot_token, method="sendMessage"),
            data={
                "chat_id": config.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )


async def send_media(
    config: AppConfig,
    file_paths: Iterable[str],
    caption: str | None = None,
    media_type: str = "document",
) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return
    method = "sendDocument" if media_type == "document" else "sendPhoto"
    async with httpx.AsyncClient(timeout=None) as client:
        for path in file_paths:
            field_name = "document" if method == "sendDocument" else "photo"
            with open(path, "rb") as file_handle:
                files = {field_name: file_handle}
                data = {"chat_id": config.telegram_chat_id}
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = "HTML"
                await client.post(
                    TELEGRAM_API.format(token=config.telegram_bot_token, method=method),
                    data=data,
                    files=files,
                )


async def send_media_group(
    config: AppConfig,
    photos: List[str],
    caption: str | None = None,
) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id or not photos:
        return
    async with httpx.AsyncClient(timeout=None) as client:
        media = []
        for idx, photo in enumerate(photos):
            entry = {"type": "photo", "media": "attach://photo{}".format(idx)}
            if idx == 0 and caption:
                entry["caption"] = caption
                entry["parse_mode"] = "HTML"
            media.append(entry)
        files = {}
        for idx, photo in enumerate(photos):
            handle = open(photo, "rb")
            files[f"photo{idx}"] = (Path(photo).name, handle, "image/png")
        try:
            await client.post(
                TELEGRAM_API.format(token=config.telegram_bot_token, method="sendMediaGroup"),
                data={"chat_id": config.telegram_chat_id, "media": json.dumps(media)},
                files=files,
            )
        finally:
            for _, handle, _ in files.values():
                handle.close()
