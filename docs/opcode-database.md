# GSP 670 Opcode Database

> ⚠️ **SUPERSEDED (2026-10-12) — historical reference only.**
>
> The normal-mode control protocol is the **Capricorn/SECOM command set**
> (opcodes `0x00`–`0x1C`). Read
> [`verified-secom-opcodes.md`](verified-secom-opcodes.md) instead — it is the
> authoritative table, verified against both the service binary and live
> hardware.
>
> Everything below describes the **FWU `0x4F00`–`0x4F1F` family only** (which is
> the firmware-update channel, not device control) and an "echo mode"
> interpretation of the `0x4000`–`0x40FF` ranges. That "echo mode" was a
> **misreading of the pure transport link-ACK (`05 30`, which echoes the request
> payload)**. Any "feature index" values in this document are fabricated. See
> [`current-status.md`](current-status.md).

_Historical content preserved below for audit only._

This document catalogs all known Capricorn protocol opcodes for the EPOS|Sennheiser GSP 670 headset and GSA 70 dongle.

## Opcode Overview

The Capricorn protocol uses opcodes in the 0x4F00-0x4F1F range for firmware update (FWU) operations. Probing has revealed additional response patterns in the 0x4000-0x40FF range.

## Extended Probe Results (2026-10-11)

Systematic probing of opcode ranges on both devices:

| Device | PID | ACK Opcodes | NAK Opcodes | Notes |
|--------|-----|-------------|-------------|-------|
| GSP 670 Headset | 0x008A | 280 | 8 | Echo mode (returns 0x0100) |
| GSA 70 Dongle | 0x0300 | 21 | 6 | Selective responses |

## FWU Family Opcodes (0x4F00-0x4F1F)

These opcodes are part of the Firmware Update family used for device configuration and firmware management.

| Opcode | Name | Direction | Payload | Description | Evidence |
|--------|------|-----------|---------|-------------|----------|
| 0x4F00 | FWU_ENABLE_REQ | Host→Device | - | Enable firmware mode | Returns NAK without enable |
| 0x4F01 | FWU_ENABLE_CFM | Device→Host | - | Enable confirmation | Returns NAK without enable |
| 0x4F02 | FWU_DEVICE_NOTIFY_IND | Device→Host | variable | Control/button events | Device-to-host only |
| 0x4F03 | FWU_UPDATE_REQ | Host→Device | - | Firmware update request | Returns NAK |
| 0x4F04 | FWU_UPDATE_CFM | Device→Host | - | Update confirmation | Timeout (no response) |
| 0x4F05 | FWU_UPDATE_IND | Device→Host | - | Update indication | Timeout |
| 0x4F06 | FWU_UPDATE_RES | Host→Device | - | Update response | Timeout |
| 0x4F07 | FWU_GET_BLOCK_IND | Device→Host | - | Get block indication | Timeout |
| 0x4F08 | FWU_GET_BLOCK_RES | Host→Device | - | Get block response | Returns NAK |
| 0x4F09 | FWU_GET_CRC_IND | Device→Host | 4 bytes | CRC indication | ACK, echoes payload |
| 0x4F0A | FWU_GET_CRC_RES | Host→Device | - | CRC response | ACK, echoes payload |
| 0x4F0B | FWU_COMPLETE_IND | Device→Host | - | Update complete | ACK, echoes payload |
| 0x4F0C | FWU_STATUS_IND | Device→Host | variable | Periodic status | ACK, echoes payload |
| 0x4F0D | FWU_MULTI_CRC_IND | Device→Host | - | Multi-CRC indication | ACK, echoes payload |
| 0x4F0E | FWU_MULTI_CRC_RES | Host→Device | - | Multi-CRC response | ACK, echoes payload |
| 0x4F0F | - | - | - | Undefined | ACK, echoes payload |
| 0x4F10 | FWU_SET_FEATURES_REQ | Host→Device | variable | Set device features | ACK, echoes payload |
| 0x4F11 | FWU_SET_FEATURES_CFM | Device→Host | - | Set features confirmation | ACK, echoes payload |
| 0x4F12 | FWU_GET_FEATURES_REQ | Host→Device | variable | Get device features | ACK, echoes payload (up to 4 bytes) |
| 0x4F13 | FWU_GET_FEATURES_CFM | Device→Host | variable | Features response | ACK, echoes payload |
| 0x4F14 | FWU_CRC32_IND | Device→Host | - | CRC32 indication | Timeout |
| 0x4F15 | FWU_CRC32_RES | Host→Device | - | CRC32 response | Timeout |
| 0x4F16 | - | - | - | Undefined | Timeout |
| 0x4F17 | - | - | - | Undefined | Timeout |
| 0x4F18 | - | - | - | Undefined | ACK, echoes payload |
| 0x4F19 | - | - | - | Undefined | ACK, echoes payload |
| 0x4F1A | - | - | - | Undefined | ACK, echoes payload |
| 0x4F1B | - | - | - | Undefined | ACK, echoes payload |
| 0x4F1C | - | - | - | Undefined | ACK, echoes payload |
| 0x4F1D | - | - | - | Undefined | ACK, echoes payload |
| 0x4F1E | - | - | - | Undefined | ACK, echoes payload |
| 0x4F1F | - | - | - | Undefined | ACK, echoes payload |

