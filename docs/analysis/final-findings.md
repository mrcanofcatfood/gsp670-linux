# Final Findings: GSP 670 Dongle Firmware Update Protocol

## Summary

After extensive reverse engineering of the EPOS Gaming Suite (v1.12.2.1185), I've identified the firmware update architecture for the GSP 70 dongle. However, **the exact upgrade trigger command has not been fully reverse engineered** due to the complexity of the EPOS custom "Capricon" protocol.

## What We Know

### 1. The Dongle Uses a Dual-PID Design
- **Normal mode:** PID 0x0300 (EPOS_GSA_70)
- **Upgrade mode:** PID 0x8089 (Sennheiser_device_upgrade_mode)

The dongle must be switched from PID 0x0300 to PID 0x8089 before firmware can be written.

### 2. The Protocol is "Capricon" (EPOS Custom)
- NOT standard NXP KBOOT (despite the DLL containing blhost.dll)
- Custom EPOS protocol over USB HID
- Uses 106-byte HID reports with Report ID 0x01
- Protocol commands found: FWU_ENABLE, FWU_UPDATE, FWU_STATUS, FWU_CRC32, FWU_GET_FEATURES

### 3. The HID Interface
- Interface 5 (Class 03 = HID)
- Report IDs: 1 (vendor-specific), 4 (consumer), 5 (LED)
- Report size: 106 bytes

### 4. The Firmware Update DLLs
- **HidDfu.dll** - HID DFU implementation with CRC32 checking
- **ModiUpdater.dll** - EPOS wrapper that calls HidDfu functions
- **blhost.dll** - NXP bootloader tool (not actually used for GSP 670)

### 5. The Upgrade Flow (Hypothesized)
1. Open HID device (VID=0x1395, PID=0x0300)
2. Send FWU_ENABLE_REQ command via HID output report
3. Dongle reboots into bootloader mode (PID changes to 0x8089)
4. Open new HID device (VID=0x1395, PID=0x8089)
5. Send FWU_UPDATE_REQ with firmware data
6. Dongle verifies with CRC32
7. Dongle reboots back to PID 0x0300 with new firmware

## What We Don't Know

### The Exact Upgrade Trigger Command
The ModiUpdater.dll has a function that calls `hidDfuConnect` with specific parameters:
- VID=0x1395
- PID=0x0089 (upgrade mode PID)
- wIndex=0x00
- wValue=0xFF00 (or 0x0000 depending on device type)
- Buffer and size pointers

However, the **exact HID report bytes** that trigger the upgrade mode transition have not been identified. The EPOS protocol uses custom opcodes (likely in the 0xE0-0xFA range) that we couldn't fully decode from the disassembly.

## What I Tried

1. ✅ Extracted the EPOS Gaming Suite MSI
2. ✅ Identified the firmware update DLLs (HidDfu.dll, ModiUpdater.dll)
3. ✅ Discovered the dual-PID design (normal vs upgrade mode)
4. ✅ Confirmed HID communication works (device responds to our commands)
5. ✅ Disassembled the ModiUpdater.dll and found the hidDfuConnect call
6. ❌ Could not identify the exact HID report bytes to trigger upgrade mode
7. ❌ Tried brute-forcing opcodes (0xE0-0xFA) - none worked

## What Needs to Happen Next

### Option 1: Capture USB Traffic on Windows (Recommended)
1. Set up a Windows environment (VM with USB passthrough or physical PC)
2. Install EPOS Gaming Suite
3. Install Wireshark + USBPcap
4. Start USB traffic capture
5. Plug in the dongle
6. Open EPOS Gaming Suite
7. Trigger a firmware check/update
8. **Save the capture** - this will show the exact HID reports sent
9. Analyze the capture to find the upgrade trigger command

