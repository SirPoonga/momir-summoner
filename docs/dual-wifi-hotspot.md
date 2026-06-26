# Dual-Wi-Fi hotspot

Momir can operate as a self-contained Wi-Fi appliance while retaining an optional internet connection for card and software updates.

## Interface roles

| Interface | Role |
| --- | --- |
| `wlan0` | Built-in Raspberry Pi Wi-Fi, permanently broadcasting the `Momir` network |
| `wlan1` | USB Wi-Fi adapter, connected to home Wi-Fi or another upstream network |

The default hotspot address is `10.42.0.1`. After joining the `Momir` network, open:

```text
http://10.42.0.1:5000
```

The optional captive portal normally opens the interface automatically. The operating system may show a **Sign in to Momir** notification instead of opening it immediately.

## Requirements

- Raspberry Pi with built-in Wi-Fi
- USB Wi-Fi adapter recognized as `wlan1`
- USB adapter connected to the internet before converting `wlan0`
- Built-in adapter capable of AP mode

Check the interfaces:

```bash
nmcli device status
iw dev
```

The intended starting state is:

```text
wlan0  connected     existing Wi-Fi connection
wlan1  connected     upstream Wi-Fi connection
```

Before changing `wlan0`, confirm SSH works through the address assigned to `wlan1`.

## Connect the USB adapter to an upstream network

Scan from `wlan1`:

```bash
nmcli device wifi list ifname wlan1
```

Create a connection without placing the password in shell history:

```bash
sudo nmcli --ask device wifi connect \
  "YOUR_WIFI_NAME" \
  ifname wlan1 \
  name "momir-upstream"
```

Verify internet access:

```bash
ping -I wlan1 -c 3 1.1.1.1
```

## Install the hotspot

From the repository root:

```bash
scripts/network/setup_dual_wifi_hotspot.sh
```

The script prompts for the `Momir` Wi-Fi password and configures:

- `hostapd` on `wlan0`
- DHCP and DNS through a dedicated `dnsmasq` service
- `10.42.0.1/24` on `wlan0`
- Routing and NAT through `wlan1`
- Automatic startup through systemd

The Wi-Fi password is converted to a PSK and is not stored in the repository.

## Install automatic UI opening

After the hotspot works:

```bash
scripts/network/setup_captive_portal.sh
```

Forget the old `Momir` network on the phone and reconnect. The phone should open Momir automatically or offer a captive-portal notification.

Manual fallback:

```text
http://10.42.0.1:5000
```

`http://momir.local` may also work while connected directly to the Momir hotspot, but the numeric address is the reliable fallback.

## Helper commands

Show status:

```bash
scripts/network/momir_hotspot_status.sh
```

Restart the hotspot services:

```bash
scripts/network/momir_hotspot_restart.sh
```

Show recent logs:

```bash
scripts/network/momir_hotspot_logs.sh
```

Specify a different number of log lines:

```bash
scripts/network/momir_hotspot_logs.sh 250
```

## Configuration overrides

The setup scripts use these defaults:

```text
MOMIR_AP_IF=wlan0
MOMIR_UPSTREAM_IF=wlan1
MOMIR_HOTSPOT_SSID=Momir
MOMIR_HOTSPOT_CIDR=10.42.0.1/24
MOMIR_WIFI_COUNTRY=US
MOMIR_WIFI_CHANNEL=6
MOMIR_APP_PORT=5000
```

Set environment variables before running a setup script to override them. For example:

```bash
MOMIR_HOTSPOT_SSID=Momir-Game \
MOMIR_WIFI_CHANNEL=11 \
scripts/network/setup_dual_wifi_hotspot.sh
```

## Phone-hotspot limitation

A phone generally cannot provide its own Wi-Fi hotspot and simultaneously join the Pi's `Momir` Wi-Fi network. During an update through the phone hotspot, access Momir through the Pi's `wlan1` address. After the update, turn off the phone hotspot and reconnect the phone to `Momir`.

## Troubleshooting

Confirm that all services are active:

```bash
scripts/network/momir_hotspot_status.sh
```

Check the logs:

```bash
scripts/network/momir_hotspot_logs.sh 200
```

Confirm the access point is active:

```bash
iw dev wlan0 info
```

Expected fields include:

```text
type AP
ssid Momir
```

Confirm the hotspot address:

```bash
ip -br address show wlan0
```

Expected address:

```text
10.42.0.1/24
```

A restart briefly disconnects hotspot clients but should not interrupt SSH through `wlan1`:

```bash
scripts/network/momir_hotspot_restart.sh
```
