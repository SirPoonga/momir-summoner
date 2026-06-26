#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo --preserve-env=PATH bash "$0" "$@"
fi

HOTSPOT_CIDR="${MOMIR_HOTSPOT_CIDR:-10.42.0.1/24}"
APP_PORT="${MOMIR_APP_PORT:-5000}"
HOTSPOT_IP="${HOTSPOT_CIDR%/*}"
PORTAL_URL="http://${HOTSPOT_IP}:${APP_PORT}/"
DNSMASQ_CONFIG="/etc/momir-hotspot/dnsmasq.conf"
PORTAL_SCRIPT="/usr/local/sbin/momir-captive-portal.py"
PORTAL_SERVICE="/etc/systemd/system/momir-captive-portal.service"
BACKUP_DIR="/root/momir-captive-portal-backup-$(date +%Y%m%d_%H%M%S)"

if [[ ! -f "$DNSMASQ_CONFIG" ]]; then
  echo "Error: $DNSMASQ_CONFIG was not found." >&2
  echo "Run setup_dual_wifi_hotspot.sh first." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
cp -a "$DNSMASQ_CONFIG" "$BACKUP_DIR/"
[[ -f "$PORTAL_SCRIPT" ]] && cp -a "$PORTAL_SCRIPT" "$BACKUP_DIR/"
[[ -f "$PORTAL_SERVICE" ]] && cp -a "$PORTAL_SERVICE" "$BACKUP_DIR/"

sed -i '/^# BEGIN MOMIR CAPTIVE PORTAL$/,/^# END MOMIR CAPTIVE PORTAL$/d' \
  "$DNSMASQ_CONFIG"

cat >>"$DNSMASQ_CONFIG" <<EOF

# BEGIN MOMIR CAPTIVE PORTAL
host-record=momir.local,${HOTSPOT_IP}
address=/connectivitycheck.gstatic.com/${HOTSPOT_IP}
address=/connectivitycheck.android.com/${HOTSPOT_IP}
address=/connectivitycheck.googleapis.com/${HOTSPOT_IP}
address=/clients3.google.com/${HOTSPOT_IP}
address=/captive.apple.com/${HOTSPOT_IP}
address=/www.msftconnecttest.com/${HOTSPOT_IP}
address=/www.msftncsi.com/${HOTSPOT_IP}
address=/detectportal.firefox.com/${HOTSPOT_IP}
address=/connectivity-check.ubuntu.com/${HOTSPOT_IP}
address=/nmcheck.gnome.org/${HOTSPOT_IP}
# END MOMIR CAPTIVE PORTAL
EOF

cat >"$PORTAL_SCRIPT" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import html
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

BIND_ADDRESS = os.environ.get("MOMIR_PORTAL_BIND", "10.42.0.1")
BIND_PORT = int(os.environ.get("MOMIR_PORTAL_PORT", "80"))
PORTAL_URL = os.environ.get("MOMIR_PORTAL_URL", "http://10.42.0.1:5000/")
UNLOCK_DELAY_SECONDS = int(os.environ.get("MOMIR_PORTAL_UNLOCK_DELAY", "15"))
SESSION_TTL_SECONDS = int(os.environ.get("MOMIR_PORTAL_SESSION_TTL", "43200"))

