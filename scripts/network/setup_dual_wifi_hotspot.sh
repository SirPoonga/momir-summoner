#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo --preserve-env=PATH bash "$0" "$@"
fi

AP_IF="${MOMIR_AP_IF:-wlan0}"
UPSTREAM_IF="${MOMIR_UPSTREAM_IF:-wlan1}"
SSID="${MOMIR_HOTSPOT_SSID:-Momir}"
HOTSPOT_CIDR="${MOMIR_HOTSPOT_CIDR:-10.42.0.1/24}"
COUNTRY="${MOMIR_WIFI_COUNTRY:-US}"
CHANNEL="${MOMIR_WIFI_CHANNEL:-6}"
CONFIG_DIR="/etc/momir-hotspot"

HOTSPOT_IP="${HOTSPOT_CIDR%/*}"
if [[ "$HOTSPOT_IP" == "$HOTSPOT_CIDR" ]]; then
  echo "Error: MOMIR_HOTSPOT_CIDR must include a prefix, such as 10.42.0.1/24." >&2
  exit 1
fi

usage() {
  cat <<EOF
Configure a Raspberry Pi dual-Wi-Fi setup for Momir.

Defaults:
  Built-in access point: $AP_IF
  USB internet adapter: $UPSTREAM_IF
  Hotspot SSID:          $SSID
  Hotspot address:       $HOTSPOT_CIDR
  Wi-Fi country:         $COUNTRY
  Wi-Fi channel:         $CHANNEL

Override defaults with environment variables:
  MOMIR_AP_IF
  MOMIR_UPSTREAM_IF
  MOMIR_HOTSPOT_SSID
  MOMIR_HOTSPOT_CIDR
  MOMIR_WIFI_COUNTRY
  MOMIR_WIFI_CHANNEL

Example:
  MOMIR_HOTSPOT_SSID=GameBox $0
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

for command in nmcli ip systemctl awk sed grep rfkill; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Error: required command not found: $command" >&2
    exit 1
  }
done

if [[ ! -d "/sys/class/net/$AP_IF" ]]; then
  echo "Error: access-point interface '$AP_IF' does not exist." >&2
  exit 1
fi

if [[ ! -d "/sys/class/net/$UPSTREAM_IF" ]]; then
  echo "Error: upstream interface '$UPSTREAM_IF' does not exist." >&2
  exit 1
fi

if ! iw list | sed -n '/Supported interface modes:/,/Band/p' | grep -q '^[[:space:]]*\* AP$'; then
  echo "Error: no Wi-Fi adapter reports AP mode support." >&2
  exit 1
fi

echo "Momir dual-Wi-Fi configuration"
echo "  Access point: $AP_IF"
echo "  Upstream:     $UPSTREAM_IF"
echo "  SSID:         $SSID"
echo "  Address:      $HOTSPOT_CIDR"
echo

