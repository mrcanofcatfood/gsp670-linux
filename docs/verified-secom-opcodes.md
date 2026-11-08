# Verified Capricorn / SECOM Protocol

**Status:** ✅ Verified against the shipped service binary **and** live
GSA 70 dongle (`1395:0300`, `/dev/hidraw1`) and GSP 670 headset
(`1395:008a`, `/dev/hidraw4`, direct USB).
**Source of truth:**
`artifacts/dlls/EPOSGamingSuiteService` →
`CCapricornDatagram::getHIDBuffers` @ `0x004c7b40`,
`::getPayload` @ `0x004cb9c0`,
`::EncodeDatagram` @ `0x004ce570`,
`::DecodeDatagram` @ `0x004ce7e0`,
`::parseDatagram` @ `0x004c8330`,
`::GetBatPercentage` @ `0x004cea40`,
`::verifyOpcode` @ `0x004cbfb0`,
`::sendCommand` @ `0x004cc460`,
`::writeCommand` @ `0x004cb270`,
CRC @ `0x004cbf40`.

---

## 1. Transport

The vendor HID interface (interface 5) has **report ID `0x01`, a 106-byte
input report and a 106-byte output report** (107 bytes including the report
ID). There is **no interrupt-OUT endpoint**: the output report is delivered via
a HID `SET_REPORT` control transfer. Writing the wrong buffer length resets
(re-enumerates) the dongle, so always write exactly 107 bytes.

The dongle exposes **6 USB interfaces**: 0–4 are USB Audio (two control +
streaming pairs), and **interface 5 is the only HID interface** (class 3) with
a **single IN endpoint** (`0x81`, 64-byte packets). There is no second
vendor/registration interface, so this HID channel is the *only* control path —
and the dongle exposes **no `power_supply` node** on Linux, so battery is only
reachable through this protocol.

```
byte  0      = 0x01            report id
bytes 1..4   = EB FE 01 00     sync
bytes 5..6   = 04 00           host marker (host -> device)
bytes 7..8   = opcode, LE      == the SECOM command (0x00..0x1C)
bytes 9..10  = payload length, LE
byte  11     = CRC-8(payload)  poly 0x07, init 0xFF, MSB-first
byte  12     = 0x00
bytes 13..   = payload
```

Build it with `gsp670.protocol.frame(opcode, payload)`.

## 2. Reply classes (live-verified)

| Marker | Meaning | Opcode field | Payload |
|--------|---------|--------------|---------|
| `05 30` | link **ACK** | `req >> 2` (0x14/0x15 return `0x0008` instead) | echo of the request payload |
| `04 10` | **NAK** | `req >> 2` | empty (CRC `0xFF`) |
| `04 00` | **data reply** | `0x0000` | 4-byte request header echoed, then the value bytes |
| `04 00` | **sub-device reply** (`0x04`, `0x05`) | `0x0004` | echo of the request header (+ `00 00` value for `0x04`) |

Notes:

* The **data reply echoes the host marker** (`04 00`) — that is why it is not
  `10 01`. The field at bytes 7..9 is not a strict echo: it is a *reply class*
  (`0x0000` plain data, `0x0004` device-event/sub-device class, `0x0008` for
  the `0x14`/`0x15` ACKs, `req >> 2` for most other ACKs).
* The ACK is a *pure link-layer* acknowledgement; a bogus opcode like
  `0x1234` is ACKed too. **An ACK does not mean the command did anything.**
* A NAK (`04 10`) is a rejection, e.g. `0x02` with an empty payload, or
  `0x4000` / `0x4F00` (RTX/FWU family, not enabled).
* Opcodes `0x08`, `0x0B`, `0x0D`, `0x0F` are rejected by the service with
  `"Opcode not supported"` and are never emitted.

## 3. Opcode table

Request payloads below are exactly the bytes produced by
`CCapricornDatagram::getHIDBuffers`. Writable opcodes (`0x11`, `0x12`,
`0x16`, `0x18`, `0x1A`) append `<value> 00` and use a length of 6.

