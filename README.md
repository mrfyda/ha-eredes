# E-REDES Integration for Home Assistant

[![Validate](https://github.com/mrfyda/ha-eredes/actions/workflows/validate.yml/badge.svg)](https://github.com/mrfyda/ha-eredes/actions/workflows/validate.yml)
[![Tests](https://github.com/mrfyda/ha-eredes/actions/workflows/tests.yml/badge.svg)](https://github.com/mrfyda/ha-eredes/actions/workflows/tests.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration to fetch energy consumption data from [E-REDES](https://balcaodigital.e-redes.pt) (Portuguese electricity distribution network operator).

## Features

- Fetches 15-minute interval energy consumption data
- Imports up to 2 years of historical data
- Compatible with Home Assistant's Energy Dashboard
- Automatic re-authentication flow when token expires
- Multi-language support (English, Portuguese)

## Sensors

| Sensor | Description | Unit |
|--------|-------------|------|
| `sensor.eredes_energy_total` | Cumulative energy consumption | kWh |
| `sensor.eredes_energy_today` | Energy consumed today | kWh |
| `sensor.eredes_energy_yesterday` | Energy consumed yesterday | kWh |
| `sensor.eredes_power_current` | Current power (15-min average) | W |

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu and select "Custom repositories"
3. Add `https://github.com/mrfyda/ha-eredes` with category "Integration"
4. Click "Install"
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy `custom_components/eredes` to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

This integration requires a session token from the E-REDES portal. Due to CAPTCHA protection on the login page, automatic authentication is not possible.

### Getting Your Token

1. Log into [balcaodigital.e-redes.pt](https://balcaodigital.e-redes.pt) in your browser
2. Open browser developer tools (F12)
3. Go to **Application** > **Cookies** > `https://balcaodigital.e-redes.pt`
4. Copy the value of the `aat` cookie

### Adding the Integration

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration**
3. Search for "E-REDES"
4. Enter your configuration:
   - **Session Cookie**: The value of the `aat` cookie from your browser (the full Cookie header is also accepted)
   - **CPE Code**: Your electricity meter CPE code (e.g., `PT0002000012345678AB`)

### Token Expiration

The token will expire after some time (typically when you log out or after extended inactivity). When this happens:

1. Home Assistant will show a re-authentication notification
2. Log into the E-REDES portal again
3. Copy the new `aat` cookie value
4. Enter it in the re-authentication form

## Energy Dashboard Setup

After installation, add the integration to your Energy Dashboard:

1. Go to **Settings** > **Dashboards** > **Energy**
2. Under "Grid consumption", click **Add consumption**
3. Select `sensor.eredes_energy_total`

## Known Limitations

| Limitation | Description |
|------------|-------------|
| Manual token | Due to CAPTCHA, tokens must be obtained manually from browser |
| Token expiry | Token expires and requires periodic manual refresh |
| Data delay | E-REDES data is typically 1-2 hours behind real-time |
| Resolution | Data is provided in 15-minute intervals only |
| Real-time | For real-time monitoring, use a dedicated energy monitor (e.g., Shelly) |

## Troubleshooting

### Invalid Token Error

If you see a token error:

1. Obtain a fresh token by logging into [balcaodigital.e-redes.pt](https://balcaodigital.e-redes.pt)
2. Copy the new `aat` cookie value
3. Reconfigure or re-authenticate the integration

### No Data

If sensors show "Unknown" or no data:

1. E-REDES may have a delay in processing data (wait 1-2 hours)
2. Check the integration logs for errors
3. Verify your CPE code is correct

## Development

```bash
# Clone the repository
git clone https://github.com/mrfyda/ha-eredes.git
cd ha-eredes

# Install development dependencies (using uv)
uv venv
source .venv/bin/activate
uv pip install -r requirements_test.txt

# Run tests
pytest tests/ -v

# Run linting
ruff check .
mypy custom_components/eredes --strict
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Disclaimer

This integration is not affiliated with or endorsed by E-REDES. Use at your own risk.
