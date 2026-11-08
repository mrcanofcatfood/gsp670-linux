# The SECOM "session handshake" — static analysis of the value-GET gate

**Date:** 2026-10-12
**Target:** `artifacts/dlls/EPOSGamingSuiteService`
**sha256:** `350d5ec4dea1f6440c83da82a0155af1d7aca02250e3f31eb7e3ebf472b8dd44`
**Method:** radare2 6.2.2 (`aaa`, `pdf`/`pdc`, string xrefs, raw-pointer
vtable walk). REPL: Ghidra 12.1.4 is installed but the REA provider is not
configured; r2 reproduces the existing `fcn.*` addresses.
**Question answered:** *Why do the SECOM value GETs (`0x0e` battery, `0x10`
sidetone, `0x13` noise-reduction, `0x17` latency, `0x1b` auto-power-off) only
link-ACK, and why does `0x04` report `00 00`, even with a live RF link?*

> **Revision (2026-10-13):** re-analysed with Ghidra 12.1.4 headless *and*
> `objdump -Mintel` on the raw PE. The event key's middle word is **not** a
> uniform `00 f0` namespace — it varies per source component (battery `0x000f`,
> ANC-state/tone `0x0007`, speaker-mic `0x001d`, device PDL `0x0029`). The full
> corrected key table + payload schemas are in **§6.1**. The earlier `12 00 f0
> 00` battery bytes and the `23 00 f0 00 01 00` = ANC-state label were wrong.
>
> **Revision 2 (2026-10-13, GAP-RE-1 resolved):** there is **no event
> subscription handshake at all** for the events that *do* flow. `enable_events`
> / `set_battery_events` (`0x685890` / `0x685b80`) set a host-side event-mode
> flag and log the change; **no RTX packet is built for them**. The dongle
> pushes link/button events **unconditionally** once the headset is linked —
> confirmed on hardware (power-cycles → `SubDevicesChanged`; button presses →
> unhandled `0x1d` frames), with no host command sent. The earlier 150 s silent
> listen saw nothing because the headset was **not actively linked** (and the
> "battery-status button" hypothesis was wrong — see §2.7).
>
> **Revision 3 (2026-10-13, GAP-RE-1b hardware result):** battery events
> **do not self-emit** on this dongle. With the headset verifiably RF-linked
> and the charger plugged/unplugged 3–4×, the dongle pushed **no**
> `Battery_Events_Percentage`/`ChargingChanged` (`12 00 0f 00 …`) frames in
> ~6 min of passive listening, and `0x0e` serves no value on the GET path.
> The §6.1 battery keys are in the receive-side dispatcher table but were
> never observed to fire on hardware. **Static closure (same day, §6.2):**
> the re-opened `set_battery_events` `[+0x74]` slot is a **read-only getter**
> and the full chain terminates in-process (exhaustive wire-builder caller
> check) — so battery pushes are **not** gated by a host enable command;
> GSA 70 firmware 3.14.2 simply never emits them on the passive channel.
> **§6.4's "listen for `12 00 0f 00`" is falsified for battery**;
> link/button events are unaffected.

---

## 1. TL;DR verdict

