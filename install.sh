#!/usr/bin/env bash
set -Eeuo pipefail

SKIP_PACKAGES=0
SKIP_UPDATE=0
NO_SERVICE=0

usage() {
    cat <<'USAGE'
Usage: ./install.sh [options]

Options:
  --skip-system-packages  Do not run apt to install OS packages.
  --skip-card-update      Create the database but do not download cards now.
  --no-service            Do not install or start the systemd service.
  -h, --help              Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-system-packages) SKIP_PACKAGES=1 ;;
        --skip-card-update) SKIP_UPDATE=1 ;;
        --no-service) NO_SERVICE=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [[ $EUID -eq 0 ]]; then
    echo "ERROR: Run install.sh as the regular account that should own Momir Summoner." >&2
    echo "The script will use sudo only for system-level changes." >&2
    exit 1
fi

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="$(id -un)"
APP_GROUP="$(id -gn)"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
SERVICE="momir-summoner.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE"
SUDOERS_PATH="/etc/sudoers.d/momir-summoner-l2ping"

if [[ "$APP_DIR" =~ [[:space:]] ]]; then
    echo "ERROR: Install path may not contain spaces: $APP_DIR" >&2
    exit 1
fi

if [[ $SKIP_PACKAGES -eq 0 ]]; then
    echo "Installing operating-system packages..."
    sudo apt-get update
    sudo apt-get install -y \
        python3-venv \
        python3-pip \
        bluez \
        obexftp \
        curl \
        fonts-dejavu-core \
        avahi-daemon
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required." >&2
    exit 1
fi
if ! command -v obexftp >/dev/null 2>&1; then
    echo "WARNING: obexftp was not found. Rendering works, but printing will not."
fi

cd "$APP_DIR"
mkdir -p prints/previews backups data

if [[ ! -f config.local.json ]]; then
    cp config.example.json config.local.json
    chmod 600 config.local.json
    echo "Created local configuration: $APP_DIR/config.local.json"
    echo "Set printer.bluetooth_address before attempting to print."
else
    chmod 600 config.local.json
    echo "Keeping existing local configuration: $APP_DIR/config.local.json"
fi

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi

VENV_PYTHON="$APP_DIR/venv/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt

"$VENV_PYTHON" - <<'PY'
from db import connect

conn = connect()
conn.close()
print("Database schema initialized.")
PY

if [[ $SKIP_UPDATE -eq 0 ]]; then
    echo "Downloading the initial local card database..."
    if ! "$VENV_PYTHON" update_cards.py; then
        echo "WARNING: Initial card download failed." >&2
        echo "The application will still be installed. Run this later:" >&2
        echo "  ./scripts/update_momir_cards.sh" >&2
    fi
fi

if [[ $NO_SERVICE -eq 0 ]]; then
    sed \
        -e "s|@APP_USER@|$APP_USER|g" \
        -e "s|@APP_GROUP@|$APP_GROUP|g" \
        -e "s|@APP_HOME@|$APP_HOME|g" \
        -e "s|@APP_DIR@|$APP_DIR|g" \
        systemd/momir-summoner.service.in \
        | sudo tee "$SERVICE_PATH" >/dev/null

    L2PING="$(command -v l2ping || true)"
    if [[ -n "$L2PING" ]]; then
        echo "$APP_USER ALL=(root) NOPASSWD: $L2PING" \
            | sudo tee "$SUDOERS_PATH" >/dev/null
        sudo chmod 440 "$SUDOERS_PATH"
        sudo visudo -cf "$SUDOERS_PATH" >/dev/null
    else
        echo "WARNING: l2ping was not found; printer status probing will be limited."
    fi

    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE"

    READY=0
    for _ in $(seq 1 45); do
        if curl --fail --silent "http://127.0.0.1:5000/api/status" >/tmp/momir_install_status.json 2>/dev/null; then
            READY=1
            break
        fi
        sleep 1
    done

    if [[ $READY -ne 1 ]]; then
        echo "ERROR: The service did not answer within 45 seconds." >&2
        sudo systemctl --no-pager --full status "$SERVICE" || true
        exit 1
    fi

    cat /tmp/momir_install_status.json
    echo
fi

HOSTNAME_NOW="$(hostname)"
echo
echo "Momir Summoner installation complete."
echo "Application directory: $APP_DIR"
echo "Local configuration: $APP_DIR/config.local.json"
echo "Open: http://${HOSTNAME_NOW}.local:5000"
echo "Fallback: http://<pi-address>:5000"