| Opcode | Name | Request payload | Reply (live) |
|--------|------|-----------------|--------------|
| `0x00` | Get firmware version (`parseSwVersion`) | `01 00 03 00` | data: `… 03 00 0e 00 02 00` → `3.14.2` |
| `0x01` | Get serial number (`parseGetSerialNumber`) | `01 00 0b 00` | data: 36-byte NUL-padded ASCII |
| `0x02` | Get device name (`parseDeviceName`) | `09 00 01 00` | data: UTF-16LE `"EPOS GSA 70"` |
| `0x03` | Get device address (`parseBDAddr`) | `06 00 14 00` | data: `4e 00 f2 e2 94 00 16 00` |
| `0x04` | Sub-devices connected (`parsesubDevicesConnected`) | `01 00 09 00` | sub-dev reply `04 00 04 00`: echo + `00 00` (0 devices) |
| `0x05` | *(unknown)* | `01 00 0a 00` | sub-dev reply `04 00 04 00`: echo only |
| `0x06` | Get DFU type (`parseDfuType`) | `01 00 0d 00` | data on device mode |
| `0x07` | Enter DFU (`parseEnterDfu`) | `01 00 06 00` | data on device mode |
| `0x09` | *(unknown)* | `06 00 09 00` + 10×`00` | ACK (`05 30 02 00` = req>>2) |
| `0x0A` | *(unknown)* | `06 00 13 00` | ACK (`05 30 02 00` = req>>2) |
| `0x0C` | Nested device BT name (`parseDeviceBtName`) | `06 00 27 00` | ACK (needs headset) |
| `0x0E` | Battery percentage (`GetBatPercentage`) | `12 00 03 00` | ACK (needs headset; reply would be `12 00 03 00 <b> 00`) |
| `0x10` | **Get sidetone** (`GetSideToneGain`) | `0a 00 0c 00` | ACK (needs headset) |
| `0x11` | **Set sidetone** (`setSideToneValue`) | `0a 00 0b 00 <v> 00` | ACK |
| `0x12` | **Set noise reduction** (`setNoiseReduction`) | `0a 00 11 00 <v> 00` | ACK |
| `0x13` | **Get noise reduction** (`GetNoiseReductionLevel`) | `0a 00 12 00` | ACK (needs headset) |
| `0x14` | Nested device PID (`parsePIDNumber`) | `01 00 14 00` | ACK (needs headset) |
| `0x15` | *(unknown)* | `08 00 f0 00` | ACK |
| `0x16` | **Send latency** (`SendLatencyCommand`) | `0a 00 16 00 <v> 00` | ACK |
| `0x17` | **Get latency** (`GetLatencyLevel`) | `0a 00 17 00` | ACK (needs headset) |
| `0x18` | Remote device info (`GetRemoteDeviceInfo`) | `06 00 32 00 <v> 00` | ACK (needs headset) |
| `0x19` | Number of link keys (`GetNbrLinkKeys`) | `06 00 11 00` | ACK |
| `0x1A` | **Set auto power off** (`SetAutoPowerOffTimerStatus`) | `01 00 1f 00 <v> 00` | ACK |
| `0x1B` | **Get auto power off** (`GetAutoPowerOffTimerStatus`) | `01 00 20 00` | ACK |
| `0x1C` | *(unknown)* | `06 00 1c 00` | ACK |

`<v>` is a single byte (the service parses it with `strtol(…, 10)` and writes
one byte; the wire field is a u16 LE so the high byte is `0x00`).

## 4. Static evidence

Adapter method → opcode (from the call sites in `CSecomParserAdapter`):