**The values are push-driven events, not GET-driven replies.** The GSA 70
dongle is a *base station* that (a) enumerates the headset as a **sub-device**
and (b) emits typed **device→host events** for telemetry. The legacy Capricorn
GET opcodes are a *parallel, older* command path: the dongle transport-ACKs
them (pure link-layer `05 30`) but its firmware does not serve a value reply on
that path. There is **no hidden parameter on the GET** (the host frame is
byte-identical to the service's) and **no extra "device index" on the wire**.

Practical consequence: battery %, charging state, sidetone, noise-reduction,
auto-power-off and the sub-device list are all delivered as events; a
host-side implementation should **listen** for them, not poll the GET opcodes.
No subscription command exists (GAP-RE-1 resolved 2026-10-13) — the dongle
emits events by default; the only precondition is an active RF link.

---

## 2. Evidence

### 2.1 Two (three) protocol layers, not one

The service is not "one opcode table". Strings and vtables reveal three layers:

| Layer | Class(es) | Where | Wire |
|---|---|---|---|
| Transport | `CCapricornDatagram` | `getHIDBuffers` `0x004c7b40`, `EncodeDatagram` `0x004ce570`, `DecodeDatagram` `0x004ce7e0` | `EB FE 01 00` + `04 00` marker + opcode/len/CRC/payload (the framing already cracked) |
| Command interface | `QtilSecomParser` → `CSecomParserAdapter` | vtable @ vaddr `0x8279a0`; wrapper fns `0x00648130` (`get_input_events`), `0x006483d0` (`get_battery_percent`), `0x006477f0` (`set_battery_events`) | Capricorn opcodes |
| Base-station / service | `ModiBaseStationDevice`, `ModiHeadsetDevice`, `ModiUsb*` | `Service_*` commands | a `<word0> <word1>` **event key** on the *event* channel (`word1` usually `0x00f0`) |

The `QtilSecomParser` wrappers are non-virtual templates that log an error and
call a single generic dispatcher (`[vptr + 0x18]`); the concrete opcode lives in
the `CSecomParserAdapter` vtable. The recovered `CSecomParserAdapter` vtable
(`vaddr 0x8279a0`, verified: `[0x8279b8] == 0x004b0b10`) confirms the known
adapter methods:

```
slot 12 getFwVersion(0x4a4700)   slot 16 getSideToneValue(0x4b2e10)  slot 20 ...
slot 13 getSerialNo(0x4a5680)    slot 17 setSideToneValue(0x4b44a0)  slot 21 ...
slot 14 getBatteryPercentage(0x4b0b10) slot 18 setNoiseReduction(0x4b4ff0)
slot 15 ...                      slot 19 getNoiseReduction(0x4b4a40)
slot 23 getRemoteDeviceInfo(0x4b6810) slot 24 getNbrLinkKeys(0x4b6db0)
slot 25 getDeviceAddress(0x4a5bf0)   slot 53 EnterDfu(0x4b2720) slot 54 getDfuType(0x4b10c0)
```

`CSecomParserAdapter::getBatteryPercentage` (`0x004b0b10`, = vtable slot
`+0x18`) builds opcode `0x0e` exactly as documented — there is **no session
argument** to add.

### 2.2 Telemetry is event-driven (the decisive strings)

The value consumers are event handlers, not GET parsers:

```
Received Battery_Events_Percentage from device.
Received Battery_Events_ChargingChanged from device.
Received Sound_Events_SideToneGainChanged from device.
Received Sound_Events_VolumeLimiterModeChanged from device.
Received Service_Events_AutoPowerOffTimerStatus from device.
Received Service_Events_AutoPowerOffTimerValue from device.
Received Service_Events_SubDevicesChanged from device.
Received Input_Events_VirtualButtonEvent from device.
Received Input_Events_MMIConfigurationUpdate from device.
Received Device_ConnectionEvents_PairingStatusIndication from device.
QtilDevice::create_battery_status: charging_status received from SecomParser is {:#06x}, battery level is {}%
QtilDevice::send_battery_statuses_event: error while reading the battery status {}
```

The *event ids* ride the event-key stream already observed live
(`docs/verified-secom-opcodes.md` §5.2): `1d 00 f0 00 …` (opcode field `0x0004`,
marker `00 01`/`ff 01`), `08 00 f0 00 …` and `01 00 f0 00 …`. The second word is
usually `0x00f0` but varies (battery uses `0x000f` — see §6.1). So the bytes the
earlier probes dismissed as "undecoded telemetry" **are** the typed event
stream, and battery/sidetone/etc. arrive there.

### 2.3 The sub-device (nested-device) model

The headset is a **sub-device** of the dongle base station, and the value
commands are **sub-device commands**:

```
QtilDevice::create_nested_secomparser: Created nested secomparser [new_subdevice_index = {}]
QtilDevice::enumerate_nested_devices ...
QtilDevice::has_nested_devices ...
QtilDevice::has_nonsecomparser_nested_subdevice: could not get nbr_link_keys ...
QtilDevice::has_nonsecomparser_nested_subdevice: could not query remote device info ...
ModiBaseStationDevice:enumerate_nested_devices ...
ModiBaseStationDevice::detect_bt_headset: No BT headsets reported by GetSubDevicesConnection on dongle (devices={:#x})
ModiBaseStationDevice::handle_event: Got a SubDevicesChanged event (devices={})
ModiBaseStationDevice::is_dongle_connected: Service_GetSubDevicesConnected: devices={}
CSecomParserAdapter::populateNestedDevices / getListofNestedDevices / getSubDeviceDetails / handleNestedDeviceEvent
```

`0x04` (`getNoOfSubDevicesConnected`) is the **Capricorn** view of this list and
returns `00 00`; the base-station view is `Service_GetSubDevicesConnected`,
whose changes arrive as the `Service_Events_SubDevicesChanged` **event**. The
two views are not the same channel, which is exactly why "link is live (events
flow) but `0x04` says 0 devices" is not a contradiction.

