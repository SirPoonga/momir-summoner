#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

systemctl restart momir-hotspot-network.service
sleep 2
systemctl restart momir-hostapd.service momir-dnsmasq.service

if systemctl list-unit-files momir-captive-portal.service >/dev/null 2>&1; then
  systemctl restart momir-captive-portal.service
fi

sleep 3
"$(dirname "$0")/momir_hotspot_status.sh"