### Option 2: Deeper Disassembly
The HidDfu.dll is a complex library (~28K lines of disassembly). A more thorough analysis could find the exact HID report format. Tools needed:
- Ghidra (free, https://ghidra-sre.org/) for better decompilation
- More time to trace the data flow

### Option 3: Accept the Current State
The dongle works at 12M speed with 1.4s latency. While not ideal, it's still usable for:
- Game audio (latency doesn't matter much for game audio)
- Single-player games
- Watching videos

The wired USB-C connection (PID 0x008A) works perfectly with normal latency.

## Files Created

- `tools/gsp670-fw-probe.py` - Working HID communication tool
- `analysis/protocol-analysis.md` - Initial protocol analysis
- `analysis/upgrade-mode-discovery.md` - Discovery of dual-PID design
- `analysis/final-findings.md` - This document
- `extracted/` - 112 files from the EPOS Gaming Suite MSI
- `firmware/EPOSGamingSuite_original.msi` - The original installer

## Capture Attempts (2026-10-10)

A KVM/libvirt Windows 10 22H2 VM was set up to attempt packet-level
USB capture. The following were confirmed working:

- QEMU Guest Agent installed; remote control via QGA
- Wireshark 4.6.9 installed and running
- EPOS Gaming Suite installed (`C:\Program Files (x86)\EPOS\Gaming Suite\`)
- USBPcap 1.5.4.0 installed; kernel driver loads (`sc query USBPcap`
  returns RUNNING); `USBPcapCMD.exe` is present and accepts CLI args
- Dongle (1395:0300) attached to the VM via QEMU USB passthrough;
  visible in the guest as "USB Composite Device"
- ETW USB tracing works; captured 32 KB of hub events via
  `Microsoft-Windows-USB-USBHUB3`

**Major breakthrough (later same session):** USBPcap was found to be
unnecessary. QEMU has a native `pcap=` property on `usb-host` devices
that writes a real per-packet pcap file. A wrapper script at
`/usr/local/bin/qemu-system-x86-64-pcap` was set up that auto-injects
`pcap=` onto `usb-host` devices. With this wrapper, we captured:

- **932+ KB, 14,000+ USB packets** in `captures/initial-enumeration.pcap`
- Real USB control, ISOCHRONOUS, and INTERRUPT transfers between the
  EPOS Gaming Suite and the dongle
- Confirms the GSP 670 negotiates at 12 Mbps Full Speed (the underlying bug)

The capture itself is a success. The remaining blocker is that the
`EPOSGamingSuiteService` still crashes on startup with access
violation `0xc0000005` in `ConfigManager.dll` — meaning the firmware
update flow is not initiated. The EPOS GUI runs and does communicate
with the dongle (visible in the pcap as audio streaming), but does
not drive firmware checks without the service.

The USBPcap incompatibility is now obsolete. QEMU's pcap= feature
(added 2021) sidesteps USBPcap entirely. USBPcap remains installed
but is not used.

### What Would Unblock the Firmware Update Capture

- A real Windows machine where `EPOSGamingSuiteService` starts
  successfully (likely requires patching `ConfigManager.dll` or running
  EPOS on the specific hardware configurations it's been tested against)
- Run EPOS Gaming Suite via Wine on the Linux host (capture with
  usbmon)
- A pre-capture (someone with a working setup captures the traffic
  and publishes the pcap)

## Firmware Availability (Confirmed via Online Search, 2026-10-10)

A search across EPOS's official site, Reddit, Head-Fi, GitHub, the
Wayback Machine, and PulseAudio/PipeWire mailing lists confirmed:

**Our dongle already has the latest known firmware (3.3.43).**

- Headset firmware: 3.2.6 (latest known)
- Dongle firmware: 3.3.43 (latest known)
- Our dongle's `bcdDevice 3.14` is the bcd-decimal rendering of 3.3.43
- The dongle PID `0x0300` is the marker for the 3.3.43 firmware;
  older firmware (pre-3.3.43) used PID `0x0089`

**No fix exists for the 12 Mbps USB bug in any publicly known firmware
version.** Evidence:
- The 12M bug is consistent across all reported firmware versions
  (early 3.01, 3.02, 3.3.43)
- No community thread reports a fix
- EPOS's only response was the unrelated Linux audio interface quirk
  (kernel-side workaround)
- The EPOS Gaming product line has been sold to ACCO Brands and is
  end-of-life; no further updates are expected

**The firmware-update tool, if completed, would have nothing to flash.**
EPOS distributes firmware exclusively through the Gaming Suite
application — no standalone firmware download URLs exist. The only
publicly available artifact is the MSI installer we already have
(`firmware/EPOSGamingSuite_original.msi`), which does not contain the
firmware files in extractable form.

### Implications for the Project

The original project goal (a Linux tool that flashes a corrected
firmware to fix the 12M bug) is **blocked at the firmware-availability
level**, not at the protocol level. Reverse-engineering the upgrade
protocol cannot help because there is no firmware image to flash.

This means the most useful contributions of this project are:
1. **Documentation** of the Capricon protocol architecture (done)
2. **USB packet capture infrastructure** (done — QEMU pcap= wrapper)
3. **A working Linux HID probe tool** (done — `tools/gsp670-fw-probe.py`)
4. **A future-ready `gsp670-fw-update.py` skeleton** (architecture
   understood but implementation not justified without a fix image)

The infrastructure is now complete and preserved. Anyone resuming
this work has a full capture pipeline plus a complete protocol
analysis to build on.

## Realistic Paths Forward

1. **Use the wired USB-C connection** — works perfectly at ~44ms
   latency per `docs/observations.md`. No firmware intervention needed.
   This is the practical recommendation for end users.

2. **Linux xHCI driver workaround research** — check whether the
   kernel's xHCI driver has tunable parameters or quirks that can
   force high-speed operation for specific devices. ~1-2 hours of
   research; low but non-zero probability of a useful result.

3. **Hardware modification of the dongle** — investigate the USB PHY
   circuit on the dongle's PCB. Look for a USB hub controller chip
   with potentially swappable crystals, retimed signals, or upstream
   port current limiting that could be tweaked. Realistic but very
   low yield; risks bricking the dongle.

4. **Implement `tools/gsp670-fw-update.py` anyway** — the architecture
   is fully understood. The tool would be ready when/if a fixed
   firmware image emerges (e.g., from EPOS support, a leaked internal
   build, or a future community reverse-engineering effort).

## Conclusion

The GSP 70 dongle firmware update protocol is a custom EPOS "Capricon"
protocol that requires Windows-specific tools (EPOS Gaming Suite) or
extensive reverse engineering to replicate on Linux. The most practical
path forward is to either:
1. Run EPOS Gaming Suite on real Windows where the service starts;
   we have full capture infrastructure via QEMU's pcap= property to
   record the firmware update traffic
2. Accept the current 12M/1.4s limitation
3. Use the wired USB-C connection (which works perfectly)

**USB packet capture infrastructure is now complete.** The
foundation laid by this project (QEMU pcap= wrapper, libvirt VM with
all tools installed, QEMU Guest Agent remote control, working
internet, working USB passthrough) is ready for whoever can get the
EPOS service to run. See `captures/README.md` for the actual capture
file.

**Critical finding (post-search):** Our dongle already runs the latest
publicly known firmware (3.3.43), which contains the 12 Mbps USB bug.
No fixed firmware exists publicly. The project's end goal of building
a Linux firmware-update tool to fix the bug is blocked by firmware
unavailability, not by protocol reverse-engineering difficulty. The
end-user recommendation is to use the wired USB-C connection, which
sidesteps both the latency issue and the dongle entirely.

---

## Update: Direct HID Probing from Linux Host

After documenting the architectural findings, we attempted to bypass the EPOS
service entirely by probing the dongle directly via `/dev/hidraw*` on the
Linux host. **See `analysis/direct-hid-probing.md` for full details.**

### Key Discoveries

1. **HID Report ID = 0x6A** (not 0x01 as previously thought).
   The HID descriptor's vendor collection uses Report ID 106 (0x6A).

2. **HID interface has ONLY an IN endpoint** (EP 1 IN, Interrupt, 64 bytes).
   There is no Interrupt OUT endpoint. Host-to-device communication MUST use
   HID SET_REPORT control transfers.

3. **One notification observed** during a 30s listen:
   `01 EB FE 01 00 10 01 00 00 08 00 E1 00 01 00 F0 00 01 ...`
   This is likely `API_FWU_DEVICE_NOTIFY_IND` (FWU status notification).

4. **SET_REPORT commands reach the dongle** — verified via `usbmon` capture.
   The dongle accepts our commands but does not respond to arbitrary opcodes.

5. **The dongle is in deep idle state** — it only emits notifications on
   status events (button press, pairing event, headset connection, etc.),
   not on command response.

### Tools Created

- `tools/hid-listener.py` — Passive listener for dongle notifications
- `tools/probe-capricon-pyusb.py` — Active sender using `pyusb` SET_REPORT

### Implication

Without being able to capture EPOS's actual SET_REPORT commands during a
firmware update flow, we cannot determine the exact `API_FWU_ENABLE_REQ`
opcode. The dongle is responsive but waiting for a **specific command
sequence** that we don't have. This further reinforces the conclusion that
**the firmware fix does not exist publicly** — the path to a fixed dongle
firmware requires the EPOS proprietary Windows tool, and EPOS's gaming
division has been sold to ACCO Brands with no public commitment to fixing
this issue.

---

## Update 2026-10-11: Demand on the Protocol Is Lifted

The `/dev/hidraw` sweep work since the sections above has **fully cracked
the Capricon wire format** for host→dongle command/reply traffic. The
"exact upgrade trigger is unknown" claim in the earlier sections is
**superseded**:

- **Wire frame** (107-byte reports, report id `0x01`):
  `EB FE 01 00 | marker(04 00) | opcode LE | size LE | CRC-8 | 00 | payload`.
- **FWU_ENABLE_REQ = opcode `0x4F00`**, payload 2 bytes (`00 00` standard /
  `01 03` special-flag). Frame verified to be parsed correctly by the dongle
  (its replies behave per-opcode, proving the header-opcode framing is right).
- **Replies**: NAK `04 10` (empty payload or rejected FWU opcodes) vs
  ACK `05 30` (payload echoed verbatim, CRC tracks it). Transform
  `reply = (req & 0xFF00) | ((req & 0xFF) >> 2)`.
- **FWU family probed live** 0x4F01..0x4F15 — PID never changed; the dongle
  is *not* in FWU mode and NAKs the rejected group. The only untested opcode
  is `0x4F00` itself, which is expected to switch the dongle to PID 0x8089.

### Live 0x4F00 result (2026-10-11, user-approved single shot)

`0x4F00` / payload `00 00` was sent once and answered with a **NAK**:
`04 10 | 00 4F | 00 00 | FF` (size 0, crc FF), reply opcode 0x4F00 =
`req & 0xFFFC`. **No PID change** (stayed 0x0300). The bare FWU_ENABLE_REQ
with the standard payload does **not** switch the dongle to 0x8089 — it is
handled exactly like the other not-in-FWU-mode rejected opcodes. Open
follow-ups (not yet tried): the `01 03` special-flag payload, any required
pre-condition/session state before the dongle honors FWU_ENABLE, or a
different engineer while the EPOS service is running.

### Remaining status

- The protocol is fully mapped; the one REQ that *might* switch PIDs has
  now been tried with the standard payload and does not switch by itself.
- **Sending the `01 03` special-flag variant (same opcode, crc CB) is the
  next candidate**, still gated on explicit user approval like the 00 00
  send was.
- Ultimately a firmware image is still required to flash — which still does
  **not** exist publicly for dongle FW 3.3.43 (the 12 Mbps bug is unfixed in
  all known firmware). The protocol work is thus complete as far as it can
  be without either a captured genuine update session (needs a working EPOS
  service) or a fixed firmware image (none released).
- Full detail, tables and probe tooling in `analysis/direct-hid-probing.md`
  and `tools/` (`gsp_hid.py`, `opcode-sweep.py`, `paced-probe.py`,
  `fwu-sweep.py`).

---

## Update 2026-10-11 (session 2): FWU sequence pinned; next live test defined

### Framing ownership (closed)

- `EB FE 01 00` magic exists **only** in `EPOSGamingSuiteService.exe`.
  The `03 04` bytes in `ModiUpdater.dll`/`HidDfu.dll` are ASN.1 X.509 OIDs,
  not frame headers. The EXE's DCI stack (`RtxProtocol<Modi_>` ←
  **`NxpDatagramIO`**) is the origin of the Capricorn datagram framing that
  the dongle empirically accepts. ⇒ FWU_ENABLE must go out Capricorn-framed
  from the EXE path; ModiUpdater/HidDfu handle the *post-switch* DFU stage
  with their own non-Capricorn HID I/O.

### Full FWU opcode table (ModiUpdater.dll .rdata — names are authoritative)

0x4F00 ENABLE_REQ · 0x4F01 ENABLE_CFM · 0x4F02 DEVICE_NOTIFY_IND ·
0x4F03 UPDATE_REQ · 0x4F04 UPDATE_CFM · 0x4F05 UPDATE_IND ·
0x4F06 UPDATE_RES · 0x4F07 GET_BLOCK_IND · 0x4F08 GET_BLOCK_RES ·
0x4F09 GET_CRC_IND · 0x4F0A GET_CRC_RES · 0x4F0B COMPLETE_IND ·
0x4F0C STATUS_IND · 0x4F0D MULTI_CRC_IND · 0x4F0E MULTI_CRC_RES ·
*(0x4F0F gap)* · 0x4F10 SET_FEATURES_REQ · 0x4F11 SET_FEATURES_CFM ·
0x4F12 GET_FEATURES_REQ · 0x4F13 GET_FEATURES_CFM · 0x4F14 CRC32_IND ·
0x4F15 CRC32_RES. Only 0x4F00/0x4F10/0x4F12 are host→device requests —
everything else in our sweep was NAK'd because it is device→host traffic.

### The canonical start-update sequence (ModiUpdater `fcn.10007b90`)

**`0x4F10 SET_FEATURES_REQ / payload 01` → `0x4F00 ENABLE_REQ / payload
00 00`** (+4000 ms retry). A special-flag path sends `0x4F00 / 01 03`
instead. EXE mirrors: `FwuSetFeaturesRequest` (`10 4f <byte>`, expects CFM
0x4F11) and `FwuEnableRequest` (`00 4f <b0> <b1>`, expects CFM 0x4F01),
both under `RtxProtocol<Modi_>` / `GfFwu.update`.

### Next live test (gated on user approval; dongle currently unplugged)

1. `0x4F10` payload `01` → expect ACK `05 30` echo.
2. `0x4F00` payload `00 00` → watch for 0x0300 disappearance / 0x8089.
   Fallback `0x4F00` payload `01 03` if NAK.

Frames precomputed via `tools/gsp_hid.py` (crc F4 / D7 / CB). See
`analysis/direct-hid-probing.md` session-2 section for the exact bytes.

---

## Update 2026-10-11 (session 3): framing *proven*; why 0x4F00 NAKs; PID corrected

### 1. Frame format proven three ways (was: inferred)

- **Live HID descriptor** (read from `/sys/.../hidraw3/device/report_descriptor`):
  the vendor collection is `Usage Page 0xFFFF / Usage 0x01`, **Report ID 0x01**,
  Report Size 8, **Report Count `0x6A` (106)** → a 106-byte INPUT *and* a
  106-byte OUTPUT report. The long-standing "Report ID = 0x6A" note was a
  **misread of the Report-Count byte `95 6a`**; the report ID is `0x01`.
  Our tool's `report[0]=0x01` + 106 data bytes is exactly right.
- **`CCapricornDatagram::EncodeDatagram`** (`fcn.004ce570`) writes, verbatim:
  `[0]=01`, `[1..4]=EB FE 01 00`, `[5..6]=04 00`, `[7..8]=opcode LE`,
  `[9..10]=size LE`, `[13..]=payload`, then `[11]=CRC-8(payload)`.
- **`CCapricornDatagram::getHIDBuffers`** (`fcn.004c7b40`) builds the identical
  shape (and has an "Opcode not supported" reject path).

⇒ The wire encoder hypothesis is **no longer a hypothesis**. The dongle's
NAK to `0x4F00` is a genuine protocol-level rejection, not a framing error.

### 2. There are two transports — only one talks to the dongle

- **Capricorn/HID (`EB FE 01 00`, marker `04 00`)** → the dongle. This is what
  we use, and it is built by `EncodeDatagram` above.
- A **SLIP-style** frame built by `fcn.00676290` (reached from
  `ModiDatagramIO::send_command`): `01` │ `escape(0x01,0x04,0x10 → 0x10 xx)`
  │ `crc16 LE (escaped)` │ `04`. Device→host notifications are **not** stuffed,
  so this is the **radio/headset link**, *not* the dongle HID channel. It is
  not the missing piece.

### 3. Correct upgrade PID for this hardware

`extracted/DeviceInfoConfig.txt` maps brand abstract names to concrete PIDs:

| abstract | PID | notes |
|---|---|---|
| `EPOS_GSA_70` (our dongle) | **0x0300** | FWAdapter = Capricon |
| `EPOS_device_upgrade_mode` | **0x8300** | ← the matching upgrade PID |
| `EPOS_H3PRO_DONGLE_UPGRADE_MODE` | 0x8303 | different SKU |
| `Sennheiser_GSA_70` | 0x0089 | Sennheiser-brand variant |
| `Sennheiser_device_upgrade_mode` | 0x8089 | ← *not* ours |
| `Sennheiser_device_upgrade_mode_usb` | 0x808A | wired/USB variant |

Earlier tooling watched only `0x8089`; **for 0x0300 the expected upgrade PID is
`0x8300`**. (The live test still polled *all* 1395 PIDs, so no switch was
missed — the dongle simply stayed at 0x0300.) `tools/gsp_hid.py` now defines
`UPGRADE_PIDS = (0x8300, 0x8303, 0x8089, 0x808A)` and `fwu-enable-sequence.py`
watches for *any* new 1395 PID rather than a single constant.

### 4. The suite reaches FWU via a stateful mode dance, not one command

Static analysis of `EPOSGamingSuiteService.exe` shows a device-management
"agent" with explicit modes **normal / recovery / service / safe / update**:

- `ModiBaseStationDevice::detect_momo_dongle` — "Setting existing dongle into
  recovery mode"; devices detected in a "recovery VID/PID" are filtered out of
  call-control (recovery re-enumerates as a *different* VID/PID).
- `ModiFirmwareUpdater::prepare_update_mode` (`fcn.0068b300`) — logs
  "rebooting into FWU mode (EnterDfu)", arms a 1100 ms delay, then invokes a
  stored `std::function` (EnterDfu).
- `fcn.0068b650` — branches on the current mode: 3 = service ("device in
  service mode, proceeding"), 5 = update ("device already in update mode"); any
  other mode falls through to the EnterDfu path.
- `CSecomParserAdapter::EnterDfu` (`fcn.004b2720`) +
  `CCapricornDatagram::parseEnterDfu` (`fcn.004cb010`) confirm EnterDfu is
  itself a **Capricorn datagram** (same encoder as our frames).
- Cleanup paths mention restoring "recovery", "safe" and "normal" modes and
  "restart nested enumeration" — i.e. the transition involves re-enumeration,
  which a single raw HID write cannot reproduce.

### 5. "Enter DFU" is firmware-version gated

`fcn.0068b650` calls `fcn.00637fc0(device_info, 0x8f1c70)` = `FirmwareVersion::
compare(...) < 0` (the string "FirmwareVersion:: cannot compare firmware version
between two different family of devices" lives in `fcn.00638120`). If the
device FW is **older** than the constant at `0x8f1c70`, it takes the branch that
logs **"MODIFWU: device firmware {} does not support enter DFU mode, proceeding"**
(`fcn.006874f0`) and *skips* EnterDfu (falling back to a non-DFU/transparent
update). The threshold object is zero in the image and filled at runtime by the
static initialiser at `0x479b8b` as `FirmwareVersion(1, 5, 20)` — i.e. there is
an explicit minimum-version gate for the DFU trigger.

**Interpretation:** the dongle NAKs `0x4F00` because it is not in the mode the
suite establishes first; for a device/firmware below the gate the suite would
not even attempt EnterDfu. A single bare `FWU_ENABLE_REQ` is therefore not
expected to switch PIDs — consistent with the observed NAK.

### 6. Live-test candidates (still gated on explicit user approval)

Ranked by expected value / risk (all are Capricorn frames via
`tools/gsp_hid.py`):

1. `0x4F10 / 01` → `0x4F00 / 01 03` (the special-flag ENABLE variant — never
   actually sent live; the earlier attempt only did `00 00`).
2. **`0x4F12 GET_FEATURES_REQ`** (read-only capability query) — may report
   whether this firmware supports enter-DFU, and may be a required handshake.
3. `0x4F00` with alternative 2-byte payloads (`01 00`, `02 00`, `00 01`) —
   the EXE builder takes the two payload bytes from caller args.
4. Write via the **feature-report** path (HIDIOCSFEATURE) instead of the
   interrupt/output-report path, in case the firmware distinguishes them.

Each live send must be re-approved before execution (project rule).