### 2.4 The "event-control / enable step" is host-side only (corrected 2026-10-13)

```
ModiBaseStationDevice: Service_EventControl failed: result = {}, device_status = {}, requested_status = {}
QtilSecomParser::set_input_events_state: failed to set input events '{}' response {}
QtilSecomParser::get_input_events: failed to get the input events, error {}
QtilSecomParser::set_battery_events: failed to set battery events, error {}
hModiHeadsetDevice::enable_events: battery events are not enabled because current fw < {}
ModiBaseStationDevice::enable_events: failed to {} events
```

These strings once looked like a "session handshake" — a `Service_EventControl`
command (and/or `set_input_events_state` / `set_battery_events`) that *enables*
event delivery, with a **firmware-version gate** for battery events.

**They are not.** Static tracing of `enable_events` (`0x685890`) and
`set_battery_events` (`0x685b80`) shows they only:
1. check/set a host-side event-mode flag (`[obj+0x340]` fw gate, §2.8), and
2. emit a diagnostic via the fmt log formatter (`0x5b0880` — mislabelled as a
   "secom parser" in earlier notes; the `0x0c`/`0x0f`/`0xfc`/`0xfff` values at
   its call sites are fmt `{}` template arguments, not wire bytes).

Neither function builds an RTX datagram. `RtxDatagramIo::split_request_into_packets`
(`0x67a070`, report id `0x58`, 64-byte, `0xEE`-padded) is reachable **only** from
the request/response SECOM senders, never from the event-enable path. The GSA 70
pushes events unconditionally; the receive dispatcher `0x643b10` has no
subscriber gate.

### 2.5 Ruled out (so it isn't re-tried)

* **A second `03 04` "Modi datagram class".** Already debunked: the `03 04`
  byte sequences in `ModiUpdater.dll`/`HidDfu.dll` are **ASN.1 X.509 OIDs**
  (`0d 06 09 60 86 48 01 65 03 04 …`), i.e. certificate data, not a frame
  class (`analysis/final-findings.md` §…, `analysis/direct-hid-probing.md`).
* **A device-index/handle field on the GET.** `getHIDBuffers` shows a fixed
  4-byte payload per opcode; `0x0e` is always `12 00 03 00`.
* **A slow reply.** A 15 s passive listen after `0x0e` yields only the `05 30`
  ACK (docs §5.2).
* **A fresh re-link.** A full unplug/re-plug + headset power-cycle does not
  unlock the GETs (docs §5.2).

### 2.6 Live re-confirmation (2026-10-12, this session)

Dongle `1395:0300` on `/dev/hidraw1`; headset currently **not** actively
linked (6 s passive listen = 0 frames):

```
0x00 -> DATA 3.14.2          0x03 -> DATA 4e00f2e294001600
0x01 -> DATA <zeros>         0x04 -> DATA(0x0004) 0000
0x02 -> DATA "EPOS GSA 70"   0x0e/0x10/0x13/0x17/0x1b -> ACK only
```

### 2.7 Live event capture and the event-enable attempt (2026-10-12)

With the headset powered on and RF-linked, a passive listen did surface the
event stream:

```
DATA10  marker=1001 op=0x0000 pl=0100 f000 0100 0000   (status toggling ...-0100)
EVENT   marker=0001 op=0x0004 pl=1d00 f000 0100 0100 0000   (unhandled id 0x1d)
```

Then the approved gated "event-enable" sweep (exact bytes logged with CRC,
`lsusb`/PID watched after each). **No re-enumeration** (PID stayed `0300`):

| sent opcode | payload | result |
|---|---|---|
| `0x05` | `01 00 0a 00` | DATA class `0x0004` (sub-device reply, echo only) |
| `0x0A` | `06 00 13 00` | ACK `0x0002`, echo only |
| `0x15` | `08 00 f0 00` | ACK `0x0008`, echo only |
| `0x1C` | `06 00 1c 00` | ACK `0x0007`, echo only |

A following 150 s passive listen while the **battery-status button was pressed**
captured **no** `Battery_Events_Percentage` (0 frames). Two findings, separately
important:

- The undeclared Capricorn opcodes do not change the event flow (consistent
  with Revision 2 — there is no subscription to toggle).
- The battery-status button is **not** an event trigger, and the headset's RF
  link was marginal during this capture. Battery events correspond to *level
  crossings* and *charger connect/disconnect* — the definitive check (GAP-RE-1b)
  is a passive listen with the headset firmly linked and the charger state
  toggled.

### 2.8 The battery-event firmware gate