## Probe Results (0x4000-0x40FF Range)

Probing the 0x4000-0x40FF range on the headset in wired mode (PID 0x008A) revealed:

| Opcode Range | Response | Notes |
|-------------|----------|-------|
| 0x4000-0x4003 | NAK | Requires enable |
| 0x4004-0x40FF | ACK | Echoes first 4 bytes of payload |

**Note:** The headset (0x008A) exhibits echo behavior where it returns the first 4 bytes of the sent payload. This may indicate the device is in a debug or test mode.

## Dongle vs Headset Behavior

| Device | PID | Behavior |
|--------|-----|----------|
| GSA 70 Dongle | 0x0300 | Proper protocol responses, NAK for disabled opcodes |
| GSP 670 Headset (Wired) | 0x008A | Echo mode - returns payload back |

## Headset Echo Mode (0x4000-0x40FF)

The headset (PID 0x008A) exhibits a distinctive "echo mode" behavior:

| Opcode Range | Response | Payload |
|-------------|----------|---------|
| 0x4000-0x4003 | NAK | (empty) |
| 0x4004-0x40FF | ACK | 0x0100 (constant) |
| 0x4F00-0x4F03 | NAK | (empty) |
| 0x4F04-0x4F1F | ACK | 0x0100 (constant) |

**Interpretation:** The headset echoes a constant 0x0100 for most opcodes, suggesting it's in a diagnostic or test mode when accessed directly. The dongle appears to act as a gateway/filters these requests.

## Dongle Selective Responses (0x4000-0x40FF)

The dongle responds to specific opcodes with ACK + 0x0100:

| Opcode Pattern | Example | Notes |
|---------------|---------|-------|
| 0x4010-0x4014 | 0x4010, 0x4011, 0x4012, 0x4013, 0x4014 | Consecutive block |
| 0x4022-0x4023 | 0x4022, 0x4023 | Consecutive block |
| 0x40Xn | 0x4033, 0x4043, 0x4053... | Every 0x10 + 3 |

This suggests a structured register layout where certain control registers are implemented.

## FWU Family Responses

| Opcode | Name | Headset | Dongle |
|--------|------|---------|--------|
| 0x4F00 | FWU_ENABLE_REQ | NAK | NAK |
| 0x4F01 | FWU_ENABLE_CFM | NAK | NAK |
| 0x4F02 | FWU_DEVICE_NOTIFY_IND | N/A (device only) | N/A |
| 0x4F03 | FWU_UPDATE_REQ | NAK | **ACK** (0x0100) |
| 0x4F04-0x4F1F | (various) | ACK (0x0100) | ACK (0x4F03 only) |

## Opcode Transform Formula

Request opcodes are transformed to expected reply opcodes:

```
reply_opcode = (req & 0xFF00) | ((req & 0xFF) >> 2)
```

Examples:
- 0x4F12 (GET_FEATURES) → 0x4F04 (reply)
- 0x4F10 (SET_FEATURES) → 0x4F04 (reply)

## Payload Echo Behavior

When probing with various payloads to 0x4F12 (GET_FEATURES):

| Sent Payload | Response Size | Response Payload | Notes |
|-------------|---------------|------------------|-------|
| (empty) | 0 | (empty) | Correct |
| 0x01 | 0 | (empty) | Single byte ignored |
| 0x0100 | 2 | 0x0100 | Echoes 2 bytes |
| 0xFFFFFFFF | 4 | 0xFFFFFFFF | Echoes 4 bytes |
| 0x68656C6C6F ("hello") | 4 | 0x68656C6C | Truncated to 4 bytes |

**Maximum echoed payload: 4 bytes**

## Known Issues

1. **Echo Mode**: The headset responds to many opcodes by echoing back the payload. This is unusual and may indicate the device is in a special mode.

2. **NAK Responses**: Many FWU opcodes return NAK, suggesting they require firmware mode to be enabled first.

3. **Timeout Responses**: Some opcodes (0x4F04-0x4F07, 0x4F14-0x4F17) do not respond at all, likely due to incorrect usage or missing prerequisites.

## Reference

- Protocol implementation: `src/gsp670/protocol.py`
- Opcode table with evidence: `docs/verified-secom-opcodes.md`
- Method summary: `docs/analysis/README.md`