| Adapter method | Addr | Opcode arg |
|----------------|------|------------|
| `getSideToneValue` | `0x004b2e10` | `0x10` |
| `setSideToneValue` | `0x004b44a0` | `0x11` |
| `setNoiseReduction` | `0x004b4ff0` | `0x12` |
| `getNoiseReduction` | `0x004b4a40` | `0x13` |
| `getBatteryPercentage` | `0x004b0b10` | `0x0e` |
| `getDfuType` | `0x004b10c0` | `0x06` |
| `EnterDfu` | `0x004b2720` | `0x07` |
| `getRemoteDeviceInfo` | `0x004b6810` | `0x18` |
| `getNbrLinkKeys` | `0x004b6db0` | `0x19` |
| `SetAutoPowerOffTimerStatus` | `0x004b8bd0` | `0x1a` |
| `GetAutoPowerOffTimerStatus` | `0x004b83b0` | `0x1b` |
| `SendLatencyCommand` | `0x004b61d0` | `0x16` (type passed by caller) |
| `getFwVersion` | `0x004a4700` | `0x00` |
| `getSerialNo` | `0x004a5680` | `0x01` |
| `getDeviceAddress` | `0x004a5bf0` | `0x03` |
| `getNoOfSubDevicesConnected` | `0x004a77e0` | `0x04` |

`getHIDBuffers` logic (decompiled):

```
frame = 01 | EB FE 01 00 | 04 00 | <opcode LE> | <len LE=4> | crc | 00 | <payload>
if opcode in {0x11,0x12,0x16,0x18,0x1a}:
    payload[4] = (byte) strtol(value_string, base 10)
    len = 6
crc = crc8(payload, len)          # poly 0x07, init 0xFF
```

`parseDatagram` switches on the frame opcode: `0x00`→sw version,
`0x01`→serial, `0x02`→device name, `0x03`→BD address,
`0x04`→sub-devices, `0x06`→DFU type, `0x07`→enter DFU,
`0x0C`→BT name, `0x0E`→battery, `0x10`→sidetone, `0x13`→noise reduction,
`0x14`→PID, `0x17`→latency, `0x18`→remote device info, `0x19`→link keys,
`0x1B`→auto-power-off; `default` → `"Opcode not supported"`.

`getHIDBuffers` (`0x004c7b40`, re-decompiled 2026-10-12) confirms the request
payloads come from a **fixed static table** (`DAT_00826fXX`) selected by a
`switch` on the opcode. The frame is assembled field-by-field:
`[0]=01`, `[1..4]=EB FE 01 00`, `[5..6]=04 00`, `[7..8]=opcode`,
`[9..10]=length`, `[13..]=payload`, `[11]=CRC(payload)`. Every opcode uses
exactly **4 bytes** (`0x09` uses 14; the value setters append one byte and bump
the length to 6). There is **no device-index / handle field on the wire**, so a
host plain query cannot be "missing" a parameter — `0x0e` is always
`12 00 03 00`.

Reply decoding (`DecodeDatagram` @ `0x004ce7e0`, `EncodeDatagram` @
`0x004ce570`, `GetBatPercentage` @ `0x004cea40`, `verifyOpcode` @ `0x004cbfb0`):

* `EncodeDatagram` reproduces the host frame byte-for-byte (same field order,
  `crc8(payload)` over the payload length) — a second, independent confirmation
  of §1.
* `DecodeDatagram` reads the length from `frame[9..10]` and copies the payload
  from `frame[0x0d..]` out of the static RX buffer `DAT_009072c0`.
* `parseDatagram` passes that *same full frame buffer* to the value parsers, so
  `GetBatPercentage` literally reads `frame[0x11] | frame[0x12]`, i.e.
  `payload[4] | payload[5]`. A `0x0e` reply of `12 00 03 00 <b> 00` therefore
  decodes to battery byte `<b>`. Every value parser
  (`GetSideToneGain`, `GetNoiseReductionLevel`, `GetLatencyLevel`,
  `GetNbrLinkKeys`, `GetRemoteDeviceInfo`, `DeviceAutoSleepLevel`) follows the
  same "echo header + value at `payload[4..5]`" shape.
* `verifyOpcode` compares the reply payload against the request payload and, on
  a mismatch, abandons the parse with *"Response does not match for the command
  sent to CSR device"*. A reply whose class/echo differs is not decoded.

## 5. Live evidence (2026-10-12)

