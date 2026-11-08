# Current Status

**Last updated:** 2026-11-08
**Scope:** the single authoritative summary of what is verified, what is
blocked, and what is still open. Where this document and any other disagree,
the verified evidence in [verified-secom-opcodes.md](verified-secom-opcodes.md)
and this document win.

---

## 1. What works (verified)

| Capability | Status | Evidence / notes |
|---|---|---|
| Device discovery (dongle + headset) | ✅ | `src/gsp670/discovery.py`, `gsp670 info` |
| Capricorn/SECOM wire framing | ✅ | [verified-secom-opcodes.md](verified-secom-opcodes.md) §1; reproduced byte-for-byte by an independent encoder |
| Identity readback: FW version, serial, device name, device address | ✅ | live: dongle `3.14.2` / `"EPOS GSA 70"`; headset `3.2.6` / `"GSP 670"` |
| Sub-device count (`0x04`) | ✅ (returns `0`) | `00 00`; not a reliable link indicator (§3) |
| Unsolicited device→host events (`00 01` / `ff 01`) | ✅ | captured on battery-button press; [verified-secom-opcodes.md](verified-secom-opcodes.md) §5.2 |
| Wireless audio (Game stereo + Chat mono + mic) | ✅ | stock `usb-gaming-headset.conf` profile set; see [install.md](install.md) |
| Wired USB-C audio (48 kHz playback / 16 kHz capture, full-duplex) | ✅ | [compatibility.md](compatibility.md); ~44 ms latency |
| Python library + CLI (`info`, `status`, `battery`, `controls`, `monitor`, `events`, `protocol inspect`) | ✅ | 220 unit/integration tests pass; `monitor`/`events` name decoded event keys live (`Frame.event_name`, `format_event_key`, `EVENT_PAYLOAD`) |

## 2. Blocked (confirmed, not a software problem)

| Item | Verdict |
|---|---|
| Firmware update to fix the 12 Mbps USB bug | **Permanently blocked** — no fixed firmware exists publicly; the dongle already runs the final known release. Nothing to flash even with a complete protocol. |
| Wireless-mode latency (~1.4 s) | **Unfixable in software** — GSA 70 Full-Speed USB PHY / bridge-buffering bug. Use wired USB-C. See [limitations.md](limitations.md) §1. |
| FWU over the SECOM transport | **Wrong transport** — firmware update uses a separate Rtx channel (64-byte `0x58`-prefixed reports), not SECOM `04 00`. The `0x4F00` SECOM send NAKed for that reason. The real request shape is `00 4F <A> <B>` with expected response `0x4f01`. FWU entry also only fires from an orchestrated mode transition (with USB re-enumeration between stages and a device firmware-version precondition), which a single raw HID write cannot reproduce. Flashing is still moot — no fixed firmware exists. |
| Feature-report write path (`HIDIOCSFEATURE`) | Not available — returns `EINVAL`; host→device is control `SET_REPORT` only. |

## 3. Value GETs — resolved (event-driven, not GET-driven)

**Why do the SECOM value GETs only return a link-ACK?** `0x0e` (battery),
`0x10` (sidetone), `0x13` (noise reduction), `0x17` (latency), `0x1b`
(auto-power-off) return only `05 30` ACKs, and `0x04` reports `00 00`
sub-devices.

**Verdict:** these values are **push-driven device→host events**, not GET
replies. The dongle is a base-station that delivers telemetry as typed events
(`Battery_Events_Percentage`, `Battery_Events_ChargingChanged`,
`Sound_Events_SideToneGainChanged`, `Service_Events_AutoPowerOffTimer*`,
`Service_Events_SubDevicesChanged`) in the event-key stream already seen on the
wire. The legacy Capricorn GETs are a superseded path the firmware
transport-ACKs but does not serve; there is **no missing parameter** on the
request — it is byte-identical to the one the vendor's own application sends,
and the request payload is a fixed 4 bytes per opcode.

- **Event key resolved:** an event body is
  `<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]`, then the value fields
  (`u8` / `u16 LE` / multi-`u8`). `word1` is **not** a fixed namespace — it
  varies by source component (battery `0x000F`, ANC-state and tone `0x0007`,
  speaker-mic `0x001D`, device PDL `0x0029`; everything else `0x00F0`). The
  full 22-key table with value schemas lives in
  `src/gsp670/protocol.py` as `EVENT_KEYS` and `EVENT_PAYLOAD`.
- **Battery specifically:** the battery event keys exist in the device's
  receive-side dispatch table but were **never observed to fire on hardware**.
  A follow-up examination of the vendor's application showed that the
  corresponding battery-event slot is a **read-only getter**, and that no host
  command exists to enable those pushes. The dongle firmware simply does not
  emit battery telemetry on the passive channel, and no GET serves the value.
  **This is why `gsp670 battery` cannot report a percentage** — see
  [limitations.md](limitations.md) §2.
- **Sidetone, noise reduction and auto-power-off** are settable: the device
  acknowledges the write. They are simply not readable back through the
  legacy GET path.
- The `0x04` sub-device count is not a reliable link indicator.

## 4. Open questions

- The trailing bytes of the `0x19` link-key reply (ten bytes) are undecoded; a
  real pairing experiment would be needed to confirm.
- The device-address blob (`4e 00 f2 e2 94 00 16 00`) is opaque.
- The value range and meaning of the sidetone / noise-reduction / latency
  bytes needs a linked headset to confirm (the byte is 1-wide on the wire).
- `0x18` (remote device info) also takes a value byte — the selector meaning
  needs a linked headset to confirm.
- The `0x14`/`0x15` link ACKs carry reply-class `0x0008` (rather than
  `req >> 2` = 5), unlike every other ACK observed — cause unknown.

## 5. Where the detail lives

| Document | Contents |
|---|---|
| [verified-secom-opcodes.md](verified-secom-opcodes.md) | The opcode table, with live and corroborating evidence |
| [protocol-reference.md](protocol-reference.md) | Frame layout, markers, CRC |
| [opcode-database.md](opcode-database.md) | Opcode definitions |
| [hid-protocol.md](hid-protocol.md) | HID descriptor and interface layout |
| [analysis/README.md](analysis/README.md) | High-level summary of the method and the reasoning |
| [limitations.md](limitations.md) | Everything that cannot work, and why |

The detailed reasoning trail behind the reverse engineering is kept in the
maintainer's private workbench and is deliberately not part of this
repository — see [legal.md](legal.md) for the publication boundary.

## 6. Related constraints

The device protocol has no encryption, no access control, no licence
validation and no authentication, so there is no technological protection
measure in play and no circumvention is involved anywhere in this project. See
[legal.md](legal.md) for the full position.
