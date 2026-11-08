# Protocol findings — summary

This is a **high-level** summary of how the GSP 670 / GSA 70 control protocol
was figured out, and what was learned. It deliberately contains no vendor
code, no binaries, no disassembly, no internal symbol names, and no code
addresses from the vendor's software.

See [../legal.md](../legal.md) for the legal position, including the rule that
governs what may and may not be published here.

## Why this document exists

Some of the protocol behaviour is not self-evident from the wire format alone.
This note records the reasoning, so that a future reader can tell a
well-supported claim from a guess.

## Method

Two sources of evidence were used, in a deliberate order:

1. **Live probing of the hardware.** A GSA 70 dongle (`1395:0300`) and a GSP
   670 headset in USB device mode (`1395:008a`) were exercised directly over
   their HID interface, sending real frames and recording real responses.
   This is the primary evidence, and it is what the opcode tables are based
   on.

2. **Study of the vendor's Windows software.** The vendor's Windows
   configuration application was examined to *explain* behaviour that live
   probing had already demonstrated. Static analysis was used as a
   cross-check and to answer "why does the device behave this way?" — never
   as the sole basis for a documented behaviour.

**The evidence standard applied:** a behaviour is documented in this project
only if it was observed on real hardware. Where static analysis contributed
an explanation, it is presented as an explanation of an observed fact, and
the observation stands on its own. Where a question could not be settled by
observation, it is recorded as open rather than asserted.

## What was established

### The protocol is a plain HID command set

The device exposes a vendor-specific HID interface. Commands are fixed-size
reports with a small header (sync, marker, opcode, length, CRC) followed by
a short payload. The layout is documented in
[../protocol-reference.md](../protocol-reference.md).

Two consequences worth stating plainly:

- **There is no encryption and no obfuscation.** Payloads are plain bytes.
- **There is no access control, licence check or authentication.** The
  device answers identity and status queries on a plain read, with no prior
  handshake and no key exchange.

The CRC is an integrity check that detects a corrupted packet. It is not
keyed and not a protection measure.

### The device has two distinct audio paths

This is a hardware design point, not a software one: the headset provides a
stereo path for game audio and a mono path for voice chat, each with its own
volume knob. On Linux the kernel's USB audio driver and the stock
`usb-gaming-headset.conf` ALSA profile set expose these as the "Game" and
"Chat" devices. Nothing in this project is required for that to work — see
[../install.md](../install.md).

### The value queries return acknowledgements, not values

Asking the device for a *value* (battery level, sidetone level, and so on)
returns a link acknowledgement rather than the value. This is initially
counter-intuitive, and it was the single most confusing finding during the
work.

The explanation, established by studying how the vendor's own application
talks to the device, is that these values are **push-driven**: the device
sends them as unsolicited event notifications when they change, rather than
answering a query. There is no subscription command to send, because the
device simply reports changes as they happen.

This has a practical consequence that the project does not paper over:

- **Sidetone and noise reduction can be *set*** — the device acknowledges the
  write.
- **Battery percentage cannot be *read*** — the device only acknowledges the
  query. There is no host-side command that turns the acknowledgement into a
  value. The headset's own LED is the only guide.

This is documented as a limitation in [../limitations.md](../limitations.md)
rather than being worked around.

### Device events are unsolicited and typed

The device emits event notifications on its own — link state changes, button
presses, charging state. Each carries a type identifier, and the project
decodes these into named events (for example, a link-change event, a
pairing-status event). The mapping is in
[../verified-secom-opcodes.md](../verified-secom-opcodes.md).

### Firmware update is not possible

This was investigated thoroughly and the conclusion is negative. Two
independent reasons:

1. **There is nothing to flash.** The device already runs the final known
   firmware (dongle 3.3.43, headset 3.2.6), and no corrected firmware image
   is publicly available.
2. **The device rejects the update command at its own firmware level.**
   The vendor's Windows application reaches update mode through an
   orchestrated sequence — several mode transitions with USB re-enumeration
   between them — and a single command from a host cannot reproduce it.
   Every candidate formulation of the request was tried against real
   hardware and was refused.

The project therefore ships **no firmware-update tooling at all**, and does
not attempt to bypass the gate. `docs/limitations.md` §3 records the
conclusion.

### The dongle's audio latency is a firmware defect

The GSA 70 dongle adds roughly 1.4 seconds of audio latency. The cause is a
buffering defect in the dongle's USB link handling, present in every
firmware release that exists. It is not fixable in software, and the
workaround is to use the wired USB-C connection, which has about 44 ms
latency. See [../limitations.md](../limitations.md) §1.

### Some vendor features were identified but not implemented

The Windows application exposes a number of features the project does not
support — per-device EQ profiles, a chat mixer, and similar. These are
desktop-software conveniences rather than device capabilities, and they were
left out of scope.

## What this document does not contain, and why

| Not included | Why |
|---|---|
| Vendor binary data, executables or decompiled output | proprietary; not redistributable |
| Disassembly listings | implementation detail of a closed-source product; not needed to use the device |
| Internal symbol and class names from the vendor's software | as above |
| Code addresses from the vendor's binaries | as above |
| USB traffic captures | may embed copyrighted firmware |
| The reasoning trail behind the firmware-update conclusion | kept in the maintainer's private workbench |

The reasoning trail is not lost — it lives in a separate private workbench
repository that is never published. What is published here is the
*interface* and the *conclusions*, which is what interoperability requires.

## Verifying the claims

Every behavioural claim above can be checked against real hardware:

```bash
# Device identity, link state, and the event stream
gsp670 info
gsp670 status
gsp670 monitor
```

The protocol-level details are in
[../protocol-reference.md](../protocol-reference.md) and
[../verified-secom-opcodes.md](../verified-secom-opcodes.md), and the test
suite exercises the framing and event decoding against recorded frames —
see `tests/unit/test_fixtures.py` and `tests/fixtures/hid_frames.json`.

## See also

- [../legal.md](../legal.md) — legal position and the provenance policy
- [../protocol-reference.md](../protocol-reference.md) — the wire format
- [../verified-secom-opcodes.md](../verified-secom-opcodes.md) — the opcode table
- [../limitations.md](../limitations.md) — what the hardware cannot do
