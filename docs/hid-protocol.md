# EPOS | Sennheiser HID interface

**Scope:** the USB HID interface exposed by the GSP 670 headset and the GSA 70
dongle, as observed on real hardware.

> This document describes the **interface** only — device identifiers, USB
> layout, and report framing. It contains no vendor code, no internal symbol
> names and no speculative register maps. See [legal.md](legal.md) for the
> publication boundary and [analysis/README.md](analysis/README.md) for the
> method.

---

## 1. Device identification

### 1.1 USB identifiers

All EPOS | Sennheiser gaming devices share the vendor ID `0x1395`.

| Device | Mode | PID (hex) | PID (dec) |
|---|---|---|---|
| GSA 70 dongle | wireless 2.4 GHz | `0x0300` | 768 |
| GSP 670 headset | wired Micro-USB | `0x008A` | 138 |
| GSP 670 headset | firmware-update mode | `0x808A`, `0x8089` | — |
| GSA 70 dongle | firmware-update mode | `0x8300`, `0x8303` | — |

Note that the vendor has rebranded the product over time: the same hardware
appears as "Sennheiser GSA 70" or "EPOS GSA 70" depending on the firmware
version. Do not match on the product string — match on `1395:0300`.

### 1.2 Connection types

| Type | Description |
|---|---|
| WiredUSB | Headset connected directly by Micro-USB |
| Wireless | Headset connected through the GSA 70 dongle |

---

## 2. USB layout

### 2.1 Audio interfaces

The dongle exposes **6 USB interfaces**: interfaces 0–4 are USB Audio (two
control plus streaming pairs), and **interface 5 is the only HID interface**
(class 3).

The dongle exposes **no `power_supply` node** on Linux, so battery
information is not reachable through the normal power-supply path — it would
have to come through the HID control protocol instead.

### 2.2 HID interface

| Property | Value |
|---|---|
| Interface number | 5 |
| Class | HID (3) |
| Endpoints | a single IN endpoint (`0x81`), 64-byte packets |
| Report ID | `0x01` |
| Output report | 106 bytes (107 including the report ID) |
| Input report | 106 bytes (107 including the report ID) |

There is **no interrupt-OUT endpoint**: the output report is delivered via a
HID `SET_REPORT` control transfer. Writing the wrong buffer length resets
(re-enumerates) the device, so always write exactly 107 bytes.

---

## 3. Report framing

```
byte  0      = 0x01            report id
bytes 1..4   = EB FE 01 00     sync
bytes 5..6   = 04 00           host marker (host -> device)
bytes 7..8   = opcode, LE      == the SECOM command (0x00..0x1C)
bytes 9..10  = length, LE      payload length
byte  11     = CRC-8(payload)  poly 0x07, init 0xFF
byte  12     = 0x00            filler
bytes 13..   = payload
```

The reply markers are:

| Marker | Meaning |
|---|---|
| `04 00` | host → device, and device → host data replies |
| `10 01` | device → host unsolicited data / events |
| `05 30` | ACK |
| `04 10` | NAK |
| `00 01` | device → host event burst |
| `ff 01` | device → host recurring keepalive / config frame |

The CRC-8 is an **integrity check** that detects a corrupted packet. It is not
keyed and is not a protection measure.

Full details are in [protocol-reference.md](protocol-reference.md); the opcode
table is in [verified-secom-opcodes.md](verified-secom-opcodes.md).

---

## 4. Accessing the interface on Linux

### 4.1 udev permissions

The HID interface is exposed as a `hidraw` node. To access it without root,
install the udev rules in `udev/99-gsp670.rules`, which grant the `audio` group
access and create the symlinks `/dev/gsp670-dongle` and `/dev/gsp670-headset`.

```bash
sudo cp udev/99-gsp670.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG audio "$USER"     # then log out and back in
```

### 4.2 With hidapi

```python
import hid

device = hid.device()
device.open_path(b"/dev/gsp670-dongle")
device.set_nonblocking(True)
```

This is what the `gsp670` library does; see `src/gsp670/device.py`.

---

## 5. Firmware update

The device supports a firmware-update mode with its own product IDs (see
§1.1). However, **no firmware update is possible from Linux**, for two
independent reasons:

1. The device already runs the final known firmware, and no corrected image is
   publicly available.
2. The device rejects the update command at its own firmware level. The
   vendor's Windows application reaches update mode through an orchestrated
   sequence of mode transitions with USB re-enumeration between them, which a
   single raw HID write cannot reproduce. Every candidate formulation of the
   request was tried against real hardware and refused.

This project ships **no firmware-update tooling** and does not attempt to
bypass that gate. See [limitations.md](limitations.md) §3.

---

## 6. Reference

- Protocol framing: [protocol-reference.md](protocol-reference.md)
- Opcode table: [verified-secom-opcodes.md](verified-secom-opcodes.md)
- Opcode definitions: [opcode-database.md](opcode-database.md)
- Method summary: [analysis/README.md](analysis/README.md)
- Linux implementation: `src/gsp670/protocol.py`, `src/gsp670/device.py`
- udev rules: `udev/99-gsp670.rules`