`hModiHeadsetDevice::enable_events` (`0x00685890`) does:

```
0x006858b9  cmp byte [esi + 0x340], 0
0x006858c0  jne 0x6859db              ; fw OK  -> set_battery_events(...)
0x006858c6  lea eax, [ebp - 0x60]
0x006858c9  mov ecx, 0x8f1c30         ; FirmwareVersion(2,0,0) threshold object
0x006858cf  call 0x6398d0             ; format "current fw < {}" message
```

and `[obj + 0x340]` is set in the headset-device init at `0x006856fd`
(`mov byte [esi + 0x340], al`) from `call 0x637fe0` with the threshold
`push 0x8f1c30`. The threshold object is a static `FirmwareVersion(2,0,0)`
(constructed at `0x00479b60`–`0x00479b7d`: `push 0; push 0; push 2;
mov ecx, 0x8f1c30` — note: the `push 0x14; push 5; push 1` sequence at
`0x479b80` is the *separate* `FirmwareVersion(1,5,20)` **EnterDfu** gate at
`0x8f1c70`, §6.5). So battery-event delivery is gated on
`headset_fw >= 2.0.0`; the GSP 670 headset is `3.2.6`, which satisfies the
gate. The gate only guards the host's *local* flag; it does not guard any
wire command — there is no subscription to send (Revision 2, §2.4).

---

## 3. Verdict and what remains

**Resolved:** the value GETs do not "need a magic parameter". The values are
**event-driven**; the plain GETs are a superseded Capricorn path the dongle
transport-ACKs but does not serve. The `0x04` = `00 00` result is the Capricorn
sub-device view, not the base-station view (`Service_GetSubDevicesConnected` /
`Service_Events_SubDevicesChanged`).

**Resolved in Phase 3 (Ghidra headless):** the receive-side key is
**`<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]`** (the device→host event
key; `word1` is usually `0x00f0` but varies — see §6.1). The full event-key
table and the separation of the **SecoM** channel from the **Rtx**
firmware-update channel are in **§6**.

**Resolved (Revision 2, 2026-10-13):** there is **no outgoing
`Service_EventControl` request to recover**. The `Service_*`/`set_battery_events`
functions are host-side bookkeeping (flag flip + log). The receive dispatcher
`0x643b10` pushes events without any subscription gate.

**Reasonable end state:** document battery/sidetone/noise-reduction/latency/
auto-power-off as **event-sourced** values (read-only via the event stream),
mark the GET adapter methods as *not served by the GSA 70 firmware*, and keep
the setters (which ACK) as write-only.

---

## 4. Recommended live experiment (gated — needs approval + linked headset)

Goal: prove that the linked headset's values arrive as events. **No setters, no
`0x07`, no `0x09`** unless explicitly approved.

1. **Read-only link check (approved):** with the headset powered on and RF
   linked, run the safe GET sweep + a 30 s passive listen and classify every
   frame by marker + event key. Expect `Service_Events_SubDevicesChanged`
   (`01 00 f0 00 01 00 …`) when the link forms and `Battery_Events_*`
   (`12 00 0f 00 …`) on battery state changes (level crossing, charger
   connect/disconnect — **not** the battery-status button; see §2.7).
2. **`0x15` (request body `08 00 f0 00`) with a live link** (already ACKs;
   re-test and watch for a follow-up event).
3. ~~Event-enable probe~~ — **REMOVED (Revision 2):** static analysis proves no
   subscription command exists; probing "enable" opcodes was based on the
   superseded §2.4 reading.
4. Fold the result into `docs/verified-secom-opcodes.md` and the library
   (`events.py`) either way.

## 5. Limits of this analysis

* The `Service_*`/`Modi_*` **command ids were not recovered** from static data
  — because there is nothing to recover: the event-enable functions are
  host-side bookkeeping (Revision 2, §2.4). The *receive-side event keys*
  **were** recovered (see §6). The `QtilSecomParser` wrapper → concrete
  dispatch for the five unnamed Capricorn opcodes (`0x05`, `0x09`, `0x0A`,
  `0x15`, `0x1C`) remains unproven — none of them is an event-subscription
  command.
* The `QtilSecomParser` wrapper → concrete dispatch is via one generic vtable
  slot, so opcode→Qtil-name mapping for the five unnamed Capricorn opcodes
  (`0x05`, `0x09`, `0x0A`, `0x15`, `0x1C`) remains unproven.
