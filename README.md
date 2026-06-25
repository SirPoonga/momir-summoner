# Momir Summoner

Momir Summoner is a Raspberry Pi-hosted web application for running a physical **Momir Vig-style** game. A phone, tablet, or computer opens the web interface, selects a mana value, summons a random creature, displays a locally generated card preview, and sends the card to a supported printer.

The Raspberry Pi performs the application, database, rendering, and printing work. The phone or other device is only used as the controller.

> [!NOTE]
> The simplest current network setup is to connect the Raspberry Pi and controller device to the same Wi-Fi network. A phone-hotspot option and an optional Tailscale setup are documented below. Instructions for a dual-Wi-Fi setup using a USB Wi-Fi adapter will be added after that configuration has been tested.

## Current Features

- Mobile-friendly web interface
- Mana values 1 through 16
- Random front-face creature selection by mana value
- Local SQLite card database
- Card search and locally generated previews
- Summon and resummon controls
- Printing through a supported Bluetooth printer
- Printed-card tracking
- Manual **Mark as Printed** control
- Printer icon for cards already marked as printed
- Front and back viewing for supported double-faced cards
- Front and back printing for supported double-faced cards
- Local card information and rules pages
- Locally stored reverse-face card data
- Card database updates using Scryfall bulk data
- Printed-card history preserved when the card database is updated
- No downloaded or cached official card artwork
- Local configuration for printer and web settings
- Automated tests and GitHub Actions validation

## Hardware

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
- USB Wi-Fi adapter for the planned dual-Wi-Fi configuration

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
    "channel": "4"
  },
  "web": {
    "host": "0.0.0.0",
    "port": 5000,
    "local_base_url": "http://momir.local:5000"
  }
}
```

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

1. Open the web interface.
2. Select the required mana value.
3. Summon a creature.
4. Review the generated card preview and information.
5. Print the selected card when needed.
6. Use **View Back** or **Print Back** when a supported card has a reverse face.
7. Use **Mark as Printed** when a card was printed outside the normal print action.
8. Use the printer icon and printed status to avoid unnecessary duplicate prints.
9. Use search to locate a specific card in the local database.

## Updating the Card Database

Use **Update Cards** at the bottom of the web interface, or run:

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

Confirm the printer is powered on and charged.

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
