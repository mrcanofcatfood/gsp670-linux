# Current Status

**Last updated:** 2026-10-12
**Scope:** the single authoritative summary of what is verified, what is
blocked, and what is still open. Where this document and any other disagree,
the verified evidence in `verified-secom-opcodes.md` and this document win.

---

## 1. What works (verified)

| Capability | Status | Evidence / notes |
|---|---|---|
| Device discovery (dongle + headset) | ✅ | `src/gsp670/discovery.py`, `gsp670 info` |
| Capricorn/SECOM wire framing | ✅ | `docs/verified-secom-opcodes.md` §1; `EncodeDatagram` @ `0x004ce570` |
| Identity readback: FW version, serial, device name, device address | ✅ | live: dongle `3.14.2` / `"EPOS GSA 70"`; headset `3.2.6` / `"GSP 670"` |
| Sub-device count (`0x04`) | ✅ (returns `0`) | `00 00`; not a reliable link indicator (§3) |
| Unsolicited device→host events (`00 01` / `ff 01`) | ✅ | captured on battery-button press; `docs/verified-secom-opcodes.md` §5.2 |
| Wired USB-C audio (48 kHz playback / 16 kHz capture, full-duplex) | ✅ | `docs/compatibility.md`; ~44 ms latency |
| Python library + CLI (`info`, `status`, `battery`, `controls`, `monitor`, `events`, `protocol inspect`) | ✅ | `70` unit tests pass; `monitor`/`events` name recovered event keys live (`Frame.event_name`, `format_event_key`, `EVENT_PAYLOAD`); `rtx_fwu_packet()`/`rtx_fwu_enable()` build the real FWU report shape |

## 2. Blocked (confirmed, not a software problem)

| Item | Verdict |
|---|---|
| Firmware update to fix the 12 Mbps USB bug | **Permanently blocked** — no fixed firmware exists publicly; dongle already runs the final known release. Nothing to flash even with a complete protocol. |
| Wireless-mode latency (~1.4 s) | **Unfixable in software** — GSA 70 Full-Speed USB PHY / bridge-buffering bug. Use wired USB-C. |
| `0x4F00 FWU_ENABLE_REQ` over SECOM | **Wrong transport** — FWU is an **Rtx** channel (`RtxDatagramIo::send_request_without_response`; 64-byte `0x58`-prefixed reports), not SECOM `04 00`. The `0x4F00`/`00 00` SECOM send NAKed for that reason. Real request shape: `00 4F <A> <B>` + expected-response `0x4f01` (`docs/analysis/session-handshake.md` §6.3). FWU entry also only fires from the `ModiFirmwareUpdater` mode dance (`FUN_0068b650` → `FUN_0068b300`; mode 3/5 precondition, 45 s reboot-await, device FW ≥ `1.5.20` EnterDfu gate) — §6.5. Flashing is still moot (no fixed firmware exists). |
| Feature-report write path (`HIDIOCSFEATURE`) | Not available — returns `EINVAL`; host→device is control `SET_REPORT` only. |

## 3. Value GETs — resolved (event-driven, not GET-driven)

**Why do the SECOM value GETs only return a link-ACK?** `0x0e` (battery),
`0x10` (sidetone), `0x13` (noise reduction), `0x17` (latency), `0x1b`
(auto-power-off) return only `05 30` ACKs, and `0x04` reports `00 00`
sub-devices.

**Verdict (static, `docs/analysis/session-handshake.md`):** these values are
**push-driven device→host events**, not GET replies. The dongle is a
base-station that delivers telemetry as typed events
(`Battery_Events_Percentage`, `Battery_Events_ChargingChanged`,
`Sound_Events_SideToneGainChanged`, `Service_Events_AutoPowerOffTimer*`,
`Service_Events_SubDevicesChanged`) in the event-key stream already seen on the
wire. The legacy Capricorn GETs are a superseded path the firmware
transport-ACKs but does not serve; there is **no missing parameter** on the
request (it is byte-identical to the service's, and `getHIDBuffers` proves a
fixed 4-byte payload per opcode).

- **Event key recovered (Phase 3, Ghidra; corrected 2026-10-13):** an event body
  is `<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]`, then the value fields
  (`seek(keylen)` + u8/u16). The middle word is **not** a fixed `0x00f0`: it is
  `0x000f` for battery (`12 00 0f 00 03/04 00` = `ChargingChanged`/`Percentage`),
  `0x0007` for ANC-state/tone, `0x001d` for speaker-mic optimised setting,
  `0x0029` for device PDL. All 22 closed keys (+ value schemas) are in
  `docs/analysis/session-handshake.md` §6.1 and `protocol.EVENT_KEYS` / `EVENT_PAYLOAD`.
- **Hardware caveat (GAP-RE-1b, 2026-10-13):** the "push-driven" verdict holds
  for **link/button** events (`SubDevicesChanged`, `1d 00 f0 00 …` — confirmed
  firing on a power-cycle window) but **battery events never fired** with a
  confirmed RF link + charger toggles, and `0x0e` serves no value. So battery %
  is currently **unobtainable via this dongle** (no push, no GET).
- **Outgoing event-enable question closed (2026-10-13):** the
  `Service_EventControl` / `set_battery_events` vtable slot (`[+0x74]`) that
  virtual dispatch selects is a **read-only getter** (`FUN_0064b7a0`); the whole
  chain terminates in-process, and an exhaustive caller check of the two Rtx
  wire builders shows no event-enable code among their callers → **no host
  enable command exists**. See `docs/analysis/session-handshake.md` §6.2.
- FWU mode dance traced (`docs/analysis/session-handshake.md` §6.5): the two firmware
  gates are **distinct** — battery events need headset FW ≥ **2.0.0**
  (`&DAT_008f1c30`, cached at `[obj+0x340]`), EnterDfu needs device FW ≥ **1.5.20**
  (`&DAT_008f1c70`). Both pass on live hardware (`3.2.6` / `3.14.2`).
- Tracking: `docs/analysis/session-handshake.md`; Phase 2/3 of
  `.opencode/plan/next-step-reconcile-and-session-gate.md`.

## 4. Documentation caveats

The following docs describe, in whole or in part, the **fabricated
feature-index model** or superseded FWU-only assumptions and should not be
trusted for the normal-mode control protocol:

- `docs/opcode-database.md` — banner added; body is superseded.
- `docs/protocol-reference.md` — normal-mode opcode section + "Report ID 0x6A"
  are superseded.
- `docs/analysis/direct-hid-probing.md` — historical; authoritative sections marked.
- `docs/analysis/final-findings.md` — FWU-focused; the "unknown trigger" claim is
  superseded by the cracked framing.
- `README.md` — battery row overstated; firmware row understated.
- `.opencode/plan/comprehensive-roadmap.md`,
  `.opencode/plan/python-cli-control-sync.md` — premise on `FeatureIndex`.

**Authoritative references:** `docs/verified-secom-opcodes.md` (protocol),
`docs/analysis/final-findings.md` (firmware-update history), this document (status).
