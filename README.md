# Salter Cook Bluetooth Thermometer Integration

Home Assistant custom integration for Salter Cook Bluetooth dual-probe kitchen thermometer. Connect, monitor temperatures, and set temperature alarms directly from Home Assistant.

## Features

- **Dual Temperature Probes**: Monitor two temperature sensors simultaneously (left and right probes)
- **Temperature Alarms**: Set temperature thresholds for each probe with automatic notifications when reached
- **Real-time Monitoring**: Continuous temperature updates via Bluetooth LE connection
- **Auto-reconnection**: Automatically reconnects when the device is powered back on
- **Power Management**: Manual disconnect button to let the device sleep and save battery

## Supported Devices

- Salter Cook Bluetooth Kitchen Thermometer (Model: SALTER-BKT)

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/stuartp44/hasalter`
6. Select category: "Integration"
7. Click "Add"
8. Find "Salter" in the integration list
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Download the latest release from [Releases](https://github.com/stuartp44/hasalter/releases)
2. Copy the `custom_components/salter` directory to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Enable Bluetooth on your Home Assistant host
2. Turn on your Salter Cook thermometer
3. Go to **Settings → Devices & Services**
4. Click **+ Add Integration**
5. Search for "**Salter**"
6. Select your device from the discovered devices list
7. Give your device a name (default: "Cook")
8. Click **Submit**

## Entities

After configuration, the integration creates the following entities:

### Sensors (2)
- **Left Probe Temperature**: Current temperature reading from probe 1
- **Right Probe Temperature**: Current temperature reading from probe 2

### Binary Sensors (3)
- **Connection Status**: Indicates if device is connected
- **Left Probe Alarm Active**: Indicates if left probe temperature has reached the alarm threshold
- **Right Probe Alarm Active**: Indicates if right probe temperature has reached the alarm threshold

### Number Controls (2)
- **Left Probe Alarm Setpoint**: Set alarm temperature for left probe (1-250°C)
- **Right Probe Alarm Setpoint**: Set alarm temperature for right probe (1-250°C)

### Buttons (3)
- **Disconnect**: Manually disconnect from device to allow it to sleep
- **Left Probe Clear Alarm**: Clear the alarm for left probe
- **Right Probe Clear Alarm**: Clear the alarm for right probe

## Usage Examples

### Monitor Cooking Temperature
Use the temperature sensors in automations to track your cooking progress:

```yaml
automation:
  - alias: "Notify when steak is ready"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cook_left_probe_temperature
        above: 55
    action:
      - service: notify.mobile_app
        data:
          message: "Steak has reached 55°C - Medium rare!"
```

### Temperature Alarms
Set alarm thresholds using the number controls:

```yaml
service: number.set_value
target:
  entity_id: number.cook_left_probe_alarm
data:
  value: 70
```

When the temperature reaches the alarm setpoint, the binary sensor will activate and you can trigger automations.

### Power Management
The device will automatically enter sleep mode after about 60 seconds of inactivity. To manually disconnect:

```yaml
service: button.press
target:
  entity_id: button.cook_disconnect
```

## Requirements

- Home Assistant 2024.1.0 or newer
- Bluetooth adapter with BLE support
- Python 3.11 or newer

## Troubleshooting

### Device Not Discovered
- Ensure Bluetooth is enabled on your Home Assistant host
- Turn the Salter device on (button press)
- Move the device closer to your Home Assistant host
- Check that no other devices are connected to the thermometer

### Connection Drops
- Ensure the device is within Bluetooth range (typically 10 meters)
- Check for Bluetooth interference from other devices
- The device automatically sleeps after 60 seconds without polling - this is normal behavior
- The integration will automatically reconnect when you turn the device back on

### Temperature Not Updating
- Check the Connection Status binary sensor
- Verify probes are properly connected to the device
- Try disconnecting and reconnecting the device

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.salter: debug
```

## Technical Details

- Communication: Bluetooth LE (BLE)
- Protocol: Custom Salter protocol over GATT characteristic `0000ffe1-0000-1000-8000-00805f9b34fb`
- Polling Interval: 1 second when connected
- Auto-sleep: ~60 seconds after last poll
- Temperature Range: -50°C to 300°C (display), 1-250°C (alarms)
- Temperature Resolution: 0.1°C

For detailed protocol analysis, see [BLE_PROTOCOL_ANALYSIS.md](BLE_PROTOCOL_ANALYSIS.md).

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.

### Commit Message Format

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Use the following format:

- `feat:` - New features (minor version bump)
- `fix:` - Bug fixes (patch version bump)
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

### Preview Releases

Add the `preview` label to your PR to create a preview release for testing before merging.

## License

See [LICENSE](LICENSE) for details.

## Disclaimer

This is an unofficial, community-developed integration and is not affiliated with, endorsed by, or sponsored by Salter Housewares Ltd. "Salter" and "Salter Cook" are trademarks of Salter Housewares Ltd. All trademarks are the property of their respective owners.

This software is provided "as is" without warranty of any kind. Use at your own risk.
