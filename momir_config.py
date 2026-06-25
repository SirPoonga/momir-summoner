from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "config.local.json"
_ADDRESS_RE = re.compile(r"(?i)^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$")

DEFAULT_PRINTER_MARGINS = {
    "left": 25,
    "top": 45,
    "right": 25,
    "bottom": 40,
}

_PRINTER_MARGIN_ENV_VARS = {
    "left": "MOMIR_PRINTER_MARGIN_LEFT",
    "top": "MOMIR_PRINTER_MARGIN_TOP",
    "right": "MOMIR_PRINTER_MARGIN_RIGHT",
    "bottom": "MOMIR_PRINTER_MARGIN_BOTTOM",
}


def _config_path() -> Path:
    configured = os.environ.get("MOMIR_CONFIG_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH


def get_config_path() -> Path:
    """Return the active local configuration path."""
    return _config_path()


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




def _coerce_printer_margin(name: str, raw: Any) -> int:
    if isinstance(raw, bool):
        raise RuntimeError(f"Printer margin {name} must be an integer.")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and re.fullmatch(r"[+-]?\d+", raw.strip()):
        value = int(raw.strip())
    else:
        raise RuntimeError(f"Printer margin {name} must be an integer.")
    if not 0 <= value <= 250:
        raise RuntimeError(
            f"Printer margin {name} must be between 0 and 250 pixels."
        )
    return value


def _validate_printer_margins(margins: dict[str, int]) -> dict[str, int]:
    if margins["left"] + margins["right"] > 270:
        raise RuntimeError(
            "Left and right margins must leave at least 180 pixels of print width."
        )
    if margins["top"] + margins["bottom"] > 470:
        raise RuntimeError(
            "Top and bottom margins must leave at least 260 pixels of print height."
        )
    return margins


def get_printer_margins() -> dict[str, int]:
    """Return margins for the currently configured printer."""
    printer = load_local_config().get("printer", {})
    if not isinstance(printer, dict):
        printer = {}
    configured = printer.get("margins", {})
    if configured in (None, ""):
        configured = {}
    if not isinstance(configured, dict):
        raise RuntimeError("Printer margins must be a JSON object.")

    margins: dict[str, int] = {}
    for name, default in DEFAULT_PRINTER_MARGINS.items():
        raw: Any = os.environ.get(_PRINTER_MARGIN_ENV_VARS[name], "").strip()
        if raw == "":
            raw = configured.get(name, default)
        margins[name] = _coerce_printer_margin(name, raw)
    return _validate_printer_margins(margins)


def save_printer_margins(values: dict[str, Any]) -> dict[str, int]:
    """Validate and persist margins for the currently configured printer."""
    if not isinstance(values, dict):
        raise RuntimeError("Printer margins must be a JSON object.")

    margins = {
        name: _coerce_printer_margin(name, values.get(name))
        for name in DEFAULT_PRINTER_MARGINS
    }
    _validate_printer_margins(margins)

    config = load_local_config()
    printer = config.get("printer")
    if not isinstance(printer, dict):
        printer = {}
        config["printer"] = printer
    printer["margins"] = margins

    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)
    return margins


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
