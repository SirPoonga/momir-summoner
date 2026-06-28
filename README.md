# Momir Summoner

Momir Summoner is a Raspberry Pi-hosted web application for running a physical **Momir Vig-style** game. A phone, tablet, or computer opens the web interface, selects a mana value, summons a random creature, displays a locally generated card preview, and sends the card to a supported printer.

The Raspberry Pi performs the application, database, rendering, and printing work. The phone or other device is only used as the controller.

> [!NOTE]
> Momir Summoner can run on a normal Wi-Fi network or on the tested dual-Wi-Fi setup. In the dual-Wi-Fi configuration, the Raspberry Pi's built-in adapter (`wlan0`) provides the permanent `Momir` hotspot at `10.42.0.1`, while a USB adapter (`wlan1`) connects the Pi to an internet-enabled Wi-Fi network.

## Current Features

- Mobile-friendly gameplay interface
- Dedicated Settings page for printer status, network information, card-database statistics and updates, and system status
- Installable home-screen/PWA icon named **Momir Summoner** for phones and tablets
- Compact printer-readiness icon in the gameplay header
- Mana values 1 through 16
- Random front-face creature selection by mana value
- Local SQLite card database
- Card search and locally generated previews
- Summon and resummon controls
- Printing through a supported Bluetooth printer
- Printed-card tracking
- Manual **Mark as Printed** control
- Printed-card indicator beside cards already marked as printed
- Front and back viewing for supported double-faced cards
- Front and back printing for supported double-faced cards
- Local card information and rules pages
- Locally stored reverse-face card data
- Card database updates using Scryfall bulk data
- Printed-card history preserved when the card database is updated
- No downloaded or cached official card artwork
- Local configuration for printer and web settings
- Per-printer left, top, right, and bottom margin calibration
- Automated tests and GitHub Actions validation

## Hardware

<!-- hardware-used:start -->
### Hardware used in the tested build

These are the specific components used for the portable Raspberry Pi 3 and thermal-printer setup:

