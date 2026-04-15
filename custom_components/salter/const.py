DOMAIN = "salter"
PLATFORMS = ["sensor", "button", "binary_sensor", "number"]

CONF_ADDRESS = "address"
CONF_NAME = "name"
DEFAULT_NAME = "Cook"

# BLE Characteristics discovered from protocol analysis
CHAR_WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # Handle 0x002b - Write commands
CHAR_NOTIFY_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # Handle 0x002e - Notifications

# Temperature encoding: value in Celsius / 25
# Examples: 0°C=0, 25°C=1, 50°C=2, 75°C=3, 100°C=4, 125°C=5, etc.
TEMP_ENCODING_DIVISOR = 25
