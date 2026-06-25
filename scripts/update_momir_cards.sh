#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SERVICE="${MOMIR_SERVICE_NAME:-momir-summoner.service}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${APP_DIR}/backups/card_update_${STAMP}"
PYTHON="${APP_DIR}/venv/bin/python"
DB="${APP_DIR}/momir.db"

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Python environment not found: $PYTHON" >&2
    echo "Run ./install.sh first." >&2
    exit 1
fi
if [[ ! -f "${APP_DIR}/update_cards.py" ]]; then
    echo "ERROR: Updater not found: ${APP_DIR}/update_cards.py" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

service_exists=0
if systemctl list-unit-files "$SERVICE" --no-legend 2>/dev/null | grep -q "^${SERVICE}"; then
    service_exists=1
    echo "Stopping $SERVICE..."
    sudo systemctl stop "$SERVICE"
fi

if [[ -f "$DB" ]]; then
    cp -a "$DB" "$BACKUP_DIR/momir.db"
fi
echo "Database backup: $BACKUP_DIR"

restore_and_restart() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo "Card update failed. Restoring the previous database..." >&2
        if [[ -f "$BACKUP_DIR/momir.db" ]]; then
            cp -a "$BACKUP_DIR/momir.db" "$DB"
        fi
    fi
    if [[ $service_exists -eq 1 ]]; then
        sudo systemctl start "$SERVICE" || true
    fi
    return $exit_code
}
trap restore_and_restart EXIT

cd "$APP_DIR"
echo "Downloading the latest Scryfall creature list..."
"$PYTHON" "$APP_DIR/update_cards.py" "$@"

if [[ $service_exists -eq 1 ]]; then
    sudo systemctl start "$SERVICE"
fi
trap - EXIT

if [[ $service_exists -eq 1 ]]; then
    READY=0
    for _ in $(seq 1 45); do
        if curl --fail --silent "http://127.0.0.1:5000/api/status" >/tmp/momir_status.json 2>/dev/null; then
            READY=1
            break
        fi
        sleep 1
    done

    if [[ "$READY" -ne 1 ]]; then
        echo "WARNING: Database updated, but the web app did not answer within 45 seconds." >&2
        sudo systemctl --no-pager --full status "$SERVICE" || true
        exit 1
    fi

    cat /tmp/momir_status.json
    echo
fi

echo "Card update finished successfully."
