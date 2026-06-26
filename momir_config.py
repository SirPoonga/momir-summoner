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


# MOMIR_THERMAL_PRINTER_CONFIG_START
PRINTER_TYPES = ("photo", "thermal_58mm")
DEFAULT_THERMAL_PRINTER_SETTINGS = {
    "columns": 32,
    "paper_width_pixels": 384,
    "qr_size_pixels": 144,
    "transport": "mock",
}
_THERMAL_ENV_VARS = {
    "columns": "MOMIR_THERMAL_COLUMNS",
    "paper_width_pixels": "MOMIR_THERMAL_PAPER_WIDTH_PIXELS",
    "qr_size_pixels": "MOMIR_THERMAL_QR_SIZE_PIXELS",
    "transport": "MOMIR_THERMAL_TRANSPORT",
}
# MOMIR_THERMAL_PRINTER_CONFIG_END


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


# MOMIR_THERMAL_PRINTER_FUNCTIONS_START
def _coerce_thermal_integer(
    name: str,
    raw: Any,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(raw, bool):
        raise RuntimeError(f"Thermal printer {name} must be an integer.")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Thermal printer {name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(
            f"Thermal printer {name} must be between {minimum} and {maximum}."
        )
    return value


def get_printer_type() -> str:
    """Return the selected printer implementation."""

    value = os.environ.get("MOMIR_PRINTER_TYPE", "").strip()
    if not value:
        printer = load_local_config().get("printer", {})
        if isinstance(printer, dict):
            value = str(printer.get("type") or "").strip()
    value = value or "photo"
    if value not in PRINTER_TYPES:
        raise RuntimeError(
            "Configured printer type must be 'photo' or 'thermal_58mm'."
        )
    return value


def get_thermal_printer_settings() -> dict[str, Any]:
    """Return validated settings for the 58 mm thermal renderer."""

    printer = load_local_config().get("printer", {})
    if not isinstance(printer, dict):
        printer = {}
    configured = printer.get("thermal", {})
    if configured in (None, ""):
        configured = {}
    if not isinstance(configured, dict):
        raise RuntimeError("Thermal printer settings must be a JSON object.")

    values: dict[str, Any] = {}
    for name, default in DEFAULT_THERMAL_PRINTER_SETTINGS.items():
        raw: Any = os.environ.get(_THERMAL_ENV_VARS[name], "").strip()
        if raw == "":
            raw = configured.get(name, default)
        values[name] = raw

    settings = {
        "columns": _coerce_thermal_integer(
            "columns",
            values["columns"],
            24,
            48,
        ),
        "paper_width_pixels": _coerce_thermal_integer(
            "paper width",
            values["paper_width_pixels"],
            256,
            576,
        ),
        "qr_size_pixels": _coerce_thermal_integer(
            "QR size",
            values["qr_size_pixels"],
            96,
            240,
        ),
        "transport": str(values["transport"] or "mock").strip().lower(),
    }
    if settings["transport"] != "mock":
        raise RuntimeError(
            "Only the thermal 'mock' transport is available until hardware "
            "testing is complete."
        )
    if settings["qr_size_pixels"] > settings["paper_width_pixels"] - 24:
        raise RuntimeError("Thermal QR size must fit within the paper width.")
    return settings


def get_printer_settings() -> dict[str, Any]:
    return {
        "type": get_printer_type(),
        "thermal": get_thermal_printer_settings(),
    }


def _write_local_config(config: dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def save_printer_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Persist printer type and thermal preview settings."""

    if not isinstance(values, dict):
        raise RuntimeError("Printer settings must be a JSON object.")

    printer_type = str(values.get("type") or get_printer_type()).strip()
    if printer_type not in PRINTER_TYPES:
        raise RuntimeError(
            "Printer type must be 'photo' or 'thermal_58mm'."
        )

    supplied_thermal = values.get("thermal", {})
    if supplied_thermal in (None, ""):
        supplied_thermal = {}
    if not isinstance(supplied_thermal, dict):
        raise RuntimeError("Thermal printer settings must be a JSON object.")

    current = get_thermal_printer_settings()
    merged = {**current, **supplied_thermal}
    thermal = {
        "columns": _coerce_thermal_integer(
            "columns",
            merged["columns"],
            24,
            48,
        ),
        "paper_width_pixels": _coerce_thermal_integer(
            "paper width",
            merged["paper_width_pixels"],
            256,
            576,
        ),
        "qr_size_pixels": _coerce_thermal_integer(
            "QR size",
            merged["qr_size_pixels"],
            96,
            240,
        ),
        "transport": str(merged.get("transport") or "mock").strip().lower(),
    }
    if thermal["transport"] != "mock":
        raise RuntimeError(
            "Only the thermal 'mock' transport is available until hardware "
            "testing is complete."
        )
    if thermal["qr_size_pixels"] > thermal["paper_width_pixels"] - 24:
        raise RuntimeError("Thermal QR size must fit within the paper width.")

    config = load_local_config()
    printer = config.get("printer")
    if not isinstance(printer, dict):
        printer = {}
    config["printer"] = printer
    printer["type"] = printer_type
    printer["thermal"] = thermal
    _write_local_config(config)

    return {"type": printer_type, "thermal": thermal}
# MOMIR_THERMAL_PRINTER_FUNCTIONS_END


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
