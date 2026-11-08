# Documentation

Reference documentation for `gsp670-linux`.

## Start here

| Document | Contents |
|---|---|
| [install.md](install.md) | Installation, per distribution and manual |
| [quick-start.md](quick-start.md) | First steps after plugging in |
| [audio-setup.md](audio-setup.md) | Routing, the Game/Chat split, Discord |
| [troubleshooting.md](troubleshooting.md) | Symptom → cause → fix |
| [limitations.md](limitations.md) | Everything that cannot work, and why |
| [compatibility.md](compatibility.md) | Kernel, distribution and version matrix |
| [virtual-surround.md](virtual-surround.md) | Host-side 7.1 virtualisation |

## Using the CLI

| Document | Contents |
|---|---|
| [cli-reference.md](cli-reference.md) | Every `gsp670` command and flag |
| [gsp670.1](gsp670.1) | The man page |
| [desktop-integration.md](desktop-integration.md) | Control panels and D-Bus integration |

## Protocol

These describe the vendor's "Capricorn" HID protocol. They document the
observed hardware interface — the wire format, the opcodes and the event
model — which is what interoperability requires.

| Document | Contents |
|---|---|
| [verified-secom-opcodes.md](verified-secom-opcodes.md) | The opcode table, with live and corroborating evidence |
| [protocol-reference.md](protocol-reference.md) | Frame, marker and CRC reference |
| [opcode-database.md](opcode-database.md) | Opcode definitions |
| [hid-protocol.md](hid-protocol.md) | USB layout and HID interface |
| [analysis/](analysis/README.md) | High-level summary of the method and the reasoning |

## Legal

| Document | Contents |
|---|---|
| [legal.md](legal.md) | Legal position, provenance policy, and the publication boundary |

## Status and internals

| Document | Contents |
|---|---|
| [current-status.md](current-status.md) | What works, what is blocked, the one open question |
| [audio-dsp.md](audio-dsp.md) | How the audio path is organised |
| [pipewire-integration.md](pipewire-integration.md) | PipeWire and WirePlumber details |

## Support

Run the doctor first — it is read-only and usually identifies the problem:

```bash
./scripts/gsp670-audio-doctor.sh
```

Report bugs at <https://github.com/OWNER/gsp670-linux/issues>.

This is an independent project and is not affiliated with EPOS or
Sennheiser.