```
$ python3 tools/secom-probe.py
0x00  01 00 03 00   -> 0400 op 0000 : 01 00 03 00 03 00 0e 00 02 00
0x01  01 00 0b 00   -> 0400 op 0000 : 01 00 0b 00 <32x 00>
0x02  09 00 01 00   -> 0400 op 0000 : 09 00 01 00 45 00 50 00 4f 00 53 00
                                        20 00 47 00 53 00 41 00 20 00 37 00 30 00 00…
                                        == "EPOS GSA 70"
0x03  06 00 14 00   -> 0400 op 0000 : 06 00 14 00 4e 00 f2 e2 94 00 16 00
0x04  01 00 09 00   -> 0530 op 0001 : 01 00 09 00            (ACK only)
0x0e  12 00 03 00   -> 0530 op 0003 : 12 00 03 00            (ACK only)
0x10  0a 00 0c 00   -> 0530 op 0004 : 0a 00 0c 00            (ACK only)
0x11  0a 00 0b 00 05 00 -> 0530 op 0004 : 0a 00 0b 00 05 00   (ACK only)
0x1234 (bogus)      -> 0530 op 120d : <echo>                (generic ACK)
0x4000              -> 0410 op 4000 : NAK
0x4f00              -> 0410 op 4f00 : NAK
0x4f12              -> 0530 op 4f04 : (FWU GET_FEATURES, empty)
```

The dongle answers `0x00`–`0x03` locally. `0x04`–`0x1C` are addressed to the
linked headset, so the dongle link-ACKs them. Note that even when the headset
*is* linked and the dongle forwards its device **events** (§5.2), these value
GETs still return no data — see the open question in §5.2.

### 5.1 GSP 670 headset, direct USB (`1395:008a`, `/dev/hidraw4`, 2026-10-12)

The headset exposes the **same** vendor HID interface (interface 5, report ID
`0x01`, 106-byte reports) and speaks the same protocol, so it can be probed
directly over USB. It answers its own identity locally but treats the value
opcodes the same way the dongle does (they target a *linked* device), so they
still only link-ACK:

```
$ python3 tools/secom-probe.py /dev/hidraw4
0x00 GET_FW_VERSION   req=01000300 -> DATA op=0000 : 01 00 03 00 03 00 02 00 06 00 == 3.2.6
0x01 GET_SERIAL_NO    req=01000b00 -> DATA op=0000 : 01 00 0b 00 <32x 00>
0x02 GET_DEVICE_NAME  req=09000100 -> DATA op=0000 : 09 00 01 00 47 00 53 00 50 00 20 00 36 00 37 00 30 00 …
                                                       == "GSP 670"
0x03 GET_DEVICE_ADDRESS req=06001400 -> DATA op=0000 : 06 00 14 00 38 00 07 f8 94 00 16 00
0x04 GET_SUBDEVICES_CONNECTED -> 0530 ACK only
0x06,0x0c,0x0e,0x10,0x13,0x14,0x17,0x19,0x1b -> 0530 ACK only
0x18 GET_REMOTE_DEVICE_INFO req=06003200 -> DATA op=0000 : 06 00 32 00 00 00 (value 0x0000)
0x05,0x09,0x0a,0x15,0x1c -> 0530 ACK only
```

Notes:

