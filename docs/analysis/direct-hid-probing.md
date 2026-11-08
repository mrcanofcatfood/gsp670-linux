# Direct USB HID Probing Results

This document captures what we learned from directly probing the dongle
on the Linux host via `/dev/hidraw*` and `libusb`.

> **Superseded in part (2026-10-12).** The normal-mode control protocol was
> subsequently identified and verified as the **Capricorn/SECOM command set**
> (opcodes `0x00`–`0x1C`); see
> [`../verified-secom-opcodes.md`](../verified-secom-opcodes.md).
> The earlier "feature index" interpretation and the FWU-only view in this
> document are **incorrect**. In particular, an ACK (`05 30`) is a pure
> transport acknowledgement and does not indicate the command was understood
> or executed.
>
> **Further correction (2026-10-13):** the `eb fe 01 00` in the captures below
> is the 4-byte **sync**, not opcode `0xEB`. The frames are ordinary
> device→host event-key payloads: `ff 01 … 08 00 f0 00 03 00` =
> `Input_Events_VirtualButtonEvent`, and `10 01 … 01 00 f0 00 01 00 00 00` =
> `Service_Events_SubDevicesChanged`. See `session-handshake.md` §6.1.

## Environment

- Host: Arch Linux 6.16.x
- Dongle: EPOS GSA 70 (VID 0x1395, PID 0x0300)
- Detached from VM via `virsh detach-device` + deauthorize/reauthorize cycle

## USB Descriptors

### Interfaces

| # | Class | Driver | Purpose |
|---|-------|--------|---------|
| 0 | Audio | snd-usb-audio | Main Audio control |
| 1 | Audio | snd-usb-audio | Headset streaming |
| 2 | Audio | snd-usb-audio | Headset streaming alt |
| 3 | Audio | snd-usb-audio | Microphone streaming |
| 4 | Audio | snd-usb-audio | Microphone streaming alt |
| 5 | **HID** | **usbhid** | **Capricon protocol** |

### HID Interface (Interface 5)

- bInterfaceClass: 3 (HID)
- bInterfaceSubClass: 0
- bInterfaceProtocol: 0
- bcdHID: 1.11
- **Endpoints: EP 1 IN only (Interrupt, 64 bytes max)**

### HID Report Descriptor (decoded)

```
USAGE_PAGE(Vendor: 0xFFFF)
USAGE(0x01)
COLLECTION(Application)
  REPORT_ID(0x6A)         ← VENDOR COLLECTION (106 = 0x6A)
  REPORT_SIZE(8 bits)
  REPORT_COUNT(1)
  INPUT(Variable, Absolute)    ← 1 byte input
  OUTPUT(Variable, Absolute)   ← 1 byte output
END_COLLECTION

USAGE_PAGE(Consumer: 0x0C)
USAGE(0x01)
COLLECTION(Application)
  REPORT_ID(0x08)
  REPORT_COUNT(4)
  REPORT_SIZE(1 bit)
  INPUT(Variable, Relative)    ← Media buttons (play/pause/etc)

  REPORT_ID(0x02)
  REPORT_COUNT(5)
  INPUT(Variable, Absolute)    ← Volume wheel (5 fields of 2 bits each)
  
  REPORT_ID(0x06)
  INPUT(Constant)               ← Mute button (1 bit constant)
END_COLLECTION
```

### Critical Findings

1. **Report ID = 0x6A** is for vendor (Capricon) communication
2. **HID interface has NO OUT endpoint** — host-to-device must use SET_REPORT
3. Per the HID descriptor, vendor Output/Input reports are 1 byte payload
4. **However, observed actual notifications are 106 bytes long** — meaning
   the HID descriptor is misleading and the chip accepts/produces longer reports

## Notification Format (Observed)

Once during a 30s listen window, the dongle sent:

