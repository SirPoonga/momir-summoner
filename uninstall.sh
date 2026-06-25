#!/usr/bin/env bash
set -Eeuo pipefail

PURGE_DATA=0
if [[ "${1:-}" == "--purge-data" ]]; then
    PURGE_DATA=1
elif [[ $# -gt 0 ]]; then
    echo "Usage: ./uninstall.sh [--purge-data]" >&2
    exit 2
fi

if [[ $EUID -eq 0 ]]; then
    echo "ERROR: Run uninstall.sh as the regular application owner." >&2
    exit 1
fi

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="momir-summoner.service"

sudo systemctl disable --now "$SERVICE" 2>/dev/null || true
sudo rm -f "/etc/systemd/system/$SERVICE"
sudo rm -f "/etc/sudoers.d/momir-summoner-l2ping"
sudo systemctl daemon-reload
sudo systemctl reset-failed "$SERVICE" 2>/dev/null || true

echo "Removed the Momir Summoner systemd service."

if [[ $PURGE_DATA -eq 1 ]]; then
    rm -rf \
        "$APP_DIR/venv" \
        "$APP_DIR/prints" \
        "$APP_DIR/backups" \
        "$APP_DIR/data"
    rm -f \
        "$APP_DIR/momir.db" \
        "$APP_DIR/momir.db-shm" \
        "$APP_DIR/momir.db-wal" \
        "$APP_DIR/config.local.json"
    echo "Removed local environment, database, configuration, backups, and output."
else
    echo "Application files and local data were preserved."
    echo "Use --purge-data to remove generated/local files too."
fi
