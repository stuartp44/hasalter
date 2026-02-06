# Salter BLE (Advert)

Home Assistant custom integration that reads Salter Bluetooth LE advertisement data and exposes it as sensors.

## Installation

### HACS

1. In HACS, open Integrations and add this repository as a custom repository (category: Integration).
2. Install the integration.
3. Restart Home Assistant.

## Configuration

1. Go to Settings -> Devices & Services.
2. Select Add Integration and search for "Salter BLE (Advert)".
3. Follow the prompts.

## Entities

Sensors are created based on the BLE advertisement data broadcast by supported Salter devices.

## Troubleshooting

- Ensure Bluetooth is enabled on your Home Assistant host.
- Move the device closer to improve BLE reception.