ANDROID_HOSTS = {
    "connectivitycheck.gstatic.com",
    "connectivitycheck.android.com",
    "connectivitycheck.googleapis.com",
    "clients3.google.com",
}
APPLE_HOSTS = {"captive.apple.com"}
WINDOWS_HOSTS = {"www.msftconnecttest.com", "www.msftncsi.com"}
FIREFOX_HOSTS = {"detectportal.firefox.com"}
LINUX_HOSTS = {"connectivity-check.ubuntu.com", "nmcheck.gnome.org"}
PROBE_HOSTS = (
    ANDROID_HOSTS | APPLE_HOSTS | WINDOWS_HOSTS | FIREFOX_HOSTS | LINUX_HOSTS
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class PortalHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    sessions: ClassVar[dict[str, tuple[float, float]]] = {}

    def log_message(self, fmt: str, *args: object) -> None:
        logging.info("%s %s", self.client_address[0], fmt % args)

    @property
    def host(self) -> str:
        return self.headers.get("Host", "").split(":", 1)[0].lower().rstrip(".")

    def _session_is_released(self, client_ip: str, now: float) -> bool:
        session = self.sessions.get(client_ip)
        if session is None or now >= session[1]:
            self.sessions[client_ip] = (
                now + UNLOCK_DELAY_SECONDS,
                now + SESSION_TTL_SECONDS,
            )
            return False
        return now >= session[0]

    def _send(
        self,
        status: int,
        body: bytes = b"",
        content_type: str = "text/plain; charset=utf-8",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Connection", "close")
        if body:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_header("Content-Length", "0")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _redirect_to_momir(self) -> None:
        safe_url = html.escape(PORTAL_URL, quote=True)
        body = (
            "<!doctype html><html><head>"
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="refresh" content="0;url={safe_url}">'
            "<title>Opening Momir</title></head><body>"
            f'<p><a href="{safe_url}">Open Momir</a></p>'
            "</body></html>"
        ).encode()
        self._send(302, body, "text/html; charset=utf-8", {"Location": PORTAL_URL})

    def _send_probe_success(self) -> None:
        host = self.host
        path = self.path.split("?", 1)[0]

        if host in ANDROID_HOSTS or path.endswith(("/generate_204", "/gen_204")):
            self._send(204)
        elif host in APPLE_HOSTS or path.endswith("/hotspot-detect.html"):
            self._send(
                200,
                b"<HTML><HEAD><TITLE>Success</TITLE></HEAD>"
                b"<BODY>Success</BODY></HTML>",
                "text/html; charset=utf-8",
            )
        elif host in WINDOWS_HOSTS:
            body = b"Microsoft NCSI" if path.endswith("/ncsi.txt") else b"Microsoft Connect Test"
            self._send(200, body, "text/plain")
        elif host in FIREFOX_HOSTS:
            self._send(200, b"success\n", "text/plain")
        else:
            self._send(204)

    def _handle(self) -> None:
        client_ip = self.client_address[0]
        if self.host not in PROBE_HOSTS:
            self._redirect_to_momir()
        elif self._session_is_released(client_ip, time.monotonic()):
            self._send_probe_success()
        else:
            self._redirect_to_momir()

    def do_GET(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._redirect_to_momir()


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    server = ReusableThreadingHTTPServer((BIND_ADDRESS, BIND_PORT), PortalHandler)
    logging.info(
        "Momir captive portal listening on http://%s:%d and redirecting to %s",
        BIND_ADDRESS,
        BIND_PORT,
        PORTAL_URL,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
PY
chmod 755 "$PORTAL_SCRIPT"

cat >"$PORTAL_SERVICE" <<EOF
[Unit]
Description=Momir captive-portal redirector
Requires=momir-hotspot-network.service
After=momir-hotspot-network.service
Wants=momir-phone-app.service
After=momir-phone-app.service

[Service]
Type=simple
Environment=MOMIR_PORTAL_BIND=${HOTSPOT_IP}
Environment=MOMIR_PORTAL_PORT=80
Environment=MOMIR_PORTAL_URL=${PORTAL_URL}
Environment=MOMIR_PORTAL_UNLOCK_DELAY=15
Environment=MOMIR_PORTAL_SESSION_TTL=43200
ExecStart=/usr/bin/python3 ${PORTAL_SCRIPT}
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

/usr/sbin/dnsmasq --test --conf-file="$DNSMASQ_CONFIG"

systemctl daemon-reload
systemctl enable momir-captive-portal.service
systemctl restart momir-dnsmasq.service
systemctl restart momir-captive-portal.service
sleep 3

echo
echo "=== CAPTIVE PORTAL ==="
systemctl --no-pager --full status momir-captive-portal.service || true

echo
echo "=== REDIRECT TEST ==="
curl --max-time 5 -sS -D - -o /dev/null \
  -H "Host: connectivitycheck.gstatic.com" \
  "http://${HOTSPOT_IP}/generate_204" || true

echo
echo "Forget and reconnect to the Momir Wi-Fi network to trigger the portal."
echo "Manual address: $PORTAL_URL"
echo "Backup: $BACKUP_DIR"