```
01 EB FE 01 00 10 01 00 00 08 00 E1 00 01 00 F0 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Breakdown:
- `01`: Report ID = 1 (response/confirmation type?)
- `EB`: Opcode = 0xEB (notification type — same as ModiUpdater.dll's API_FWU_DEVICE_NOTIFY_IND)
- `FE`: Sub-type / module selector
- `01 00 10 01 00 00`: Sequence/data header
- `08 00 E1 00 01 00 F0 00 01 00 00 00 00 00 00 00 00 00 00 00 00`: Payload (mostly zeros)

This is likely a `FWU_STATUS_IND` or similar periodic status notification.
The dongle does NOT send these continuously — only on events.

## SET_REPORT via Control Transfer

Verified that `hidapi.write()` correctly issues SET_REPORT control transfers:

```
SETUP packet: bmRequestType=0x21, bRequest=0x09
wValue = (0x02 << 8) | 0x6A  ← OUTPUT report, Report ID 0x6A
wIndex = 5                       ← Interface 5
wLength = N+1                    ← Including Report ID byte
Data = [0x6A, opcode, payload...]
```

This was confirmed via `usbmon` capture:
```
USB CONTROL SUBMIT to 3:68:0
  0x0000: 6aeb fe01 0400     j.....     ← Our sent data visible
