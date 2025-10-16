import json
import threading
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "settings": {
        "telegram_bot_token": "7920768022:AAEPamnK198v5zZgFoV7JTIUmwQR5gpl0MA",
        "telegram_chat_id": "-4903664506",
        "container_filter": "frigate",
        "mention_user_ids": ["164182203", "5005576103", "849791306"],
        "mention_name": "@sergiobaiao",
        "check_interval_minutes": 10,
        "timezone": "America/Sao_Paulo"
    },
    "hosts": []
}


class ConfigManager:
    """Thread-safe configuration manager backed by JSON files."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._lock = threading.Lock()
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._config_path.exists():
            self._write(DEFAULT_CONFIG)

    def _read(self) -> Dict[str, Any]:
        with self._config_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, data: Dict[str, Any]) -> None:
        with self._config_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return self._read()

    def get_settings(self) -> Dict[str, Any]:
        return self.get_config().get("settings", {})

    def get_hosts(self) -> List[Dict[str, Any]]:
        return list(self.get_config().get("hosts", []))

    def update_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            config = self._read()
            config.setdefault("settings", {}).update(new_settings)
            self._write(config)
            return config["settings"]

    def replace_hosts(self, hosts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with self._lock:
            config = self._read()
            config["hosts"] = hosts
            self._write(config)
            return hosts

    def save_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._write(config)
            return config

    def update_host(self, host_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            config = self._read()
            hosts = config.setdefault("hosts", [])
            for idx, host in enumerate(hosts):
                if host.get("id") == host_id:
                    updated = {**host, **payload}
                    hosts[idx] = updated
                    self._write(config)
                    return updated
            raise KeyError(f"Host {host_id} not found")

    def add_host(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            config = self._read()
            hosts = config.setdefault("hosts", [])
            hosts.append(payload)
            self._write(config)
            return payload

    def delete_host(self, host_id: str) -> None:
        with self._lock:
            config = self._read()
            hosts = config.setdefault("hosts", [])
            new_hosts = [host for host in hosts if host.get("id") != host_id]
            config["hosts"] = new_hosts
            self._write(config)


__all__ = ["ConfigManager", "DEFAULT_CONFIG"]
