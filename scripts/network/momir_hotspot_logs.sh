#!/usr/bin/env bash
set -Eeuo pipefail

LINES="${1:-100}"

if [[ ! "$LINES" =~ ^[0-9]+$ ]]; then
  echo "Usage: $0 [number-of-lines]" >&2
  exit 2
fi

journalctl \
  -u momir-hotspot-network.service \
  -u momir-hostapd.service \
  -u momir-dnsmasq.service \
  -u momir-captive-portal.service \
  -n "$LINES" \
  --no-pager