- [58 mm Bluetooth thermal receipt printer](https://www.amazon.com/dp/B0CDLX1DR9)
- [Portable battery pack](https://www.amazon.com/dp/B00ME3ZH7C)
- [USB Wi-Fi adapter](https://www.amazon.com/dp/B008IFXQFU)
- [Short USB power cable](https://www.amazon.com/dp/B013G4EAEI)
- [Raspberry Pi 3 Model B](https://www.amazon.com/dp/B07BDR5PDW)
- [Raspberry Pi 3 case](https://www.amazon.com/dp/B07D5FVLGN)

Product listings and availability may change.
<!-- hardware-used:end -->

### Required

- Raspberry Pi with Wi-Fi and Bluetooth
- microSD card
- Reliable Raspberry Pi power supply
- Supported Bluetooth photo printer
- Smartphone, tablet, or computer with a web browser
- Wi-Fi network shared by the Raspberry Pi and controller device
- Internet connectivity for initial setup and card-database updates

### Optional

- Tailscale account for reliable private addressing
- USB Wi-Fi adapter for the tested dual-Wi-Fi configuration (`wlan1` internet uplink while `wlan0` hosts the `Momir` network)

The current implementation has been tested with a Polaroid Mint-compatible Bluetooth photo printer. The print transport sends generated JPEG files through Bluetooth OBEX FTP. Supporting another printer may require changes to the renderer or print transport.

## Software Requirements

- Raspberry Pi OS or another Debian-based Linux distribution
- Python 3.11 or newer
- Python virtual-environment support
- SQLite
- BlueZ Bluetooth utilities
- OBEX FTP utilities
- Git

## Prepare Raspberry Pi OS

Use Raspberry Pi Imager to install Raspberry Pi OS. For the simplest setup, use these operating-system customization settings:

- **Hostname:** `momir`
- **Username:** `momir`
- **Password:** Choose your own secure password
- **Enable SSH:** Yes, using password authentication
- **Wireless LAN:** Enter the Wi-Fi network and password the Raspberry Pi should use

The hostname and username are recommendations rather than hard requirements. The installer detects the current user and installation path.

> [!IMPORTANT]
> Choose a unique password during setup. Do not use `momir` as the password, and do not publish the password in the repository or documentation.

On supported local networks, the interface should be available at:

```text
http://momir.local:5000
```

If that address does not work, use the Raspberry Pi's local IP address:

```text
http://<raspberry-pi-ip>:5000
```

## Installation

### 1. Clone the repository

Clone the repository as the regular Linux account that should own and run the application:

```bash
git clone <repository-url> ~/momir
cd ~/momir
```

Replace `<repository-url>` with the HTTPS or SSH address of this repository.

### 2. Run the installer

```bash
chmod +x install.sh
./install.sh
```

The installer:

1. Installs required Debian packages.
2. Creates a Python virtual environment.
3. Installs Python dependencies.
4. Creates `config.local.json`.
5. Initializes and downloads the local card database.
6. Generates a systemd service for the current user and repository path.
7. Starts and verifies the web application.

Useful installer options:

```bash
./install.sh --skip-card-update
./install.sh --skip-system-packages
./install.sh --no-service
```

Use `--skip-card-update` when internet access is temporarily unavailable. The database can be downloaded later.

## Configure the Printer

The installer creates:

```text
config.local.json
```

Edit that file and enter the printer's Bluetooth address:

```json
{
  "printer": {
    "bluetooth_address": "AA:BB:CC:DD:EE:FF",
    "channel": "4",
    "margins": {
      "left": 25,
      "top": 45,
      "right": 25,
      "bottom": 40
    }
  },
  "web": {
    "host": "0.0.0.0",
    "port": 5000,
    "local_base_url": "http://momir.local:5000"
  }
}
```


Printer margins are measured in pixels on the 450 x 730 printer canvas and are
stored inside the printer configuration because calibration can vary by printer.
The defaults preserve the original calibrated layout: left `25`, top `45`,
right `25`, and bottom `40`. Changing a margin automatically invalidates cached
previews and printer images so the next request uses the new calibration.

Margins can also be adjusted from the web interface at `http://momir.local:5000/settings`; saved values are written to the active printer entry in `config.local.json`.


Printer margins can be adjusted on the **Settings** page. The Left, Top,
Right, and Bottom values are stored under `printer.margins` in
`config.local.json` and apply to the currently configured printer. The default
calibration is 25, 45, 25, and 40 pixels respectively.

### Find the Bluetooth address

Turn on the printer and run:

```bash
bluetoothctl
```

At the `bluetoothctl` prompt:

```text
power on
scan on
devices
```

Record the address shown next to the printer, then stop scanning and exit:

```text
scan off
quit
```

Do not commit `config.local.json`. It may contain machine-specific device information.

Restart the service after changing configuration:

```bash
sudo systemctl restart momir-summoner.service
```

### Environment-variable overrides

Environment variables override values in `config.local.json`:

```text
MOMIR_CONFIG_PATH
MOMIR_PRINTER_ADDRESS
MOMIR_PRINTER_CHANNEL
MOMIR_PRINTER_MARGIN_LEFT
MOMIR_PRINTER_MARGIN_TOP
MOMIR_PRINTER_MARGIN_RIGHT
MOMIR_PRINTER_MARGIN_BOTTOM
MOMIR_HOST
MOMIR_PORT
MOMIR_LOCAL_BASE_URL
```

## Open the Interface

Open either:

```text
http://momir.local:5000
```

or:

```text
http://<raspberry-pi-ip>:5000
```

Find the Raspberry Pi's current addresses with:

```bash
hostname -I
```

The first address shown is usually the local IPv4 address.

The root address opens the gameplay page. Search, mana selection, summoning, card previews, printing controls, and printed-card controls remain on this page.

Use the gear icon in the gameplay header to open **Settings**. Settings can also be opened directly at:

```text
http://momir.local:5000/settings
```

The printer icon on the left side of the gameplay title shows current readiness:

- **Green:** the configured printer answered the readiness check
- **Gray:** the printer is off, unavailable, not configured, or otherwise not ready

Tap the printer icon to open Settings and view the detailed printer-status message. This header icon is separate from the printed-card indicator shown beside a card that has already been marked as printed.

## Connecting from a Phone or Other Device

### Option 1: Shared Wi-Fi Network

This is the simplest setup.

1. Connect the Raspberry Pi to Wi-Fi.
2. Connect the phone or controller device to the same Wi-Fi network.
3. Open `http://momir.local:5000`.
4. If the hostname does not work, use the Raspberry Pi's local IP address.

Some managed, guest, hotel, or store networks block communication between connected devices. If both devices are connected but the page does not open, client isolation may be enabled.

### Option 2: Phone Hotspot

A phone hotspot can provide a self-contained setup for a game store or event.

1. Turn on the phone's hotspot.
2. Connect the Raspberry Pi to that hotspot.
3. Open the hotspot's connected-device list.
4. Find the IP address assigned to the Raspberry Pi.
5. Open that address in the phone's browser:

```text
http://<raspberry-pi-ip>:5000
```

No additional networking software is required when the phone shows the assigned IP address and permits communication with connected clients.

Some phones show only a device name or hardware address. In that case, use Tailscale or wait for the documented USB Wi-Fi adapter configuration.

### Option 3: Tailscale

Tailscale gives the Raspberry Pi a stable private address that can be used from another device signed into the same Tailscale network. Router port forwarding is not required.

Only basic Tailscale device connectivity is needed. An exit node and subnet router are not required.

Install Tailscale on the Raspberry Pi:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Open the authentication link printed in the terminal and sign in.

Verify the connection:

```bash
tailscale status
tailscale ip -4
```

Install the official Tailscale application on the phone or controller device, sign in to the same Tailscale account, and enable the connection.

Open Momir Summoner using the Raspberry Pi's Tailscale address:

```text
http://<tailscale-ip>:5000
```

MagicDNS may also permit the Tailscale device name:

```text
http://<tailscale-device-name>:5000
```

> [!IMPORTANT]
> Do not expose port `5000` directly to the public internet. Do not configure router port forwarding for this application. Use a trusted local network or Tailscale.

### Option 4: USB Wi-Fi Adapter

**Documentation pending hardware testing.**

The planned configuration will use the Raspberry Pi's built-in Wi-Fi and a USB Wi-Fi adapter to provide a predictable portable network arrangement.

Final instructions will be added only after confirming:

- A reliable adapter and chipset
- Which interface connects to internet or venue Wi-Fi
- Which interface provides the private controller network
- NetworkManager connection priorities
- Routing behavior
- Reboot behavior
- Recovery steps that do not risk losing SSH access

Until those tests are complete, use shared Wi-Fi, a phone hotspot, or Tailscale.

## Using Momir Summoner

1. Open the gameplay page.
2. Check the printer-readiness icon in the header before printing. Green means ready; gray means unavailable or not ready.
3. Select the required mana value.
4. Summon a creature.
5. Review the generated card preview and information.
6. Print the selected card when needed.
7. Use **View Back** or **Print Back** when a supported card has a reverse face.
8. Use **Mark as Printed** when a card was printed outside the normal print action.
9. Use the printed-card indicator beside the card name to avoid unnecessary duplicate prints.
10. Use Search on the gameplay page to locate a specific card in the local database.
11. Use the gear icon to open Settings for detailed printer status, network information, card-database controls, and system status.

## Updating the Card Database

Open **Settings → Card Database** and select **Update Cards**, or run:

```bash
./scripts/update_momir_cards.sh
```

The updater:

- Retrieves current English paper-card data from Scryfall
- Keeps only cards whose front face is a creature
- Excludes Battles and cards that are creatures only on the reverse face
- Stores supported reverse-face rules data locally
- Preserves printed status by Oracle ID
- Creates a database backup before command-line updates

Internet access is required only while the update is running.

## Offline Use

After a successful card-database update, normal gameplay uses local data for:

- Card selection
- Search
- Card names and rules
- Reverse faces
- Generated mobile previews
- Generated printer images
- Printed-card tracking

Official card artwork is not downloaded, cached, displayed, or distributed.

Before taking the system to a location with limited or no internet access:

1. Update the card database.
2. Restart the Raspberry Pi.
3. Disconnect internet access temporarily.
4. Test summoning, searching, front and back viewing, and printing.

## Updating the Project

Download the latest source:

```bash
cd ~/momir
git pull
```

Update Python dependencies:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
```

Update the card database when needed:

```bash
./scripts/update_momir_cards.sh
```

Restart the service:

```bash
sudo systemctl restart momir-summoner.service
```

## Backup

Before a major update, stop the service and create a local archive:

```bash
sudo systemctl stop momir-summoner.service
cd ~
tar -czf momir_backup_$(date +%Y%m%d_%H%M%S).tar.gz momir
sudo systemctl start momir-summoner.service
```

Backup archives may contain:

- Local configuration
- Printer addresses
- Database and printed-card history
- Generated print files
- Logs or other runtime data

Do not commit backup archives to a public repository.

## Service Management

Check status:

```bash
sudo systemctl status momir-summoner.service
```

Restart:

```bash
sudo systemctl restart momir-summoner.service
```

Stop:

```bash
sudo systemctl stop momir-summoner.service
```

Start:

```bash
sudo systemctl start momir-summoner.service
```

### Application logs

View recent logs:

```bash
journalctl -u momir-summoner.service -n 100 --no-pager
```

Follow live logs:

```bash
journalctl -u momir-summoner.service -f
```

## Troubleshooting

### The phone cannot open the page

Confirm the service is running:

```bash
systemctl status momir-summoner.service
```

Confirm the application is listening:

```bash
ss -ltnp | grep 5000
```

Confirm the Raspberry Pi's addresses:

```bash
hostname -I
```

Confirm both devices are on the same network, or that both are connected to the same Tailscale network.

Check for guest-network, venue-network, or hotspot client isolation.

### `momir.local` does not work

Use the Raspberry Pi's numeric local IP address instead:

```text
http://<raspberry-pi-ip>:5000
```

Confirm the hostname:

```bash
hostname
```

Confirm the Avahi service is running:

```bash
systemctl status avahi-daemon
```

### The Tailscale address does not work

Check the Raspberry Pi:

```bash
tailscale status
tailscale ip -4
```

Confirm Tailscale is active on the controller device and both devices appear in the same tailnet.

Confirm the application is listening on `0.0.0.0:5000`.

### The printer is not found

A gray printer icon on the gameplay page means the configured printer is not currently ready or reachable. Tap the icon or open Settings to view the detailed status message.

Confirm the printer is powered on, charged, and awake.

Check Bluetooth:

```bash
systemctl status bluetooth
```

List known Bluetooth devices:

```bash
bluetoothctl devices
```

Confirm that the address in `config.local.json` matches the printer currently being used.

### Printing fails intermittently

- Move the printer closer to the Raspberry Pi.
- Confirm the printer is awake before printing.
- Use a reliable Raspberry Pi power supply and USB cable.
- Check application and service logs.
- Confirm another phone or computer is not actively connected to the printer.
- Confirm the configured Bluetooth channel is correct.

### Raspberry Pi power problems

Check the Raspberry Pi throttling flags:

```bash
vcgencmd get_throttled
```

A result of:

```text
throttled=0x0
```

means no current or recorded throttling flags are set. Investigate any nonzero result before relying on the system during an event.

### The card database is empty

Run:

```bash
cd ~/momir
./scripts/update_momir_cards.sh
```

Then restart the service:

```bash
sudo systemctl restart momir-summoner.service
```

### View service errors

```bash
journalctl -u momir-summoner.service -n 100 --no-pager
```

## Development and Tests

Create a development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the tests:

```bash
python -m unittest discover -s tests -v
```

The tests cover:

- Front-face creature filtering
- Battle exclusion
- Reverse-face storage
- Missing-artwork acceptance
- Local configuration
- Environment-variable precedence
- Printed-card tracking
- Preservation of printed status during card updates

GitHub Actions runs the test suite on supported Python versions.

## Uninstalling

Remove the systemd service while preserving application files and local data:

```bash
./uninstall.sh
```

Remove the service and generated local data:

```bash
./uninstall.sh --purge-data
```

Review the command output before deleting the repository directory itself.

## Runtime Files Excluded from Git

These files and directories are intentionally excluded:

```text
config.local.json
momir.db
momir.db-*
prints/
images/
backups/
logs/
data/*.json
data/*.json.gz
venv/
.venv/
```

The repository includes small project-generated mana-symbol PNG files used to render mana costs and rules text. They are not official card artwork and can be regenerated with:

```bash
python fetch_mana_symbols.py
```

## Card Data and Intellectual Property

Card rules and metadata are retrieved from [Scryfall](https://scryfall.com/) during local installation and updates.

Official card artwork is not downloaded, included, cached, or distributed by this project.

Magic: The Gathering, card names, mana symbols, and related properties are owned by Wizards of the Coast and their respective rights holders.

Momir Summoner is an independent fan-made project and is not affiliated with, endorsed by, sponsored by, or approved by Wizards of the Coast or Scryfall.

## License

The project source code is licensed under the GNU General Public License v3.0 only (`GPL-3.0-only`). See [LICENSE](LICENSE).

<!-- MOMIR_CURRENT_SETUP_START -->
## Tested dual-Wi-Fi setup

The tested portable network configuration keeps the game available even when
no normal Wi-Fi network is present:

- `wlan0` — the Raspberry Pi's built-in Wi-Fi adapter. It hosts the permanent
  `Momir` wireless network.
- `wlan1` — a USB Wi-Fi adapter. It connects the Pi to home Wi-Fi or another
  internet-enabled network.
- Hotspot address — `10.42.0.1/24`.
- Hotspot URL — open `http://10.42.0.1/` while connected to the `Momir`
  wireless network.
- Normal-network URL — open `http://momir.local:5000/` while the controller
  device and Pi are connected to the same regular Wi-Fi network.

The hotspot uses `hostapd`, `dnsmasq`, IP forwarding/NAT, and a small port-80
captive-portal proxy. The application itself continues to run on port `5000`.
Automatic captive-portal opening varies by phone and tablet, so a saved
bookmark or home-screen icon is the most reliable launch method.

Useful verification commands:

```bash
ip -br addr show wlan0 wlan1
sudo systemctl is-active momir-hotspot-network.service
sudo systemctl is-active momir-hostapd.service
sudo systemctl is-active momir-dnsmasq.service
sudo systemctl is-active momir-captive-portal.service
curl -I http://127.0.0.1:5000/
```

The tested hotspot configuration files are stored under
`/etc/momir-hotspot/`, and the captive-portal proxy is installed at
`/usr/local/sbin/momir-captive-portal.py`.

## Add Momir Summoner to a phone or tablet home screen

Open Momir Summoner in the device browser, then use the browser's
**Add to Home screen** or **Install app** command. The installed shortcut uses
the name **Momir Summoner** and the icons provided by:

- `webapp/static/manifest.webmanifest`
- `webapp/static/icons/`

Using the home-screen shortcut is recommended on the dedicated hotspot because
some devices do not automatically open their captive-portal window.
<!-- MOMIR_CURRENT_SETUP_END -->

<!-- MOMIR_THERMAL_PRINTER_START -->
## Printer types and 58 mm thermal printing

Momir Summoner supports two printer output modes:

- **Photo printer** keeps the existing full-card image renderer and photo
  printer workflow.
- **58 mm thermal receipt printer** prints a fast black-and-white receipt using
  native ESC/POS text and a native QR code.

The thermal receipt contains only the card name and mana cost, creature type,
rules text, power/toughness, and QR code. It does not include artwork, mana
value, set, collector number, rarity, flavor text, or legal text.

### Confirmed PT210 Bluetooth configuration

```text
Name: PT210_4558
Bluetooth address: 10:22:33:05:45:58
RFCOMM channel: 1
Transport: direct Python Bluetooth RFCOMM socket
```

The application does not use `/dev/rfcomm0`. It opens a direct RFCOMM socket
for each print and sends native ESC/POS text and native QR commands.

Mock mode remains available by setting `transport` to `mock`. Mock jobs are
saved under `prints/thermal-mock/`.
<!-- MOMIR_THERMAL_DETAILS_START -->
### Thermal QR targets and printed-state behavior

The native 58 mm thermal slip includes a QR code that opens the card's exact
Scryfall page using the stored `scryfall_uri`. If that URI is unavailable, the
application falls back to a Scryfall search for the card name. Opening the QR
code requires internet access; printing the locally stored card information
does not.

Each configured printer has its own **Mark card as printed** option. Its
default value is **No**, so printing through a newly configured printer does
not change the card's printed state unless that option is explicitly enabled.
The manual **Mark as Printed** control remains available on the main screen.

Thermal printing is an additional printer type. Existing photo-printer support
remains available and is not replaced by the thermal workflow.
<!-- MOMIR_THERMAL_DETAILS_END -->

<!-- MOMIR_THERMAL_PRINTER_END -->
