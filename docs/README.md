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

These describe the vendor's "Capricorn" HID protocol, recovered by reverse
engineering the vendor's Windows software. They document the observed wire
format; they contain no vendor code or binary data.

| Document | Contents |
|---|---|
| [verified-secom-opcodes.md](verified-secom-opcodes.md) | The authoritative opcode and payload table, with evidence |
| [protocol-reference.md](protocol-reference.md) | Frame, marker and CRC reference |
| [opcode-database.md](opcode-database.md) | Known opcode definitions |
| [hid-protocol.md](hid-protocol.md) | HID descriptor and interface layout |
| [analysis/](analysis/) | The working notes and evidence behind the above |

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