```

The dongle's USB device is `3:68` on the host (was `3:68` in original enumeration,
device address changed after detach/re-attach).

## Test Commands Sent (No Responses)

All commands accepted by the dongle (no USB errors), but the dongle did not respond:

| Bytes Sent | Expected Response | Actual |
|------------|-------------------|--------|
| `6A 00` | None (probe) | Silent |
| `6A 01` | Firmware version | Silent |
| `6A EB` | Notification | Silent |
| `6A EB FE 01 04 00` | Status | Silent |
| `6A EB FE 01 10 01` | Status (echo of observed) | Silent |
| `6A FF` | Test | Silent |
| `6A EB FE 01 04 00 ...` | Long command | Silent |

## Conclusion

The dongle's HID interface is **operational** — it accepts SET_REPORT commands
and can send notifications (we observed one). However, it does NOT respond to
arbitrary commands. The dongle is in a low-power idle state and only emits
notifications on **status changes** (button press, pairing event, etc.).

## Next Steps To Try

1. **Trigger a dongle event**: Pair/unpair the headset, press the volume wheel,
   or trigger the link key. This should cause the dongle to start sending
   notifications.

2. **Capture traffic from EPOS Gaming Suite**: Need to capture the actual
   SET_REPORT commands sent by EPOS when starting the firmware update. This
   is the only way to know the exact `API_FWU_ENABLE_REQ` opcode format.

3. **Look at the notification opcode mapping**: The 0xEB notification opcode
   might actually be the response to a specific command we haven't sent yet.
   Look for the format the dongle expects in its initial handshake.

4. **Try specific Capricon module IDs**: The notification has `EB FE 01`.
   The `FE` might be a module ID. Try sending commands with various module
   IDs (0x01, 0x02, 0x03, ...) to find which one the dongle responds to.

5. **Read firmware version with proper opcode**: Once we know which module ID
   is correct, the GET_FW_VERSION_REQ might just return the firmware version.

## Files

- `tools/hid-listener.py` — passive listener that captures notifications
- `tools/probe-capricon-pyusb.py` — pyusb-based sender for SET_REPORT

## Tool Requirements

- Python 3
- `hidapi` Python module (`pip3 install hidapi` or `pacman -S python-hidapi`)
- `pyusb` Python module (`pacman -S python-pyusb`)
- Root access (for /dev/hidraw*)
---

## Update: Volume Button Trigger Captures Notifications

We **DID** capture FWU_STATUS_IND notifications from the dongle after
triggering a volume button event:

### Notification Format Observed

After writing `02 01` (Report ID 0x02 = Consumer Page Volume, value 0x01 = Volume Up)
to the dongle's HID interface, the dongle started sending:

```
01 eb fe 01 00 ff 01 04 00 0e 00 80 00 08 00 f0 00 03 00 00 00 00 00 00 00 00 00 00 00 00 00
```

This is **Report ID 0x01** (a response/confirmation Report ID), with
**opcode 0xEB** (FWU_DEVICE_NOTIFY_IND) and **sub-opcode 0xFE**.

### Earlier Captured Notification (from initial enumeration)

```
01 eb fe 01 00 10 01 00 00 08 00 e1 00 01 00 f0 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00
```

The byte at offset 4 changed between captures:
- Initial: `0x10` (could be a sequence/counter)
- After volume up: `0xff` (status byte?)

### Observations About the Protocol

1. **The dongle accepts SET_REPORT commands silently** (no error response)
2. **Volume Up writes (Report ID 0x02) trigger status notifications**
3. **Notifications are only sent during active states** — after about
   20 seconds of inactivity, the dongle goes silent again
4. **The dongle uses Report ID 0x01 for notifications**, not 0x6A
   (the 0x6A is for vendor commands going host → device)

### Critical Conclusion **superseded** (2026-10-11)

The old "deep idle / no response / register-write unlock" hypothesis below
was **disproven**. `CxAudioHidDll32.dll::CxAudioHidOpenConnection`
(0x1000a600) is pure USB/HID enumeration (vendor/usage-page filtering) —
**no register writes**, and the register-bus datagrams in that DLL are a
*separate* protocol with **no FWU link**. And once the correct Capricorn
frame shape was applied, the dongle answered *every* well-formed request
(NAK/ACK per opcode, see authoritative section below). The actual
surviving unknowns are the FWU *precondition state* and the *payload* of
`0x4F00` — not the framing or an "open connection" ritual.

**(Historical notes preserved below only for audit.)**

The reason a bare `0x4F00`/`00 00` send was initially unanswered/NACKed is
**not** a missing open sequence: the dongle *did* NAK it (reply `04 10`,
opcode 0x4F00). It rejects FWU_ENABLE because it is not in a FWU session
state — the host-side state machine sends a `0x4F10 SET_FEATURES_REQ`
before `0x4F00` in one branch (see authoritative section), and the
`01 03` special-flag payload exists as an alternative.

---

## Update 2026-10-11: Wire Format, Reply Classes and FWU Family (Authoritative)

The sections above are **historical / superseded**. Once the frame format below
was applied, the dongle answered *every* well-formed request. The earlier
"no response", "Report ID 0x6A", and "deep idle state" conclusions were an
artifact of probing with the wrong frame shape (report size 1 instead of 107).

### Wire layout (report coords, `/dev/hidraw`, 107-byte reports)

| offset | len | meaning |
|--------|-----|---------|
| 0      | 1   | report id = `0x01` |
| 1..4   | 4   | sync = `EB FE 01 00` |
| 5..6   | 2   | marker, host = `04 00` |
| 7..8   | 2   | opcode, little-endian |
| 9..10  | 2   | payload size, LE |
| 11     | 1   | CRC-8 (poly 0x07, init 0xFF) over payload |
| 12     | 1   | filler = `0x00` |
| 13..   | n   | payload |

Data coords (no report id) = report coords − 1 compt positions; builders in
`tools/gsp_hid.py` are the source of truth.

### Reply classes (supersedes any earlier "universal NAK" claim)

- **NAK**: marker `04 10`, size 0, crc `FF`. Returned for empty-payload
  requests and for FWU opcodes the dongle rejects (not in FWU/upgrade mode).
- **ACK**: marker `05 30`, size N, crc = crc8(payload), payload = **exact
  echo** of the request payload (sensitivity tests: `01 00`→`C2`, `00 00`→`D7`,
  `02 00`→`FD`, `00 01`→`D0`, `01 03`→`CB`, `03 01`→`EF`; the CRC always
  tracks the echoed payload).
- **Marker transform** (request → reply): byte0 + 1, byte1 + 0x30
  (`04 00`→`05 30`, `03 04`→`04 34`, `10 01`→`11 31`).
- **Opcode transform**: `reply_opcode = (req & 0xFF00) | ((req & 0xFF) >> 2)`
  (e.g. `0x4008`→`0x4002`, `0x4010`→`0x4004`; for `req 0x4F00` → `0x4F00`).

### FWU (0x4F) opcode table — decoded from ModiUpdater.dll

Full table with firmware API names (`API_FWU_*`) and direction per opcode is
in the session-2 section below. Summary: 0x4F00 ENABLE_REQ, 0x4F01 ENABLE_CFM,
0x4F02 DEVICE_NOTIFY_IND, 0x4F03 UPDATE_REQ, 0x4F04 UPDATE_CFM,
0x4F05 UPDATE_IND, 0x4F06 UPDATE_RES, 0x4F07 GET_BLOCK_IND, 0x4F08
GET_BLOCK_RES, 0x4F09 GET_CRC_IND, 0x4F0A GET_CRC_RES, 0x4F0B COMPLETE_IND,
0x4F0C STATUS_IND, 0x4F0D MULTI_CRC_IND, 0x4F0E MULTI_CRC_RES, 0x4F10
SET_FEATURES_REQ, 0x4F11 SET_FEATURES_CFM, 0x4F12 GET_FEATURES_REQ, 0x4F13
GET_FEATURES_CFM, 0x4F14 CRC32_IND, 0x4F15 CRC32_RES (0x4F0F undefined).

**FWU_ENABLE_REQ = 0x4F00**, payload 2 bytes: `00 00` (standard path, both
branches of `fcn.10007b90`) or `01 03` (special-flag path when state bits
0x2|0x4 are set). Builder writes opcode word `0x4F00` (LE `00 4F`) at
payload[0..1].

### FWU family sweep (2026-10-11, payload `00 00`, marker `04 00`)

Probed 0x4F01..0x4F15 (0x4F00 itself gated — it is the DFU trigger).
Dongle PID stayed 0x0300 throughout. Results:

- **NAK group 0x4F01..0x4F07** — rejected (`04 10`, size 0, crc FF); reply
  opcode = `req & 0xFFFC`.
- **ACK group 0x4F08..0x4F15** — echo ACK (`05 30`) with the shift transform:
  0x4F08..0x4F0B→0x4F02, 0x4F0C..0x4F0F→0x4F03, 0x4F10..0x4F13→0x4F04;
  exception 0x4F14/0x4F15→0x4F08 (transform predicts 0x4F05).

**Conclusion:** the dongle parses our header-opcode framing and applies
FWU-specific logic per opcode — the wire encoder hypothesis
(`frame(0x4F00, payload)`) is empirically confirmed. The gated single-shot
`0x4F00` send is the remaining step to test the PID switch to 0x8089.

---

## Update 2026-10-11 (session 2): Full FWU opcode table + host sequence resolved

### 1. Framing ownership resolved: FWU_ENABLE goes out Capricorn-framed from the EXE path

- `EB FE 01 00` magic exists **only** in `EPOSGamingSuiteService.exe`
  (3 occurrences). It is **absent** from `ModiUpdater.dll`,
  `HidDfu.dll`, and `CxAudioHidDll32.dll`.
- The `03 04` byte sequences found in ModiUpdater.dll / HidDfu.dll are
  **ASN.1 X.509 OIDs** (`0d 06 09 60 86 48 01 65 03 04 ...`) — certificate
  data, **not** a frame header.
- EXE-side protocol stack: `epos::dci::RtxProtocol<epos::dci::protocol::Modi_>`
  (vtable `0x805334`) derives from **`NxpDatagramIO`** (slot 0 = `0x00617a70`).
  That base class is the source of the NXP datagram framing that matches the
  empirically confirmed Capricorn wire format. FWU requests built in the DCI
  layer therefore go out as Capricorn `EB FE 01 00` datagrams.
- ModiUpdater.dll and HidDfu.dll run their own non-Capricorn HID I/O for the
  *post-switch* DFU transfer stage; the `0x4F00` DFU-mode trigger itself is
  Capricorn (EXE path).

### 2. Full FWU opcode table (source: ModiUpdater.dll .rdata, file 0x1a0c0)

Sorted `{u16 opc, u16 0, u32 nameVA}` entries:

| opcode | name | direction |
|--------|------|-----------|
| 0x4F00 | API_FWU_ENABLE_REQ  | host→device (DFU trigger) |
| 0x4F01 | API_FWU_ENABLE_CFM  | device→host |
| 0x4F02 | API_FWU_DEVICE_NOTIFY_IND | device→host |
| 0x4F03 | API_FWU_UPDATE_REQ  | host→device |
| 0x4F04 | API_FWU_UPDATE_CFM  | device→host |
| 0x4F05 | API_FWU_UPDATE_IND  | device→host |
| 0x4F06 | API_FWU_UPDATE_RES  | device→host |
| 0x4F07 | API_FWU_GET_BLOCK_IND | device→host |
| 0x4F08 | API_FWU_GET_BLOCK_RES | device→host |
| 0x4F09 | API_FWU_GET_CRC_IND  | device→host |
| 0x4F0A | API_FWU_GET_CRC_RES  | device→host |
| 0x4F0B | API_FWU_COMPLETE_IND | device→host |
| 0x4F0C | API_FWU_STATUS_IND   | device→host |
| 0x4F0D | API_FWU_MULTI_CRC_IND| device→host |
| 0x4F0E | API_FWU_MULTI_CRC_RES| device→host |
| *(0x4F0F not defined — gap)* | | |
| 0x4F10 | API_FWU_SET_FEATURES_REQ | host→device |
| 0x4F11 | API_FWU_SET_FEATURES_CFM | device→host |
| 0x4F12 | API_FWU_GET_FEATURES_REQ | host→device |
| 0x4F13 | API_FWU_GET_FEATURES_CFM | device→host |
| 0x4F14 | API_FWU_CRC32_IND    | device→host |
| 0x4F15 | API_FWU_CRC32_RES    | device→host |

Notes:
- The 0x4F0F gap explains the empirically observed "groups of four" in the
  ACK sweep (0x4F08..0x0B, 0x4F0C..0x0F, 0x4F10..0x13, 0x4F14..0x15).
- Only three opcodes are host→device *requests*: 0x4F00, 0x4F10, 0x4F12.
  Everything else NAK'd in our sweep is device→host traffic — consistent
  with them being rejected as send-class.

### 3. Host-side FWU state machine (ModiUpdater.dll `fcn.10007b90`)

- **Branch bit0-of-[obj+0x68] SET:**
  1. `fcn.100010e6(2,1)` → builds message `10 4f 01` =
     **`0x4F10 API_FWU_SET_FEATURES_REQ` with payload byte `0x01`** (via
     `fcn.10004730`: data len 3, opcode word, feature byte).
  2. `fcn.100012e4(2,0,0)` → builds `00 4f 00 00` =
     **`0x4F00 ENABLE_REQ` payload `00 00`**.
  3. 4000 ms retry timer (`fcn.100013b1`).
- **Branch bit0 clear:** `0x4F00` payload `00 00` directly (+cleanup).
- **Special-flag path** (`fcn.10005dd0` @ `0x100065e8`, state bits 1 AND 2
  set): `fcn.100012e4(2,1,3)` → **`0x4F00` payload `01 03`**, clears bit1,
  4000 ms timer.

⇒ **The canonical "start update session" sequence is
`0x4F10/01` then `0x4F00/00 00`**, with `/01 03` as an alternative ENABLE.

### 4. EXE-side DCI request classes (epos::dci)

- `FwuSetFeaturesRequest` ctor `fcn.0067c0d0`: data = `10 4f <feature byte>`
  (3 bytes); expects CFM opcode `0x4F11`, 1 payload byte. Built by
  `RtxProtocol<Modi_>` virt slot 37 (`fcn.0067e140`).
- `FwuEnableRequest` ctor `fcn.0067bf90`: data = `00 4f <b0> <b1>`
  (4 bytes, two payload bytes from caller args); expects CFM opcode `0x4F01`,
  1 payload byte. Built by `RtxProtocol<Modi_>` virt slot 36 (`fcn.0067d400`).
- Both dispatched via `fcn.00679ee0` (request sender). Update driver:
  `ModiFirmwareUpdater.virtual_36` → `fcn.0068bb60` ("MODIFWU: starting
  GfFwu.update") → state machine `fcn.0061b770`.

### 5. Pending live test (gated on explicit user approval + dongle replug)

Dongle was unplugged at session end; test runs only when 0x0300 is present.

Candidate sequence (Capricorn frames, computed by `tools/gsp_hid.py`):

| step | frame (after `01 EB FE 01 00 04 00`) | crc |
|------|--------------------------------------|-----|
| 1. SET_FEATURES_REQ `10 4f` size1 payload `01` | `10 4f 01 00 f4 00 01` | F4 |
| 2. ENABLE_REQ `00 4f` size2 payload `00 00`    | `00 4f 02 00 d7 00 00 00` | D7 |
| 2b. ENABLE_REQ variant payload `01 03`         | `00 4f 02 00 cb 00 01 03` | CB |

Expected on step 1: ACK `05 30` echo; then watch `0x0300`-disappearance →
`0x8089` after step 2. Failure mode: NAK `04 10` like the bare 0x4F00.

---

### Live probe results (session 3)

- **GET_FEATURES 0x4F12** (empty payload): ACK (marker 0530, opcode 0x4F04, size=0, crc=FF, empty payload) — accepted but returns no feature data. Try
  with 1-byte payloads (0x00, 0x01, 0x02) — all ACK with empty payload.
- **SET_FEATURES 0x4F10/01 → ENABLE 0x4F00/01 03** (special-flag):
  SET_FEATURES ACK (0x4F04, size=0, empty) → ENABLE NAK (marker 0410, opcode
  0x4F00, size=0, crc=FF). PID stayed 0x0300. Same result as the 00 00 payload.
- **Conclusion**: the dongle accepts SET_FEATURES and GET_FEATURES (both return ACK
  with empty payload) but rejects ENABLE regardless of payload (NAK 0410). The
  "special-flag" 01 03 variant does not change the outcome. The device is not
  in the mode/state required to honor ENABLE.


## Update 2026-10-11 (session 3): framing proven, PID corrected, mode gate found

#

### Live probe results (session 3)

| Probe | Result |
|-------|--------|
| `GET_FEATURES 0x4F12` (empty + 0x00 + 0x01 + 0x02 + 0x00010203) | ACK — **device echoes request payload verbatim**. No real feature data returned. |
| `SET_FEATURES 0x4F10/01` → `ENABLE 0x4F00/01 03` | SET_FEATURES ACK → ENABLE **NAK** (marker=0410, opcode=0x4F00). PID stayed 0x0300. Same as the earlier `00 00` attempt. |
| `HIDIOCSFEATURE` ioctl (64/106/1 bytes, with/without report ID prefix) | All return EINVAL — device has no dedicated feature report endpoint; host→device uses control SET_REPORT, which is already exercised via `dev.write()` |

**Conclusion**: The device accepts SET_FEATURES and GET_FEATURES (ACK with echoed payload) but **consistently rejects ENABLE** regardless of payload. GET_FEATURES provides no real capability data — it just echoes back the request. The HIDIOCSFEATURE path is not available. This is fully consistent with the firmware-level gate identified in static analysis: the dongle's firmware 3.3.43 does not honor FWU_ENABLE in its current mode/state, and the suite's orchestrated sequence (recovery→service→update with USB re-enumeration) cannot be reproduced by a single raw HID write.
## Wire format — now proven, not inferred

1. **Live HID report descriptor** (`hidraw3`, 1395:0300) decoded:

   ```
   06 FF FF   Usage Page (Vendor 0xFFFF)
   09 01      Usage (0x01)
   A1 01      Collection (Application)
   85 01      Report ID (0x01)
   09 01       15 00 26 FF 00  75 08  95 6A  81 02   INPUT   <- 106 bytes
   09 02       15 00 26 FF 00  75 08  95 6A  91 02   OUTPUT  <- 106 bytes
   C0
   05 0C ...  Report IDs 0x04/0x05 = Consumer Control (media/LED)
   ```

   ⇒ vendor channel = **Report ID `0x01`, 106-byte data**, exactly as
   `tools/gsp_hid.py` builds it. The historical "Report ID = `0x6A`" claim was
   a **misread of the Report-Count byte `95 6A` (106)**.

2. **`CCapricornDatagram::EncodeDatagram`** (`fcn.004ce570`) emits, byte for
   byte, the same layout:
   `[0]=01 ; [1..4]=EB FE 01 00 ; [5..6]=04 00 ; [7..8]=opcode LE ;
   [9..10]=size LE ; [13..]=payload ; [11]=CRC-8(payload)`.
   `CCapricornDatagram::getHIDBuffers` (`fcn.004c7b40`) builds the same shape
   and has an `"Opcode not supported"` reject path. ⇒ the frame is correct by
   construction; any rejection is semantic.

### Two transports (only one is the dongle)

- **Capricorn/HID** `EB FE 01 00 / 04 00` → the dongle (ours, `EncodeDatagram`).
- **SLIP-style** `01 │ escape{01,04,10→10 xx} │ crc16 LE │ 04`, built by
  `fcn.00676290` (from `ModiDatagramIO::send_command`). Device→host
  notifications are un-stuffed, so this is the radio/headset link, not the
  dongle HID channel. Not the missing piece.

### Upgrade PID correction (DeviceInfoConfig.txt)

- `EPOS_GSA_70` = **0x0300** → upgrade mode **`EPOS_device_upgrade_mode` = 0x8300**.
- 0x8089 (`Sennheiser_device_upgrade_mode`) is the Sennheiser-brand variant;
  0x808A = Sennheiser USB; 0x8303 = H3PRO dongle.
- `tools/gsp_hid.py`: `UPGRADE_PIDS = (0x8300, 0x8303, 0x8089, 0x808A)`,
  `DFU_PID = 0x8300`. `fwu-enable-sequence.py` now reports *any* new 1395 PID
  (`watch_pids(baseline, ...)` / `pids_changed(baseline)`), not just 0x8089.

### Mode state machine + firmware-version gate (EXE side)

- Modes: **normal / recovery / service / safe / update**. Recovery is a
  separate VID/PID re-enumeration; cleanup strings mention restoring recovery /
  safe / normal and "restart nested enumeration".
- `ModiFirmwareUpdater::prepare_update_mode` (`fcn.0068b300`) → "rebooting into
  FWU mode (EnterDfu)"; `fcn.0068b650` branches on mode 3 (service) / 5
  (update), otherwise attempts EnterDfu.
- EnterDfu is a **Capricorn** transaction (`CSecomParserAdapter::EnterDfu`
  `fcn.004b2720` + `CCapricornDatagram::parseEnterDfu` `fcn.004cb010`).
- **Gate**: `fcn.0068b650` does `fcn.00637fc0(device_info, 0x8f1c70)` =
  `FirmwareVersion::compare(...) < 0`. If true → logs "MODIFWU: device firmware
  {} does not support enter DFU mode, proceeding" (`fcn.006874f0`) and skips
  EnterDfu. `0x8f1c70` is a `FirmwareVersion(1,5,20)` built by the static
  initialiser at `0x479b8b`.

⇒ The bare `0x4F00` NAK is explained: DFU entry is mode- and (possibly)
version-gated; the suite establishes the mode first via re-enumeration, which a
single HID write cannot reproduce.

### Ranked next live probes — status as of 2026-10-12

1. ~~`0x4F10/01` → `0x4F00/01 03`~~ — **TESTED, CLOSED.** SET_FEATURES ACKed,
   ENABLE **NAKed** (`04 10`, opcode `0x4F00`), PID stayed `0x0300` (session 3).
2. `0x4F12 GET_FEATURES_REQ` — **TESTED, CLOSED.** ACK with echoed payload only;
   no real capability data (session 3).
3. `0x4F00` payload variants `01 00` / `02 00` / `00 01` — **untried.**
4. ~~Feature-report write path (`HIDIOCSFEATURE`)~~ — **TESTED, CLOSED.**
   Returns `EINVAL`; host→device is control `SET_REPORT` only (session 3).

**Verdict:** DFU entry cannot be reached by a single raw HID write. The dongle's
firmware (`3.3.43`) is mode-gated: the EPOS service must first perform a
re-enumeration "mode dance" (recovery → service → update), which this channel
cannot reproduce. See `docs/current-status.md`.