* **Update (Phase 3):** the Ghidra headless pass has now been run (r2 `pdc` was
  coarse). It recovered the event-key encoding and the Rtx FWU channel
  (§6). Converting the coarse r2 addresses to the Ghidra project
  (`/tmp/opencode/ghidra-proj`, program `EPOSGamingSuiteService`) is the
  recommended next step for any further protocol work.

---

## 6. Phase 3 — the event-key encoding and the Rtx split (Ghidra)

**Method:** Ghidra 12.1.4 headless, project `/tmp/opencode/ghidra-proj`,
program `EPOSGamingSuiteService`; scripts in `/tmp/opencode/ghidra-scripts`
(`RDecomp*.java`, `RScalar.java`, `RRefs.java`). r2 addresses translate to the
Ghidra project one-for-one (same image base).

### 6.1 The device→host event key (corrected 2026-10-13)

The dispatcher `FUN_00643b10` matches each known notification against a small
stack key:

```c
local_24 = 0xf0012; local_20 = 4;     // Battery_Events_Percentage
if (FUN_00642d30(&local_24)) { ... }  // 3-word (6-byte) compare
```

`FUN_00642d30` compares **three u16 words** of the datagram body against the
key; `FUN_00642cf0` compares **two u16 words**. So every Modi notification
begins with:

```
<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]
```

**`word1` is not a fixed `00 f0` namespace.** It is `0x00F0` for most
notifications but is `0x0007` for the ANC-state / tone events, `0x000F` for the
battery events, `0x001D` for the speaker-mic optimised-mic event and `0x0029`
for the device PDL event. (Earlier notes claimed a uniform `f0 00`; the raw
disassembly contradicts that — e.g. the battery constant is `0x000f0012`, not
`0x00f00012`.) `word1` is matched as a datagram *field*; an instruction scan for
it finds only these key constants, not a shared tag.

Ground truth (verified with both Ghidra and `objdump -Mintel` on the raw PE —
e.g. `64409a: c7 45 e0 12 00 0f 00  mov DWORD PTR [ebp-0x20],0xf0012`):

| key bytes | words (w0, w1, var) | value schema | handler (log string) |
|---|---|---|---|
| `23 00 f0 00 01 00` | (0023, 00f0, 1) | u8, u16 | `Component_Events_StatusChange` |
| `17 00 07 00`       | (0017, 0007, —) | u16 | `ANC_AdaptiveNoiseCancelationStateChanged` |
| `17 00 f0 00 01 00` | (0017, 00f0, 1) | u8  | `ANC_Events_HearThroughChanged` |
| `17 00 f0 00 02 00` | (0017, 00f0, 2) | u16 | `ANC_Events_AdaptiveNoiseCancelationLevelChanged` |
| `12 00 0f 00 03 00` | (0012, 000f, 3) | u16 | `Battery_Events_ChargingChanged` |
| `12 00 0f 00 04 00` | (0012, 000f, 4) | u8  | `Battery_Events_Percentage` |
| `10 00 1d 00`       | (0010, 001d, —) | u8  | `SpeakerMic_OptimizedMicSettingChanged` |
| `10 00 f0 00 01 00` | (0010, 00f0, 1) | u16 | `SpeakerMic_Events_TalkWhileMuteStatus` |
| `0a 00 f0 00 02 00` | (000a, 00f0, 2) | u16 | `Sound_Events_SideToneGainChanged` |
| `0a 00 f0 00 03 00` | (000a, 00f0, 3) | u8  | `Sound_Events_PcSoundPriority` |
| `0a 00 f0 00 04 00` | (000a, 00f0, 4) | u8  | `Sound_Events_VolumeLimiterModeChanged` |
| `08 00 f0 00 03 00` | (0008, 00f0, 3) | u8 ×4 | `Input_Events_VirtualButtonEvent` |
| `08 00 f0 00 07 00` | (0008, 00f0, 7) | u8 ×2 | `Input_Events_MMIConfigurationUpdate` |
| `07 00 07 00`       | (0007, 0007, —) | u16 | `Tone_AudioPromptsModeChanged` |
| `06 00 29 00`       | (0006, 0029, —) | u8  | `Device_DevicePdlModeChangeIndication` |
| `06 00 f0 00 01 00` | (0006, 00f0, 1) | u16 | `Device_ConnectionEvents_ConnectionStatus` |
| `06 00 f0 00 04 00` | (0006, 00f0, 4) | u8  | `Device_ConnectionEvents_PairingStatusIndication` |
| `06 00 f0 00 05 00` | (0006, 00f0, 5) | u8, u8 | `Device_ConnectionEvents_ConnectionChangeEvent` |
| `06 00 f0 00 07 00` | (0006, 00f0, 7) | u8  | `Device_ConnectionEvents_MultipointConnectionInScoStatus` |
| `01 00 f0 00 01 00` | (0001, 00f0, 1) | u16 | `Service_Events_SubDevicesChanged` |
| `01 00 f0 00 02 00` | (0001, 00f0, 2) | u16 | `Service_Events_AutoPowerOffTimerValue` |
| `01 00 f0 00 03 00` | (0001, 00f0, 3) | u8  | `Service_Events_AutoPowerOffTimerStatus` |

