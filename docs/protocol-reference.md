# Capricorn Protocol Reference

> **See also:** [`verified-secom-opcodes.md`](verified-secom-opcodes.md) —
> the verified normal-mode opcode/payload table (2026-10-12). Where the two
> disagree, the verified document wins.
>
> **Corrections applied 2026-10-12:** the normal-mode control opcodes are
> SECOM `0x00`–`0x1C` (**not** the FWU `0x4F00` family); the vendor Report ID is
> `0x01` (**not** `0x6A` — that was a misread of the Report-Count byte `95 6A`);
> and an ACK (`05 30`) is a pure transport acknowledgement, not evidence the
> command was understood. See [`current-status.md`](current-status.md).

This document describes the Capricorn HID protocol used by the EPOS|Sennheiser GSP 670 headset and GSA 70 dongle.

## Overview

The GSP 670 uses a vendor-specific HID protocol called "Capricorn" for control communication. This is separate from the audio streaming interfaces (which use standard USB Audio Class).

**Key characteristics:**
- HID interface with vendor-specific usage page (0xFFFF)
- 106-byte reports (plus 1 byte report ID = 107 total)
- Report ID 0x01 for Capricorn frames
- No OUT endpoint - host-to-device uses SET_REPORT control transfers

## Frame Format

Each HID report is 107 bytes (1 report ID + 106 data bytes):

```
Offset  Size  Field           Description
------  ----  -----           -----------
0       1     report_id       Always 0x01
1       4     sync            EB FE 01 00
5       2     marker          See Marker Types
7       2     opcode          Little-endian opcode
9       2     size            Little-endian payload size
11      1     crc             CRC-8 of payload
12      1     filler          Always 0x00
13      N     payload         Actual data (N = size)
```

## Marker Types

Markers indicate the direction and type of frame:

| Marker | Value | Direction/Type |
|--------|-------|----------------|
| HOST | 04 00 | Host to Device (and the data/sub-device reply echo) |
| DEVICE | 10 01 | Device to Host (unsolicited data / events) |
| EVENT_BURST | 00 01 | Device to Host event burst (button press) |
| EVENT_POLL | ff 01 | Device to Host recurring event/config frame |
| ACK | 05 30 | Link acknowledgement (pure transport; echoes payload) |
| NAK | 04 10 | Negative acknowledgement |

### Marker Transform

When the device responds to a host marker, it transforms the marker:
- Byte 0: +1 (04 → 05, 10 → 11)
- Byte 1: +0x30 (00 → 30, 01 → 31)

Example: Host sends 04 00 (MARKER_HOST), device responds with 05 30 (MARKER_ACK).

## Opcode Families

There are **two** opcode spaces:

* **Normal-mode control = Capricorn/SECOM `0x00`–`0x1C`** — device identity,
  controls, telemetry. This is the one used for ordinary device operation; see
  [`verified-secom-opcodes.md`](verified-secom-opcodes.md) for the full table.
* **Firmware-update (FWU) `0x4F00`–`0x4F1F`** — used only for the (blocked)
  firmware-update flow:

| Opcode | Name | Direction | Description |
|--------|------|-----------|-------------|
| 0x4F00 | FWU_ENABLE_REQ | Host→Device | Enable firmware mode (NAKs on this firmware) |
| 0x4F01 | FWU_ENABLE_CFM | Device→Host | Enable confirmation |
| 0x4F02 | FWU_DEVICE_NOTIFY_IND | Device→Host | Control/button events |
| 0x4F0C | FWU_STATUS_IND | Device→Host | Periodic status notification |
| 0x4F10 | FWU_SET_FEATURES_REQ | Host→Device | Set device features |
| 0x4F12 | FWU_GET_FEATURES_REQ | Host→Device | Get device features |
| 0x4F13 | FWU_GET_FEATURES_CFM | Device→Host | Features response |

## Opcode Transform

Request opcodes are transformed to expected reply opcodes:

```
reply_opcode = (req & 0xFF00) | ((req & 0xFF) >> 2)
```

Example: 0x4F12 → 0x4F04 (GET_FEATURES request → confirmation)

## CRC-8 Algorithm

Payload integrity is verified using CRC-8:

- **Polynomial:** 0x07
- **Initial value:** 0xFF
- **Input:** Payload bytes only (not the entire frame)

```python
def crc8(data: bytes, init: int = 0xFF) -> int:
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc
```

## Frame Classification

Received frames are classified based on their marker:

| Marker | Kind | Meaning |
|--------|------|---------|
| 05 30 | ack | Pure transport acknowledgement (echoes payload; not proof of execution) |
| 04 10 | nak | Request rejected |
| 04 00 (opcode 0000) | other | Data reply (echoed request header + value) |
| 04 00 (opcode 0004) | subreply | Sub-device / device-event reply class |
| 00 01 / ff 01 | event | Unsolicited device→host event |
| 10 01 | other | Asynchronous device→host data |

## HID Report Descriptor

The device HID report descriptor reveals:

1. **Vendor Collection (Report ID 0x01)**
   - 106-byte input *and* 106-byte output report (the historical "Report ID
     0x6A" was a misread of the Report-Count byte `95 6A` = 106)

2. **Consumer Control (Report ID 0x08)**
   - 4 bits for media buttons (play/pause, next, prev)

3. **Volume Wheel (Report ID 0x02)**
   - 5 fields of 2 bits each for volume wheel

4. **Mute Button (Report ID 0x06)**
   - Constant field for mute button

## USB Endpoints

| Interface | Class | Purpose |
|----------|-------|---------|
| 0 | Audio | Main audio control |
| 1 | Audio | Headset playback streaming |
| 2 | Audio | Headset playback alt |
| 3 | Audio | Microphone capture |
| 4 | Audio | Microphone capture alt |
| 5 | HID | Capricorn control protocol |

## Product IDs

| PID | Device | Mode |
|-----|--------|------|
| 0x0300 | GSA 70 | Normal (dongle) |
| 0x008A | GSP 670 | Wired USB device mode |
| 0x8300 | GSA 70 | Firmware upgrade |
| 0x8303 | GSA 70 | Firmware upgrade |
| 0x8089 | GSA 70 | Firmware upgrade |
| 0x808A | GSA 70 | Firmware upgrade |

## Sequence Diagram

Typical command/response flow:

```
Host                           Device
  |                               |
  |  SET_REPORT(0x4F12, payload) |
  |------------------------------>|
  |                               |
  |  INTERRUPT IN (0x4F04, data)  |
  |<------------------------------|
  |                               |
```

Asynchronous notifications:

```
Host                           Device
  |                               |
  |                    [button press]
  |                               |
  |  INTERRUPT IN (0x4F02, event) |
  |<------------------------------|
```

## Reference

- Protocol implementation: `src/gsp670/protocol.py`
- Analysis document: `docs/analysis/direct-hid-probing.md`
