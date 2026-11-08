# Quick Start

Get the EPOS|Sennheiser GSP 670 headset working on Linux.

## Prerequisites

- Linux kernel **5.14.15 or newer**
- PipeWire (0.3.38+) or PulseAudio (16+)
- `wireplumber` (recommended)
- The headset with either the GSA 70 dongle or the USB-C cable

## Step 1: Install

```bash
git clone https://github.com/OWNER/gsp670-linux
cd gsp670-linux
sudo ./scripts/install.sh
```

The installer detects your distribution and installs the right package names.
It is idempotent, so re-running it is safe.

Preview without changing anything:

```bash
sudo ./scripts/install.sh --dry-run
```

See [install.md](install.md) for per-distribution instructions and for a fully
manual installation.

## Step 2: Reconnect the device

Unplug and replug the GSA 70 dongle (or the headset's USB-C cable). The ALSA
card is created at plug-in time.

## Step 3: Verify the audio devices

```bash
wpctl status | grep -iE 'GSA 70|GSP 670'
```

You should see a **stereo** `Game` sink and a **mono** `Chat` sink, plus a
microphone source on the Chat device:

```
 ├─ Sinks:
 │      75. EPOS GSA 70 Chat                    [vol: 1.00]
 │  *   76. EPOS GSA 70 Game                    [vol: 1.00]
 │
 ├─ Sources:
 │  *   77. EPOS GSA 70 Chat                    [vol: 1.00]
```

If only one device appears, see [limitations.md](limitations.md) §6 — it is
usually an old kernel.

## Step 4: Set the defaults

```bash
wpctl set-default "$(wpctl status | grep -oP '^\s+\K[0-9]+(?=\. EPOS GSA 70 Game)' | head -1)"
wpctl set-default "$(wpctl status | grep -oP '^\s+\K[0-9]+(?=\. EPOS GSA 70 Chat)' | head -1)"
```

Full routing guidance, including Discord, is in
[audio-setup.md](audio-setup.md).

## Step 5: Check for problems

```bash
./scripts/gsp670-audio-doctor.sh
```

This is read-only. It reports what it finds and changes nothing.

## Step 6 (optional): device controls

The headset exposes a few hardware controls over the vendor HID protocol.
These need the Python package, which the installer already set up:

```bash
gsp670 info          # firmware version, serial, device name, address
gsp670 status        # link state, headset state
gsp670 controls list # available controls
gsp670 monitor       # live device events
```

The controls that work are sidetone, noise reduction and the auto-power-off
timer. Volume and mute are handled by the OS mixer, and the battery percentage
is not readable from the device — see [limitations.md](limitations.md).

## Common problems

### "Device not found"

```bash
lsusb | grep -i 1395
```

Expected: `1395:0300` for the dongle, `1395:008a` for the wired headset.

If the USB device is there but no audio device appears, the ALSA card may have
failed to register. The installed guard fixes this automatically; to do it by
hand:

```bash
sudo /usr/lib/gsp670/gsp670-audio-guard.sh
```

### "Permission denied" on the control commands

The udev rules grant the `audio` group access to the device's `hidraw` node.
Check that the rules are installed and that you are in the group:

```bash
ls /etc/udev/rules.d/99-gsp670.rules
groups | grep audio
```

If you were just added to the group, log out and back in.

### Discord says "no audio input detected"

This is usually the idle-suspend race, not a microphone fault. Confirm the
WirePlumber drop-in is installed:

```bash
ls ~/.config/wireplumber/wireplumber.conf.d/50-gsp670.conf
```

If it is missing:

```bash
sudo install -Dm644 contrib/wireplumber/50-gsp670.conf \
    /etc/wireplumber/wireplumber.conf.d/50-gsp670.conf
systemctl --user restart wireplumber
```

Also make sure Discord is not routed through an EasyEffects or virtual-surround
sink — the doctor script lists any such attachment.

### Audio is delayed by more than a second

That is the dongle's firmware latency bug, not a misconfiguration. Use the
wired USB-C connection for gaming. See [limitations.md](limitations.md) §1.

## Command reference

| Command | Description |
|---|---|
| `gsp670 info` | Device information and enumeration |
| `gsp670 status` | Headset and link status |
| `gsp670 battery` | Battery state (no percentage — see limitations) |
| `gsp670 controls list` | Available device controls |
| `gsp670 controls get/set` | Read or write a control |
| `gsp670 monitor` | Live device events |
| `gsp670 events` | Raw HID events |
| `gsp670 protocol inspect` | Known protocol opcodes |

Most commands accept `--json` for machine-readable output.

## Where to go next

- [install.md](install.md) — per-distribution and manual installation
- [audio-setup.md](audio-setup.md) — routing, Discord, chat/game split
- [troubleshooting.md](troubleshooting.md) — symptom → cause → fix
- [limitations.md](limitations.md) — what cannot work, and why
- [compatibility.md](compatibility.md) — kernel and distribution matrix
- [virtual-surround.md](virtual-surround.md) — host-side 7.1 virtualisation