IFS= read -r -s -p "Choose the Momir Wi-Fi password (8-63 characters): " HOTSPOT_PASS
echo
if (( ${#HOTSPOT_PASS} < 8 || ${#HOTSPOT_PASS} > 63 )); then
  echo "Error: the Wi-Fi password must contain 8-63 characters." >&2
  exit 1
fi

echo "Installing required packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  hostapd dnsmasq iptables wpasupplicant iw rfkill curl

HOTSPOT_PSK="$(
  wpa_passphrase "$SSID" "$HOTSPOT_PASS" |
    awk '$1 ~ /^psk=/ && $0 !~ /"/ {sub(/^[[:space:]]*psk=/, ""); print; exit}'
)"
unset HOTSPOT_PASS

if [[ ! "$HOTSPOT_PSK" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "Error: failed to derive the Wi-Fi PSK." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/root/momir-hotspot-backup-$STAMP"
mkdir -p "$BACKUP_DIR" "$CONFIG_DIR"

for path in \
  /etc/NetworkManager/conf.d/30-momir-hotspot.conf \
  "$CONFIG_DIR/hostapd.conf" \
  "$CONFIG_DIR/dnsmasq.conf" \
  /etc/sysctl.d/90-momir-hotspot.conf \
  /usr/local/sbin/momir-hotspot-network \
  /etc/systemd/system/momir-hotspot-network.service \
  /etc/systemd/system/momir-hostapd.service \
  /etc/systemd/system/momir-dnsmasq.service
do
  if [[ -e "$path" ]]; then
    cp -a --parents "$path" "$BACKUP_DIR/"
  fi
done

# Stop any NetworkManager connection currently using the access-point interface.
ACTIVE_CONNECTION="$(
  nmcli -t -f NAME,DEVICE connection show --active |
    awk -F: -v device="$AP_IF" '$2 == device {print $1; exit}'
)"
if [[ -n "$ACTIVE_CONNECTION" ]]; then
  nmcli connection down "$ACTIVE_CONNECTION" 2>/dev/null || true
fi

# Disable any old NetworkManager-created hotspot with the standard name.
nmcli connection modify "Momir-Hotspot" connection.autoconnect no 2>/dev/null || true
nmcli connection down "Momir-Hotspot" 2>/dev/null || true

install -d -m 0755 /etc/NetworkManager/conf.d
cat >/etc/NetworkManager/conf.d/30-momir-hotspot.conf <<EOF
[keyfile]
unmanaged-devices=interface-name:${AP_IF}
EOF

# Apply the setting without restarting NetworkManager, preserving wlan1 and SSH.
nmcli device set "$AP_IF" managed no || true

cat >"$CONFIG_DIR/hostapd.conf" <<EOF
country_code=${COUNTRY}
interface=${AP_IF}
driver=nl80211

ssid=${SSID}
hw_mode=g
channel=${CHANNEL}
ieee80211n=1
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0

wpa=2
wpa_psk=${HOTSPOT_PSK}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
chmod 600 "$CONFIG_DIR/hostapd.conf"
unset HOTSPOT_PSK

cat >"$CONFIG_DIR/dnsmasq.conf" <<EOF
interface=${AP_IF}
bind-dynamic
listen-address=${HOTSPOT_IP}

dhcp-range=10.42.0.20,10.42.0.200,255.255.255.0,24h
dhcp-option=option:router,${HOTSPOT_IP}
dhcp-option=option:dns-server,${HOTSPOT_IP}

domain-needed
bogus-priv
no-resolv
server=1.1.1.1
server=8.8.8.8
EOF
chmod 644 "$CONFIG_DIR/dnsmasq.conf"

cat >/etc/sysctl.d/90-momir-hotspot.conf <<'EOF'
net.ipv4.ip_forward=1
EOF
sysctl --system >/dev/null

cat >/usr/local/sbin/momir-hotspot-network <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail

AP_IF="${AP_IF}"
UPSTREAM_IF="${UPSTREAM_IF}"
HOTSPOT_CIDR="${HOTSPOT_CIDR}"

start_hotspot_network() {
  rfkill unblock wifi || true
  nmcli device set "\$AP_IF" managed no || true

  ip link set "\$AP_IF" down || true
  ip address flush dev "\$AP_IF" || true
  ip address add "\$HOTSPOT_CIDR" dev "\$AP_IF"
  ip link set "\$AP_IF" up

  sysctl -w net.ipv4.ip_forward=1 >/dev/null

  iptables -t nat -C POSTROUTING -o "\$UPSTREAM_IF" -j MASQUERADE 2>/dev/null ||
    iptables -t nat -A POSTROUTING -o "\$UPSTREAM_IF" -j MASQUERADE

  iptables -C FORWARD -i "\$AP_IF" -o "\$UPSTREAM_IF" -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -i "\$AP_IF" -o "\$UPSTREAM_IF" -j ACCEPT

  iptables -C FORWARD -i "\$UPSTREAM_IF" -o "\$AP_IF" \
    -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -i "\$UPSTREAM_IF" -o "\$AP_IF" \
      -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
}

stop_hotspot_network() {
  iptables -t nat -D POSTROUTING -o "\$UPSTREAM_IF" -j MASQUERADE 2>/dev/null || true
  iptables -D FORWARD -i "\$AP_IF" -o "\$UPSTREAM_IF" -j ACCEPT 2>/dev/null || true
  iptables -D FORWARD -i "\$UPSTREAM_IF" -o "\$AP_IF" \
    -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true

  ip address flush dev "\$AP_IF" 2>/dev/null || true
  ip link set "\$AP_IF" down 2>/dev/null || true
}

case "\${1:-start}" in
  start) start_hotspot_network ;;
  stop) stop_hotspot_network ;;
  restart)
    stop_hotspot_network
    start_hotspot_network
    ;;
  *)
    echo "Usage: \$0 {start|stop|restart}" >&2
    exit 2
    ;;
esac
EOF
chmod 755 /usr/local/sbin/momir-hotspot-network

cat >/etc/systemd/system/momir-hotspot-network.service <<'EOF'
[Unit]
Description=Momir hotspot network configuration
After=NetworkManager.service
Wants=NetworkManager.service momir-hostapd.service momir-dnsmasq.service
Before=momir-hostapd.service momir-dnsmasq.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/momir-hotspot-network start
ExecStop=/usr/local/sbin/momir-hotspot-network stop

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/momir-hostapd.service <<EOF
[Unit]
Description=Momir Wi-Fi access point
Requires=momir-hotspot-network.service
After=momir-hotspot-network.service

[Service]
Type=simple
ExecStart=/usr/sbin/hostapd ${CONFIG_DIR}/hostapd.conf
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/momir-dnsmasq.service <<EOF
[Unit]
Description=Momir hotspot DHCP and DNS
Requires=momir-hotspot-network.service
After=momir-hotspot-network.service

[Service]
Type=simple
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --conf-file=${CONFIG_DIR}/dnsmasq.conf
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Dedicated Momir services use isolated configuration files.
systemctl disable --now hostapd.service 2>/dev/null || true
systemctl disable --now dnsmasq.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable \
  momir-hotspot-network.service \
  momir-hostapd.service \
  momir-dnsmasq.service

systemctl restart momir-hotspot-network.service
sleep 2
systemctl restart momir-hostapd.service momir-dnsmasq.service
sleep 5

echo
echo "=== MOMIR HOTSPOT STATUS ==="
systemctl --no-pager --full status \
  momir-hotspot-network.service \
  momir-hostapd.service \
  momir-dnsmasq.service || true

echo
echo "=== ADDRESSES ==="
ip -br address show "$AP_IF" || true
ip -br address show "$UPSTREAM_IF" || true

echo
echo "=== ACCESS POINT ==="
iw dev "$AP_IF" info || true

echo
echo "Configuration backup: $BACKUP_DIR"
echo
echo "Connect to Wi-Fi '$SSID' and open http://${HOTSPOT_IP}:5000"