Payload schema detail. After the key the handler advances the in-byte-stream past
it (`FUN_006b3f50(6)` for three-word keys, `FUN_006b3f50(4)` for two-word keys —
`n` = key length in bytes, not a fixed 6) and then reads the value fields:
`FUN_006b3cf0` = u8, `FUN_006b3d40` = u16 LE. The `06`/`01` family uses four
reader helpers that are just `seek(6)` + read: `FUN_00643a40`/`FUN_00643ac0` =
u16, `FUN_00643a80` = u8, `FUN_006439e0` = two u8 packed into a u16 (low =
first byte). `Component_Events_StatusChange` reads a u8 then a u16.

Two-word keys are matched with `FUN_00642cf0`; a two-word key with a two-byte
value is also six bytes long, so the three-word lookup is tried first and the
two-word form is the fallback.

The captured link frame `00 01 op=0x0004 pl= 1d 00 f0 00 01 00 01 00 00 00` is
`<word0=0x001d> <word1=0x00f0> <variant=1> …` — no dispatcher case exists for
`word0=0x1d`, so it is an **unhandled** event (the `0x1508` "VirtualButton"
label from the early capture was a guess).

The earlier `08 00 f0 00` = `Service_GetSubDevicesConnected` note was a
mis-identification: `08 00 f0 00` is not in the receive-side dispatch table
(it is the `0x15` *request* body). The real sub-devices-changed event is
`01 00 f0 00 01 00` = `Service_Events_SubDevicesChanged`.

**Wired into the library/CLI (2026-10-13):** `protocol.decode_event_key()` /
`protocol.format_event_key()` and `Frame.event_name` decode these keys live;
`protocol.EVENT_PAYLOAD` records each value schema; `gsp670 monitor` /
`gsp670 events` print the recovered name (or an `unknown event (…)` description)
for every event-word payload. See `tests/unit/test_event_keys.py` and
`docs/current-status.md`.


### 6.2 `Service_*` event-enable functions are host-side, vtable-dispatched

`Service_EventControl` (`FUN_0061a560`), `set_battery_events`
(`FUN_00685b80`, `FUN_005fc100`) and the `QtilSecomParser::*` wrappers
(`FUN_00647e80`, `FUN_00648bb0`) are thin templates that fetch a service object
via `[this+0x100]`/`[+0x24]` and then call a **per-command vtable slot**, e.g.:

```c
// ModiBaseStationDevice::set_battery_events(char on)
local_16 = (char)on == 1;                            // requested_status
puVar5   = (**(code **)(*obj + 0x100))(&local_2c);   // -> IModiSecomparser
result   = (**(code **)(*puVar5 + 0x74))(on, &local_15, *(u16*)(obj + 0x338));
//                                                         ^ slave / sub-device id
```

So there is **no event-key id literal to find** for an outgoing request —
because the *event-enable* path never sends one (Revision 2, §2.4). These
vtable-dispatched calls run **host-side bookkeeping**: update a flag, write a
log line. The only wire traffic built around the secomparser interfaces are the
request/response SECOM GETs/SETs (`RtxDatagramIo::split_request_into_packets`,
`0x67a070`). `[obj+0x338]`
is the 16-bit **slave / sub-device id** (matches `…for slave {:#06x}`); the
`[obj+0x340]` byte is the **battery-events fw gate** — `headset_fw >= 2.0.0`
(static initializer at `0x479b64` builds the gate object at `&DAT_008f1c30` as
`FirmwareVersion(2,0,0)`, family `5`; see §6.5).

**Chain resolved end-to-end (2026-10-13, Ghidra headless; closes the
GAP-RE-1b "re-opened" question):** the `[+0x74]` slot is **read-only**, and the
whole event-enable chain terminates in-process — nothing reaches the USB wire:

```
ModiBaseStationDevice::set_battery_events  (FUN_00685b80)
  host flag + fmt-log "new_event_mode {}"           <- no wire call
  [device_vtbl+0x100]() -> secomparser
    [secomparser_vtbl +0x74]  == FUN_0064b7a0       <- READ-ONLY getter
      [.. +0x1bc]() -> sub-device proxy             (FUN_0064c470 / ctor
                                                    FUN_006b4480, vtbl 0x8133c0)
        [proxy_vtbl +0x50] == FUN_006b5090          (build 52-byte cmd obj 0x13/1,
                                                    FUN_00645db0 EXEC)  <- READ
        [proxy_vtbl +0xc4] == FUN_006b8d40          (same 52-byte cmd shape)  <- SET
```

`FUN_0064b7a0` (the `[+0x74]` implementation) fetches the sub-device proxy via
`[+0x1bc]`, **reads** a u16 through the proxy's `[+0x50]`, and returns it to
the caller for the `device_status != requested_status` comparison — i.e. it
*reads the current event state*, it never writes it. The `[+0x50]`/`[+0xc4]`
terminals build 52-byte request/response structs
(`FUN_006b3c80(4,0,1,2)` / `FUN_006b3c10(6,0,1,2)`, setter `FUN_006b3e40`,
extractor `FUN_006b3d40`) and execute them **in-process** via `FUN_00645db0`
on the DECT sub-device; their callee set contains **no** Rtx/HID builder.

**Exhaustive wire-builder caller check:** the *complete* set of direct callers
of the two 64-byte report builders is:

| builder | callers |
|---|---|
| `split_request_into_packets` (`0x67a070`) | `FUN_006796b0` (SECOM send-with-response, itself only from `FUN_00679a30`), `FUN_00679ee0` |
| `send_request_without_response` (`0x679ee0`) | the 12 §6.3 FWU builders + `FUN_006853e0` (keepalive, registered only in the Rtx handler tables `0x8052e4`/`0x8053a4`) |

No event-enable function appears in either list, so `set_battery_events` /
`Service_EventControl` / the `QtilSecomParser` wrappers **cannot** produce a
host→dongle packet. Combined with the GAP-RE-1b hardware result (battery
frames never fire even linked, Revision 3), battery events are **not gated by a
host command**: GSA 70 firmware 3.14.2 simply does not emit them on the passive
channel, and no GET serves the value either.

### 6.3 Firmware update is a separate **Rtx** channel, not SECOM

`FwuEnableRequest` (`FUN_0067bf90`, driven by `FUN_0067d400`) is serialized with
a small `std::vector<uint8_t>` helper family:

* `FUN_006d5fc0(vec, u16)` = append **u16 LE**
* `FUN_006d60d0` / `FUN_006d5f90` = append **u8**
* `FUN_006d6010` = append **u32 LE**; `FUN_00679460` = insert

and dispatched by `FUN_00679ee0` = **`RtxDatagramIo::send_request_without_response`**.
`RtxDatagramIo::split_request_into_packets` (`FUN_0067a070`) then builds **64-byte**
reports: byte 0 = **`0x58`**, then ≤63 payload bytes, padded with **`0xEE`**,
plus a per-request 1-byte sequence counter stored at `this+8`.

Recovered FWU command table (builder → request id → expected response id):

| purpose | builder | request | response |
|---|---|---|---|
| enable | `FUN_0067bf90` / `FUN_0067d400` | `0x4f00` | `0x4f01` |
| update | `FUN_0067e220` / `FUN_0067e390` | `0x4f03` | `0x4f04` |
| — | `FUN_0067e500` / `FUN_0067e6f0` | `0x4f06` | — |
| — | `FUN_0067d780` / `FUN_0067d910` | `0x4f08` | — |
| — | `FUN_0067daa0` / `FUN_0067dc30` | `0x4f0a` | — |
| — | `FUN_0067ddc0` / `FUN_0067df80` | `0x4f0e` | — |
| — | `FUN_0067c0d0` | `0x4f10` | — |
| keepalive | `FUN_0067c850` | `0xf066` | — |

`FwuEnableRequest` payload = `00 4F <A> <B>` (two caller-supplied bytes) plus an
expected-response sub-record `0x4f01, 1, 01 00`. The earlier live test sent
`0x4F00` with `00 00` on the **SECOM `04 00`** channel — the wrong transport —
which is why it NAKed. FWU must go through the Rtx layer.

### 6.4 Consequence for the GSP 670

Battery / sidetone / ANC / auto-power-off telemetry arrives as **events** (per
the receive-side dispatcher); the `Service_*` *setters* are write-only and
virtual-dispatch-selected; the plain Capricorn GETs remain a superseded path.

