#!/usr/bin/env bash
set -u

AP_IF="${MOMIR_AP_IF:-wlan0}"
UPSTREAM_IF="${MOMIR_UPSTREAM_IF:-wlan1}"
HOTSPOT_IP="${MOMIR_HOTSPOT_IP:-10.42.0.1}"
APP_PORT="${MOMIR_APP_PORT:-5000}"

echo "=== SERVICES ==="
for service in \
  momir-hotspot-network.service \
  momir-hostapd.service \
  momir-dnsmasq.service \
  momir-captive-portal.service \
  momir-phone-app.service
do
  printf "%-38s %s\n" "$service" "$(systemctl is-active "$service" 2>/dev/null || true)"
done

echo
echo "=== INTERFACES ==="
ip -br address show "$AP_IF" 2>/dev/null || true
ip -br address show "$UPSTREAM_IF" 2>/dev/null || true

echo
echo "=== ACCESS POINT ==="
iw dev "$AP_IF" info 2>/dev/null || true

echo
echo "=== NETWORKMANAGER ==="
nmcli -f DEVICE,TYPE,STATE,CONNECTION device status 2>/dev/null || true

echo
echo "=== ROUTES ==="
ip route

echo
echo "=== MOMIR UI ==="
curl --max-time 5 -sS -o /dev/null -w \
  "http://${HOTSPOT_IP}:${APP_PORT} -> HTTP %{http_code}\n" \
  "http://${HOTSPOT_IP}:${APP_PORT}" || true

echo
echo "=== CONNECTED HOTSPOT CLIENTS ==="
ip neigh show dev "$AP_IF" 2>/dev/null || true
