# Salter Cook BLE Protocol Analysis - SOLVED

## Summary
Successfully decoded the temperature alarm setting protocol through BLE log analysis.

## Temperature Setting Protocol - CONFIRMED

### Command Structure (8 bytes)
```
09 08 02 03 YY YY ZZ ZZ
```

**Breakdown:**
- **Bytes 0-3**: Header `09 08 02 03` (constant)
- **Bytes 4-5**: Probe 1 temperature × 10 (16-bit big-endian)
- **Bytes 6-7**: Probe 2 temperature × 10 (16-bit big-endian)

**Key insight**: The command sets **BOTH probes simultaneously**, not individually.

### Confirmed Examples

**Example 1**: Probe 1 = 65°C, Probe 2 = 100°C
```
09 08 02 03 02 8a 03 e8
            ^^^^^ ^^^^^
            650   1000
            65°C  100°C
```

**Example 2**: Probe 1 = 65°C, Probe 2 = 60°C
```
09 08 02 03 02 8a 02 58
            ^^^^^ ^^^^^
            650   600
            65°C  60°C
```

### Temperature Encoding
- Temperature value = actual temperature × 10
- Sent as 16-bit big-endian integer
- Range: 0-255°C (0-2550 in encoded value)
- Examples:
  - 22°C → 220 → `0x00DC`
  - 65°C → 650 → `0x028A`
  - 100°C → 1000 → `0x03E8`

## BLE Characteristics

**UUID: `0000ffe1-0000-1000-8000-00805f9b34fb`**
- Used for both writing commands and receiving notifications
- Write Handle: 0x002b
- Notify Handle: 0x002e

### Other Commands

**Poll/Status Command** (sent repeatedly):
```
09 03 06
```

**Init Command** (sent on connection):
```
09 03 09
```

### Device Notifications

**Temperature Data** (`0x08 XX 06 ...`):
- Regular temperature updates from both probes

**Init Response** (`0x08 XX 09 ...`):
- Contains alarm setpoint configuration
- Bytes 4-5: Probe 1 alarm × 10 (16-bit BE)
- Bytes 6-7: Probe 2 alarm × 10 (16-bit BE)

**Power Off Notification** (`0x08 XX af ...`):
- Sent when user presses power button
- Signals device is shutting down
- Integration uses this to avoid reconnection attempts until device powers back on

## Implementation Status

✅ **FULLY IMPLEMENTED** in Home Assistant integration:
- Command format: 8-byte structure to set both probes
- Temperature encoding: `temp × 10` as 16-bit big-endian
- When user sets probe 1, current probe 2 value is preserved
- When user sets probe 2, current probe 1 value is preserved
- Full range support: 0-250°C in 1°C increments

## Testing Summary

**Confirmed working:**
- ✅ Probe 1 at 100°C
- ✅ Probe 1 at 65°C
- ✅ Probe 2 at 100°C
- ✅ Probe 2 at 60°C

**To test in Home Assistant:**
- Set alarm temperature via number entities
- Verify device responds correctly
- Check that alarms trigger at set temperatures

## Notes

- Protocol uses 8-byte commands, not 3-byte as initially thought
- Both probe setpoints must be sent together in single command
- Device-to-app communication for reading temperatures (0x08 messages) uses different format
- Setting commands always use the `09 08 02 03` header