**Hardware caveat (Revision 3, 2026-10-13):** of these event families, only
*link* (`SubDevicesChanged`, `01 00 f0 00 01 00`) and *button/0x1d* events were
observed to actually fire on the dongle. **Battery events (`12 00 0f 00 …`)
never fired** with a confirmed link + charger toggles, and `0x0e` serves no
value. sidetone/ANC events remain untested on hardware. So:
- link/button event listening works as documented — no further work needed;
- battery "listen for `12 00 0f 00`" is **falsified** — and the fallback
  hypothesis (host enable command) is **closed by §6.2's resolved chain**:
  the `[+0x74]` dispatch is read-only and no event-enable code can reach the
  Rtx wire builders. Battery % is **unobtainable through this dongle** (no
  push, no GET).

### 6.5 The FWU mode dance (traced, 2026-10-12)

The "update mode" choreography lives in `ModiFirmwareUpdater`, **not** in the
SECOM/Rtx request layer. All addresses below are from the headless Ghidra pass.

**Entry — `FUN_0068ac70`** (`"MODIFWU: .... performing MODI firmware update ..."`,
registered at the command-dispatch slot `0x7e7660+0x10`): builds the component
update list (`FUN_0068a2a0`) and, if non-empty, checks the **device mode**
(`(**(code **)(**[this+0x48] + 0xfc))()` → `IUsbDevice`-style mode getter):

| mode | branch |
|---|---|
| `3` (service) | `"MODIFWU: device in service mode, proceeding"` → run update inline |
| `5` (update) | `"MODIFWU: device already in update mode, proceeding"` |
| other | **gate check** (below), then reboot dance |

**Gate — `FUN_00637fc0(&DAT_008f1c70)`**: `FirmwareVersion::compare(device, gate) < 0`.
The gate object at `0x8f1c70` is built by the static initializer at `0x479b80`
as **`FirmwareVersion(1, 5, 20)`** (ctor `FUN_00638790`, nibble-encodes each
decimal field into a `std::vector<uint32_t>`; family `5` set at `[obj+0x38]`).

* device `>= 1.5.20` → **`FUN_0068b300`** = `prepare_update_mode`:
  `"rebooting into FWU mode (EnterDfu) and set reboot requested flag to true"`,
  vtable `[+0x10]` dispatch on the MODI singleton with the logging sink
  `&DAT_007d2278`, state `[updater+0x10] = 0x44c`,
  `FUN_00493c00(L"Putting device into firmware update mode")`, then a **45 s
  reboot-await timer** (`(*[updater+0x48]+0xd8)(&ms=45000, 0)`) and the
  reboot-requested flag `[updater+0x4c] = 1`.
* device `< 1.5.20` → **`FUN_006874f0`** logs
  `"MODIFWU: device firmware {} does not support enter DFU mode, proceeding"`
  and takes the legacy path — i.e. EnterDfu was only introduced in 1.5.20.

**The actual `FwuEnableRequest`** (`FUN_0067d400` → builder `FUN_0067bf90` →
`RtxDatagramIo::send_request_without_response`): payload `00 4F <A> <B>` with the
two bytes taken from the caller's stack slots (0x4/0x8) plus the expected-response
sub-record `0x4f01, 1, 01 00`. `FUN_0067d400` is referenced only from the Rtx
handler tables at `0x805304` / `0x8053c4` alongside the other FWU builders
(`0x67e140/67e220/67e500/67daa0/67ddc0/67d780/…`).

**Take-away for the live sweeps:** the `0x4F00` SECOM NAK and the "bat‑button
does nothing" results are both explained by structure, not protocol skill:
1. FWU enable is an **Rtx** report (`0x58`, 64-byte, `0xEE`-padded) — never
   `04 00` SECOM; and
2. it only fires from inside the mode dance, after the `>= 1.5.20` gate and a
   **`service-mode` precondition** (`**[updater+0x48]+0xfc`), with a 45 s
   reboot window and `[updater+0x4c]` set. The dongle `3.14.2` passes the 1.5.20
   gate; the missing pieces are the Rtx transport plus the caller-supplied
   `<A> <B>` bytes.

The **battery-events gate** is a *separate* constant: `&DAT_008f1c30` built at
`0x479b64` as **`FirmwareVersion(2,0,0)`** and cached by the
`ModiHeadsetDevice` ctor (`FUN_00685650` → `FUN_00637fe0`) into `[obj+0x340]`;
`enable_events` (`FUN_00685890`) skips battery events with
`"battery events are not enabled because current fw < {}"` when the byte is
unset. Headset `3.2.6` passes — and since the flag change is host-side only
(Revision 2, §2.4), no wire command is associated with it.
