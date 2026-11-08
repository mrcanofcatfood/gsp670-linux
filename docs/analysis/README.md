# Analysis notes

These are the working notes behind the protocol documentation. They record how
the vendor's "Capricorn" HID protocol was recovered and what was verified
against a live device.

They are included because the protocol documents
([../protocol-reference.md](../protocol-reference.md),
[../verified-secom-opcodes.md](../verified-secom-opcodes.md),
[../opcode-database.md](../opcode-database.md)) cite them as their evidence
trail. If you only want to *use* the headset, you do not need to read these.

| Document | Contents |
|---|---|
| [session-handshake.md](session-handshake.md) | The handshake and event model; why the value GETs return only an ACK; the firmware-update mode dance |
| [direct-hid-probing.md](direct-hid-probing.md) | The raw HID probes, with live captures and their interpretation |
| [final-findings.md](final-findings.md) | Firmware-update history and the final verdict on the FWU path |

## A note on what is not here

The following were deliberately left out of this repository:

- **Vendor binaries** — the EPOS Gaming Suite installer, its DLLs and the
  decompiled output. These are proprietary and are not redistributable.
- **USB captures** — multi-megabyte binary traces that may contain
  copyrighted firmware.
- **Windows VM images** used for capture sessions.

The distilled conclusions from that work live in the protocol documents and in
[../current-status.md](../current-status.md).

## Legal

This project is an independent reverse-engineering effort and is not
affiliated with EPOS or Sennheiser. See the `legal-analysis` material in the
project's development history if you need the reasoning; the short version is
that the protocol documentation here describes observed behaviour on hardware
the user owns, and contains no vendor code.