* The headset firmware is **3.2.6** (the dongle is 3.14.2) and its own device
  name is `"GSP 670"` (the dongle's is `"EPOS GSA 70"`).
* Headset device address `38 00 07 f8 94 00 16 00` vs dongle
  `4e 00 f2 e2 94 00 16 00` — both end in `94 00 16 00`; the rest is opaque.
* `0x18` returned value `0x0000` = "no remote device" — the headset is on USB,
  not RF-linked in this test. Note §5.2: even when the dongle *does* forward
  headset events, the value opcodes still only link-ACK, so ACK-only reads are
  not merely a pairing-state artefact.

> ⚠️ **Do not send `0x07` (ENTER_DFU) to the headset.** Probing it makes the
> headset reboot into firmware-update mode: PID `008a` → `808a`, a single
> vendor HID interface with a 1022-byte output report, its audio card
> disappears, and CAPRICORN writes start failing with `EPIPE` (the 107-byte
> frame no longer matches the DFU report size). It is recoverable: the device
> re-enumerates back to `008a` on its own after a short while, or immediately
> after a USB reset (`USBDEVFS_RESET`), but a USB reset issued while it is
> mid-transition can also leave it half-enumerated (`bNumInterfaces=0`) until a
> second reset. The default `secom-probe.py` sweep skips `0x07` and the value
> setters; pass them explicitly only when intended.

### 5.2 Unsolicited device→host events (live, 2026-10-12)

While the GSP 670's **battery-percent button** was pressed, the dongle
(`/dev/hidraw1`) emitted unsolicited input reports — a passive listener is
otherwise silent. A captured frame, verbatim:

```
01 eb fe 01 00 | 00 01 | 04 00 | 0a 00 | ca | 00 | 1d 00 f0 00 01 00 01 00 74 00
rid  sync       marker  op      len    crc  f    payload
```

* `crc8(payload) = 0xca` = byte 11 → the **same CRC-8 rule** (poly `0x07`,
  init `0xFF`, MSB-first, over the payload) applies to these frames.
* The frame layout is identical to host frames; only the **marker** differs.

Marker family (`flag` = marker byte 1): host uses `flag = 0x00`, device→host
uses `flag = 0x01`.

| Marker | Direction | Opcode field | Payload shape |
|--------|-----------|--------------|---------------|
| `04 00` | host→device, and the data *reply* echo | `0x0000` / request | request header + value |
| `10 01` | device→host data | `0x0000` | `01 00 f0 00 01 00 <s> 00` (`s` toggles 0/1) |
| `00 01` | device→host **event** | `0x0004` | `1d 00 f0 00 01 00 01 00 <v> 00` |
| `ff 01` | device→host **event** | `0x0004` | `08 00 f0 00 03 00 01 00 00 00 00 00 00 00` |
| `05 30` | link ACK | `req >> 2` | echo |
| `04 10` | NAK | `req >> 2` | — |

Observed on a **battery-percent button press**:

> **Key model (corrected 2026-10-13):** an event body is
> `<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]`; `word1` is usually
> `0x00f0` but varies (battery `0x000f`, ANC-state/tone `0x0007`, …). The
> `00 01` payload `1d 00 f0 00 01 00` is therefore word0 `0x001d`,
> word1 `0x00f0`, variant `1` — an **unhandled** id (no dispatcher case), so the
> earlier "VirtualButtonEvent" label on it was wrong. The real virtual-button
> event is `08 00 f0 00 03 00`. See `docs/analysis/session-handshake.md` §6.1.

* `00 01` frames arrive in a **burst** (one press produced ~70 frames over
  ~20 s in one capture; a later capture produced 1–3 frames per press).
* `ff 01` frames recur every ~1–2 s; `10 01` frames toggle a single bit.

A 120 s **passive** listen while the headset's charge state was toggled
produced **no reports at all** — the dongle does not push a battery event on
charge change, and is otherwise silent when no button is pressed.

A later capture with the RF link confirmed live:

* One battery-button press produced a clean **3-frame** burst: two `10 01`
  toggles (`… 01 00 <0> 00`, then `… 01 00 <1> 00`) and one `00 01` event
  (`1d 00 f0 00 01 00 01 00 04 00`).
* A second press produced a **19-frame** `00 01` burst in ~2.5 s with value
  bytes spanning `00`–`a3` — random-looking, *not* a percentage. The voice
  prompt during the same press announced **">80%" battery**, so the varying
  byte is **not** the battery level (it looks like a signal/telemetry stream).
* Sending `0x0e` immediately before the press still produced only the link ACK
  and no data frame — so the missing battery reply is not a timing artefact and
  the events do not transport the value either.
* After a **full re-link** (dongle unplugged/re-plugged + headset power-cycled),
  a repeat probe while the link was confirmed live (the `10 01` toggle and
  `00 01` burst appeared during the `0x0e` window) still gave `0x04` → ACK,
  `0x0e` → ACK only, `0x18=5` → ACK. A fresh RF link does **not** unlock the
  value GETs.

Decode (static, `events-dump.txt`):

* `CCapricornDatagram::parseVirtualButtonEvent` (`0x004cf360`) reads the event
  value from **buffer offset `0x13`** (= payload byte 6).
* `handleDeviceChange` (`0x004cde50`) / `handleConfigChange` (`0x004cf5f0`)
  forward an event code (`0x34`) to a listener callback.
* `verifyOpcode` (`0x004cbfb0`) merely checks the reply echoes the request.

**Consequence (open question):** device events reach the host, yet `0x04`
still reports `0000` sub-devices and the value GETs (`0x0e`, `0x10`, `0x13`,
`0x17`, `0x1b`) still only link-ACK. So *"0 sub-devices" is not a reliable link
indicator*, and battery / sidetone / noise-reduction / latency are **not**
read back through those GETs (at least not from a plain host query without
whatever session/handshake the EPOS service performs).

Re-confirmed with correct attribution while the link was live (drain-before-
write + 2.5 s timeout via `GSA70Device.secom_exchange`):

```
SUBDEVICES 0x04 req=01000900 -> DATA 01000900 0000
BATTERY    0x0e req=12000300 -> ACK
SIDETONE   0x10 req=0a000c00 -> ACK
NOISE_RED  0x13 req=0a001200 -> ACK
LATENCY    0x17 req=0a001700 -> ACK
AUTOPOWER  0x1b req=01002000 -> ACK
```

A targeted test ruled out a merely *slow* reply: sending `0x0e` and then
listening passively for **15 s** produced only the link ACK
(`05 30` op `0x0003`, payload `12 00 03 00`) and nothing else. Combined with
`getHIDBuffers` (§4) showing the request is byte-identical to the official
service's, the dongle genuinely does not answer `0x0e` in this state.

**GAP-RE-1b hardware verdict (2026-10-13, controlled ± confirmed link):**
the earlier silent listens above were all ambiguous because the RF link was
not independently confirmed. This test closed that gap:

* A 180 s **unbuffered** raw monitor while the headset was power-cycled
  showed the push channel is healthy and the headset **is** RF-linked:
  `SubDevicesChanged` (`01 00 f0 00 01 00`, count 0↔1) fired on every link
  drop/formation, plus corroborating `1d 00 f0 00 01 00 01 00 07 00` frames
  (§2.7's unhandled id) on button presses — all unprompted.
* In the same linked window and a further 150 s window in which the user
  **plugged/unplugged the charger 3–4×** with the headset on and linked, the
  dongle pushed **zero** `Battery_Events_Percentage` /
  `ChargingChanged` frames (`12 00 0f 00 04 00` / `12 00 0f 00 03 00`).
* The `0x0e` poll fallback (30 s interval) also returned **no value** every
  time — the GET path does not serve battery either.

**Conclusion:** the §6.1 battery keys exist in the receive-side dispatcher
table but were **never observed to fire on hardware**. **Static closure
(same day, Ghidra headless — §6.2 of `docs/analysis/session-handshake.md`):** the
re-opened `set_battery_events` `[+0x74]` slot is a **read-only getter**, and
an exhaustive caller check of the two Rtx wire builders
(`split_request_into_packets` `0x67a070`, `send_request_without_response`
`0x679ee0`) shows no event-enable code among their callers — so battery pushes
are **not gated by a host enable command**. GSA 70 firmware 3.14.2 simply does
not emit battery telemetry on the passive channel, and no GET serves the value.
Link/button events are unaffected. See `docs/analysis/session-handshake.md`
Rev 3 / §6.2 / §6.4.

## 6. Using it from Python

```python
import sys; sys.path.insert(0, 'src')
from gsp670.device import GSA70Device

with GSA70Device() as d:
    print(d.get_device_name())        # 'EPOS GSA 70'
    print(d.get_firmware_version())   # '3.14.2'
    print(d.get_device_address().hex())
    print(d.get_subdevices_connected())  # None until the headset is linked
    d.set_sidetone(5)                 # opcode 0x11
```

Low level:

```python
from gsp670.protocol import SecomOpcode, secom_request, frame
frame(SecomOpcode.SET_SIDETONE, secom_request(SecomOpcode.SET_SIDETONE, 5))
```

## 7. Open questions

* Opcodes `0x05`, `0x09`, `0x0A`, `0x15`, `0x1C` have no recovered name.
  **`0x09` is the only request with a long payload** (`06 00 09 00` + ten
  `00` bytes, length 14) and is the prime candidate for a
  **registration / link-key / paired-device-add** command (cf. `0x19`
  number-of-link-keys). The ten trailing bytes are undecoded; a real pairing
  experiment would be needed to confirm.
* The device-address blob (`4e 00 f2 e2 94 00 16 00`) is opaque.
* The value range/meaning of sidetone / noise-reduction / latency values
  needs a linked headset to confirm (the byte is 1-wide on the wire).
* `0x18` (`GetRemoteDeviceInfo`) also takes a value byte — confirm the
  selector meaning with a linked headset.
* **Why do the value GETs (`0x0e`, `0x10`, `0x13`, `0x17`, `0x1b`) only
  link-ACK even while device events (§5.2) are arriving?** **Resolved:** the
  values are **push-only events**; the legacy Capricorn GETs are a superseded
  path the dongle transport-ACKs but does not serve. There is no missing request
  parameter (the host frame is byte-identical to the service's). See
  `docs/analysis/session-handshake.md` §1/§3.
* The `0x14`/`0x15` link ACKs carry reply-class `0x0008` (not `req >> 2` = 5),
  unlike every other ACK observed — cause unknown.
* **RESOLVED (Phase 3, Ghidra; corrected 2026-10-13) — the event key.**
  Every device→host notification body begins
  `<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]`. The dispatcher
  `FUN_00643b10` matches a 6-byte key via `FUN_00642d30` (3× u16) or a 4-byte
  key via `FUN_00642cf0` (2× u16). **`word1` is not a fixed `0x00f0`** — it
  varies per source component: battery `12 00 0f 00 {03,04} 00`, ANC-state
  `17 00 07 00`, tone `07 00 07 00`, speaker-mic optimised `10 00 1d 00`,
  device PDL `06 00 29 00`; the rest use `0x00f0` (e.g. sound
  `0a 00 f0 00 02/03/04 00`, input `08 00 f0 00 03/07 00`, ANC
  `17 00 f0 00 01/02 00`, component `23 00 f0 00 01 00`, connection/service
  `06 00 f0 00 …` / `01 00 f0 00 …`). Full 22-key table with value schemas:
  `docs/analysis/session-handshake.md` §6.1. So `1d 00 f0 00 …` reads as word0
  `0x001d`, word1 `0x00f0`, variant `1` — an **unhandled** id (no dispatcher
  case), not VirtualButton.
* **Payload structure (corrected):** the key is `<w0> <w1> [<variant>]`; after
  it, `seek(keylen)` then the value fields (u8 / u16 LE / multi-u8). It is *not*
  a fixed `<id> <0x00f0> <variant>` shape. Host→device request bodies are a
  separate matter: e.g. `0x0e` → `12 00 03 00`, `0x15` → `08 00 f0 00` (an
  un-named request body, *not* `Service_GetSubDevicesConnected`; the real
  sub-devices-changed event is `01 00 f0 00 01 00`).
* Outgoing `Service_*` **setters** carry no literal id: they are selected by
  virtual dispatch on `ModiBaseStationDevice` (`[obj+0x100]` → secomparser →
  per-command vtable slot, e.g. `[+0x74]` = `set_battery_events`, arg
  `[obj+0x338]` = 16-bit slave id). These are **host-side bookkeeping only**
  (flag flip + log) — no RTX packet is built (corrected 2026-10-13, GAP-RE-1
  resolved). See `docs/analysis/session-handshake.md` §6.2.
* **Firmware update is a separate Rtx channel**, not SECOM: `RtxDatagramIo`
  emits 64-byte `0x58`-prefixed, `0xEE`-padded reports; FWU ids are
  `0x4f00`(→`0x4f01`), `0x4f03`(→`0x4f04`), `0x4f06`, `0x4f08`, `0x4f0a`,
  `0x4f0e`, `0x4f10`, `0xf066`. See `docs/analysis/session-handshake.md` §6.3.
