# gsp670-linux

Linux support for the **EPOS|Sennheiser GSP 670** wireless gaming headset and
the **GSA 70** wireless dongle.

> The GSP 670 was made by Sennheiser and is now branded **EPOS**. It is *not* a
> SteelSeries product, despite the similar model numbering.

---

## What you get

The headset exposes **two separate audio devices**, exactly like on Windows:

| Device | Channels | Use it for |
|---|---|---|
| **Game** | stereo (2ch) | games, music, video |
| **Chat** | mono (1ch) | Discord / TeamSpeak / voice chat — plus the microphone |

The two volume knobs on the headset map onto these two devices, so you get
independent game and chat volume, like the vendor's Windows software does.

## Quick start

```bash
git clone https://github.com/OWNER/gsp670-linux
cd gsp670-linux
sudo ./scripts/install.sh
```

Then **unplug and replug** the dongle (or the headset's USB-C cable).

Verify:

```bash
wpctl status | grep -i 'GSA 70'
```

You should see a stereo `Game` sink and a mono `Chat` sink.

If anything looks wrong, run the doctor — it is read-only and safe:

```bash
./scripts/gsp670-audio-doctor.sh
```

### Per-user install (no root)

```bash
./scripts/install.sh --user
```

Only the udev rules need root, and they are only needed for the optional
device-control features (see below). Audio itself needs no privileges.

## How much setup is actually required?

Honestly, **very little**. On a modern system the kernel and PipeWire already
do the heavy lifting:

| Component | Who provides it |
|---|---|
| The ALSA card, and the "Game"/"Chat" split | The kernel (`snd-usb-audio`) plus the stock `usb-gaming-headset.conf` ALSA profile set that ships with PulseAudio/ALSA |
| The `Game` and `Chat` sinks and the mic source | PipeWire (or PulseAudio) reading that profile set |
| Audio routing, chat/game split, mic | PipeWire / WirePlumber |

So this repository installs **no kernel module and no custom ALSA profile**.
What it *does* install is the set of fixes that the stock configuration does
not cover:

1. **udev rules** — grant your user `hidraw` access to the device so the
   optional control features work.
2. **A systemd audio guard** — recovers the ALSA card in the rare case where
   the kernel binds the dongle's audio interfaces without registering a card,
   which leaves the headset completely silent.
3. **A WirePlumber configuration** — stops WirePlumber from suspending the
   idle USB-audio node. On this device the suspend/resume cycle races any
   host DSP stage and breaks Discord (`no-audio-input-detected`) and
   EasyEffects. This is the single most valuable file in the repo.

## Requirements

- Linux kernel **5.14.15 or newer** (older kernels expose the device as mono
  only — see [docs/compatibility.md](docs/compatibility.md))
- PipeWire **0.3.38+** or PulseAudio **16+**
- `wireplumber` (recommended — PipeWire's session manager)
- For the optional Python features: Python 3.9+ and `hidapi`

Supported on any systemd-based distribution. The installer detects the distro
and installs the right package names for Debian/Ubuntu, Fedora/RHEL, Arch
(including CachyOS/Manjaro), openSUSE, Alpine, Void and Gentoo.

## Optional: device controls

The headset has a vendor HID interface (the "Capricorn" protocol) that
exposes a few hardware features the OS mixer cannot reach. This repository
includes a Python library and CLI for them:

```bash
sudo ./scripts/install.sh      # installs hidapi + the gsp670 CLI
gsp670 info                    # firmware version, serial, device name, address
gsp670 status                  # link state, headset state
gsp670 controls list           # available controls
gsp670 controls set sidetone 5 # 0-10
gsp670 monitor                 # live device events (buttons, link, charging)
```

| Feature | Status |
|---|---|
| Sidetone (mic monitoring) | works |
| Noise reduction | works |
| Auto power-off timer | works |
| Device identity (FW, serial, name, address) | works |
| Event monitoring | works |
| Battery percentage | **not readable** — the device only acknowledges the request |
| Volume / mute | **OS-side** — use your mixer, these are not device commands |
| Firmware update | **not possible** — see below |

The CLI needs `hidapi` only. The D-Bus daemon additionally needs `dbus-python`
and `PyGObject`:

```bash
pip install 'gsp670[dbus]'
```

## Known limitations

These are hardware and firmware facts, not bugs in this project.

### The dongle has ~1.4 seconds of audio latency

The GSA 70 dongle's USB Full-Speed PHY has a buffering bug in its firmware
that adds roughly **1.4 seconds** of latency. Every known firmware release
(3.3.43) has it. This makes the dongle usable for chat but not for games.

**Use the wired USB-C connection** for gaming: it has about **44 ms** latency
and is the better choice anyway. The dongle is still useful for walking
around.

Both modes work on Linux; the wired headset enumerates as `1395:008a`.

### Battery percentage cannot be read

The battery query opcode only returns a link acknowledgement, never a
percentage. The headset's own LED indicator is the only guide. The `gsp670
battery` command reports what the device will tell you and explains the LED
legend.

### Firmware cannot be updated

The device rejects the firmware-update command at the firmware level; the
upgrade mode is gated behind a handshake that only the vendor's Windows
software performs. The device already runs the final known firmware
(dongle 3.3.43, headset 3.2.6), so there is nothing to flash anyway.

### 7.1 surround is host-side virtualisation

The headset hardware is stereo-only. There is no device-side surround DSP.
This repository can host-side virtualise 7.1 through a PipeWire filter-chain
using the HeSuVi GSX head-related impulse response:

```bash
./scripts/setup-virtual-surround.sh --persist
```

See [docs/virtual-surround.md](docs/virtual-surround.md).

## Troubleshooting

Start here:

```bash
./scripts/gsp670-audio-doctor.sh
```

It checks the USB device, the ALSA card, the PipeWire nodes and their state,
whether the idle-suspend override is actually applied, whether a host DSP
stage is sitting between your apps and the hardware, and whether your default
sink/source are stale. It prints what it finds and changes nothing.

Common issues and their fixes are in
[docs/troubleshooting.md](docs/troubleshooting.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/install.md](docs/install.md) | Per-distribution installation |
| [docs/quick-start.md](docs/quick-start.md) | First steps after plugging in |
| [docs/audio-setup.md](docs/audio-setup.md) | Routing, Discord and chat setup |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Symptom → cause → fix |
| [docs/compatibility.md](docs/compatibility.md) | Kernel, distro and version matrix |
| [docs/limitations.md](docs/limitations.md) | Everything that cannot work, and why |
| [docs/virtual-surround.md](docs/virtual-surround.md) | Host-side 7.1 virtualisation |
| [docs/cli-reference.md](docs/cli-reference.md) | `gsp670` command reference |
| [docs/protocol-reference.md](docs/protocol-reference.md) | The device HID protocol |
| [docs/verified-secom-opcodes.md](docs/verified-secom-opcodes.md) | Verified opcodes |
| [docs/legal.md](docs/legal.md) | Legal position and provenance policy |
| [docs/analysis/README.md](docs/analysis/README.md) | How the protocol was figured out |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest tests/ -q
```

The unit and integration tests need no hardware. The tests under
`tests/hardware/` need a physically connected device.

### Before publishing

The repository URL is a placeholder. Replace `OWNER` with your GitHub
username in these files:

```bash
grep -rl OWNER --exclude-dir=.venv --exclude-dir=.git . \
  | xargs sed -i 's|OWNER|<your-username>|g'
```

That covers `pyproject.toml`, `README.md`, the systemd units, the packaging
rules in `rules.d/`, and the docs.

## Uninstall

```bash
sudo ./scripts/install.sh --uninstall
```

## Legal

This project publishes the hardware **interface** only. It contains no vendor
binaries, no firmware, no decompiled output and no USB captures, and the
device's control protocol has no encryption, access control or licence
validation — so there is no protection measure being circumvented.

The boundary is enforced by a required CI check:

```bash
./scripts/check-provenance.sh
```

See [docs/legal.md](docs/legal.md) for the full position, and
[docs/analysis/README.md](docs/analysis/README.md) for the method used to
work out the protocol.

This is an independent project and is **not affiliated with EPOS or
Sennheiser**. Their trademarks are used only to identify the hardware.

## Licence

MIT — see [LICENSE](LICENSE).

The HeSuVi impulse responses used by the optional virtual-surround feature are
*not* bundled; they are downloaded on demand from the
[HeSuVi project](https://sourceforge.net/projects/hesuvi/) under its own
licence.
