from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "config.local.json"
_ADDRESS_RE = re.compile(r"(?i)^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$")


def _config_path() -> Path:
    configured = os.environ.get("MOMIR_CONFIG_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH


def load_local_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read Momir configuration from {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError(f"Momir configuration must contain a JSON object: {path}")
    return loaded


def get_printer_address(*, required: bool = True) -> str | None:
    value = os.environ.get("MOMIR_PRINTER_ADDRESS", "").strip()
    if not value:
        printer = load_local_config().get("printer", {})
        if isinstance(printer, dict):
            value = str(printer.get("bluetooth_address") or "").strip()
    if not value:
        if required:
            raise RuntimeError(
                "Printer Bluetooth address is not configured. Set "
                "MOMIR_PRINTER_ADDRESS or edit config.local.json."
            )
        return None
    if not _ADDRESS_RE.fullmatch(value):
        raise RuntimeError("Configured printer Bluetooth address is invalid.")
    return value.upper()


def get_printer_channel() -> str:
    value = os.environ.get("MOMIR_PRINTER_CHANNEL", "").strip()
    if not value:
        printer = load_local_config().get("printer", {})
        if isinstance(printer, dict):
            value = str(printer.get("channel") or "").strip()
    if not value:
        value = "4"
    if not value.isdigit() or not 1 <= int(value) <= 30:
        raise RuntimeError("Configured printer Bluetooth channel is invalid.")
    return value


def _config_section(name: str) -> dict[str, Any]:
    section = load_local_config().get(name, {})
    return section if isinstance(section, dict) else {}


def get_web_host() -> str:
    value = os.environ.get("MOMIR_HOST", "").strip()
    if not value:
        value = str(_config_section("web").get("host") or "").strip()
    return value or "0.0.0.0"


def get_web_port() -> int:
    value = os.environ.get("MOMIR_PORT", "").strip()
    if not value:
        value = str(_config_section("web").get("port") or "").strip()
    value = value or "5000"
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError("Configured web port must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Configured web port must be between 1 and 65535.")
    return port


def get_local_base_url() -> str:
    value = os.environ.get("MOMIR_LOCAL_BASE_URL", "").strip()
    if not value:
        value = str(_config_section("web").get("local_base_url") or "").strip()
    return (value or "http://momir.local:5000").rstrip("/")
