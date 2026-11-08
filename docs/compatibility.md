# Compatibility

Hardware, kernel and distribution compatibility for the GSP 670 / GSA 70.

## Hardware

### Headsets and dongles

| Device | USB ID | Mode | Status | Notes |
|---|---|---|---|---|
| GSP 670 headset | `1395:008a` | wired USB-C | **works** | ~44 ms latency, 48 kHz stereo playback / 16 kHz mono capture |
| GSA 70 dongle | `1395:0300` | wireless 2.4 GHz | **works, with high latency** | ~1.4 s latency from a firmware bug |
| GSA 70 dongle | `1395:0300` | control interface | **works** | vendor HID protocol, for sidetone and friends |
| GSA 70 (upgrade PIDs) | `1395:8089`, `1395:808a`, `1395:8300`, `1395:8303` | firmware update | **blocked** | no firmware update is possible |

The GSP 670 is an **EPOS|Sennheiser** product. It is not a SteelSeries device,
despite the similar model numbers.

## Audio format

The headset exposes two ALSA devices on one card:

| ALSA device | Role | Format |
|---|---|---|
| `hw:X,0` | Chat — mono output + microphone | 48 kHz playback (mono), 16 kHz capture (mono) |
| `hw:X,1` | Game — stereo output | 48 kHz playback (stereo) |

Under PipeWire these become the `Game` and `Chat` sinks and the Chat capture
source. The stereo/mono split comes from the stock
`usb-gaming-headset.conf` ALSA profile set.

Full-duplex (simultaneous playback and capture) works.

## Kernel

| Kernel | Status | Notes |
|---|---|---|
| ≥ 5.14.15 | **works** | The USB-audio interface-reordering quirk is upstream; this is what creates the Game/Chat split |
| 5.14.0 – 5.14.14 | partial | May expose the device as mono only |
| < 5.14 | **mono only** | The device works, but only as a single mono device — no Game/Chat split, no stereo |

Check yours:

```bash
uname -r
```

The old community workaround — recompiling `snd-usb-audio` with a reversed
interface-creation order — is **not** needed on any current distribution. That
patch is obsolete.

## Audio stack

| Stack | Status | Notes |
|---|---|---|
| PipeWire ≥ 0.3.38 | **works** | Recommended |
| PipeWire < 0.3.38 | partial | May lack the required profile support |
| PulseAudio ≥ 16 | **works** | Uses the same ALSA profile set |
| PulseAudio < 16 | partial | May lack the required profile support |
| ALSA directly (`aplay`, `arecord`) | **works** | No mixing, no chat/game split |
| JACK via PipeWire | untested | |

The community PulseAudio profile project for this device was retired in 2022;
its own README states that kernels ≥ 5.15 and PulseAudio ≥ 16 support the
device natively. This repository therefore ships **no** custom ALSA profile.

## Distributions

The installer detects the distribution from `/etc/os-release` and maps the
`hidapi` package name accordingly. The audio path needs **no package from this
project** at all.

| Distribution | Package manager | `hidapi` package | D-Bus packages |
|---|---|---|---|
| Debian, Ubuntu, Mint, Pop, elementary, Kali | apt | `python3-hidapi` | `python3-dbus python3-gi` |
| Fedora, RHEL, CentOS, Rocky, AlmaLinux, Nobara | dnf | `python3-hidapi` | `python3-dbus python3-gobject` |
| Arch, CachyOS, Manjaro, EndeavourOS, Garuda | pacman | `python-hidapi` | `python-dbus python-gobject` |
| openSUSE, SLE | zypper | `python3-hidapi` | `python3-dbus python3-gi` |
| Alpine | apk | `py3-hidapi` | `py3-dbus py3-gobject` |
| Void | xbps | `python3-hidapi` | `python3-dbus python3-gobject` |
| Gentoo | emerge | `dev-python/hidapi` | `dev-python/dbus dev-python/pygobject` |

Anything else with a `systemd` and `udev` should work with the generic
installer; add the package name to `scripts/distros.sh` if the detection gets
it wrong.

### Verified on

| Distribution | Version | Kernel | PipeWire | Status |
|---|---|---|---|---|
| CachyOS | rolling | 7.3.1 | 1.6.10 | verified |

Other distributions are expected to work but have not been explicitly
verified. Contributions with a tested matrix entry are welcome.

## Python

| Version | Status |
|---|---|
| 3.9 – 3.13 | supported |
| 3.8 | not supported (`requires-python = ">=3.9"`) |
| 3.14 | works, used for development |

Dependencies:

| Package | Required for | Optional? |
|---|---|---|
| `hidapi` | the `gsp670` CLI and library | yes — audio needs none of this |
| `dbus-python` | the D-Bus daemon | yes (`gsp670[dbus]`) |
| `PyGObject` | the D-Bus daemon | yes (`gsp670[dbus]`) |

## Feature matrix

| Feature | Dongle (`1395:0300`) | Wired (`1395:008a`) |
|---|---|---|
| Stereo Game output | yes | yes |
| Mono Chat output | yes | yes |
| Microphone capture | yes | yes |
| Separate game/chat volume | yes | yes |
| Full duplex | yes | yes |
| Sidetone | yes | yes |
| Noise reduction | yes | yes |
| Auto power-off timer | yes | yes |
| Device identity readback | yes | yes |
| Event monitoring | yes | yes |
| Battery percentage | **no** | **no** |
| Volume / mute control | OS-side | OS-side |
| Firmware update | **no** | **no** |
| 7.1 surround | host-side only | host-side only |
| Acceptable latency | **no** (~1.4 s) | yes (~44 ms) |

See [limitations.md](limitations.md) for the details behind each "no".
