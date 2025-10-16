from __future__ import annotations

import asyncio
from typing import Dict, Iterable, List, Optional

import httpx


class TelegramNotifier:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30)
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def send_message(
        self,
        bot_token: str,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> Optional[Dict]:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        async with self._lock:
            response = await self._client.post(url, data=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def format_mentions(user_ids: Iterable[str], name: str) -> str:
        tags: List[str] = []
        for user_id in user_ids:
            tags.append(f"<a href=\"tg://user?id={user_id}\">{name}</a>")
        return " ".join(tags)


__all__ = ["TelegramNotifier"]
