# Contributing

Contributions are welcome through GitHub issues and pull requests.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Do not commit local configuration, databases, generated prints, downloaded card
data, Bluetooth addresses, Wi-Fi credentials, or backup archives.

Changes to card-import behavior should include tests covering front-face
creature filtering and preservation of printed status.
