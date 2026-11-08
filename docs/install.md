# Installation

## The short version

```bash
sudo ./scripts/install.sh
```

Then unplug and replug the dongle (or the headset's USB-C cable).

Verify:

```bash
wpctl status | grep -i 'GSA 70'
```

---

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Linux kernel | ≥ 5.14.15 | Older kernels expose the device as mono only |
| PipeWire | ≥ 0.3.38 | Or PulseAudio ≥ 16 |
| wireplumber | any recent | Recommended; its config fixes a real bug (below) |
| Python | ≥ 3.9 | Only for the optional device-control features |
| hidapi | ≥ 0.14 | Only for the optional device-control features |

## What the installer does

| Step | Effect | Needed for |
|---|---|---|
| udev rules | your user gets `hidraw` access to the device | device controls |
| `gsp670-audio-guard.service` | re-probes `snd-usb-audio` if the ALSA card went missing | recovering from a silent headset |
| `50-gsp670.conf` (WirePlumber) | stops the idle USB-audio node from being suspended | Discord, EasyEffects |
| `50-gsp670-surround.conf` | optional host-side 7.1 virtualisation | surround |
| `gsp670` Python package | CLI + library | device controls |

The ALSA profile set that creates the "Game"/"Chat" split is **not** installed
by this project — it is the stock `usb-gaming-headset.conf` that ships with
PulseAudio/ALSA and that PipeWire reads through the ALSA configuration API.

## Installer options

```bash
sudo ./scripts/install.sh              # system-wide (recommended)
./scripts/install.sh --user            # per-user; no root except udev
./scripts/install.sh --dry-run         # show what would happen, change nothing
./scripts/install.sh --no-python       # audio setup only, no Python package
./scripts/install.sh --with-dbus       # also install the D-Bus stack
./scripts/install.sh --uninstall       # remove everything
```

`--dry-run` is safe to run at any time and prints every path it would touch.

## Per-distribution notes

### Debian / Ubuntu / Mint

```bash
sudo apt install python3-hidapi         # only for the device controls
sudo apt install python3-dbus python3-gi   # only for the D-Bus daemon
```

`libhidapi-hidraw0` is the underlying C library; the `python3-hidapi` package
pulls it in.

### Fedora / RHEL / Nobara

```bash
sudo dnf install python3-hidapi
sudo dnf install python3-dbus python3-gobject   # only for the D-Bus daemon
```

### Arch / CachyOS / Manjaro / EndeavourOS

```bash
sudo pacman -S python-hidapi
sudo pacman -S python-dbus python-gobject   # only for the D-Bus daemon
```

Note the Arch package names have no `3` in them.

### openSUSE

```bash
sudo zypper install python3-hidapi
```

### Alpine

```bash
sudo apk add py3-hidapi
```

### Void

```bash
sudo xbps-install python3-hidapi
```

### Gentoo

```bash
sudo emerge dev-python/hidapi
```

## Manual installation

If you would rather not run the installer:

### 1. udev rules

```bash
sudo cp udev/99-gsp670.rules /etc/udev/rules.d/
sudo cp udev/99-gsp670-audio.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

The first rule grants `audio`-group access to the device's `hidraw` node and
creates the symlinks `/dev/gsp670-dongle` and `/dev/gsp670-headset`. The
second asks systemd to start the audio guard when the dongle is plugged in.

Add yourself to the `audio` group and log out and back in:

```bash
sudo usermod -aG audio "$USER"
```

### 2. Audio guard

```bash
sudo install -Dm755 scripts/gsp670-audio-guard.sh /usr/lib/gsp670/gsp670-audio-guard.sh
sudo install -Dm644 systemd/gsp670-audio-guard.service \
    /usr/lib/systemd/system/gsp670-audio-guard.service
sudo systemctl daemon-reload
sudo systemctl enable --now gsp670-audio-guard.service
```

### 3. WirePlumber configuration

This is the important one. Without it, WirePlumber suspends the idle USB-audio
node, and the resulting resume race breaks Discord and EasyEffects.

```bash
sudo install -Dm644 contrib/wireplumber/50-gsp670.conf \
    /etc/wireplumber/wireplumber.conf.d/50-gsp670.conf
systemctl --user restart wireplumber
```

Use `~/.config/wireplumber/wireplumber.conf.d/50-gsp670.conf` instead of the
system path if you prefer a per-user install.

### 4. Python library (optional)

```bash
python3 -m pip install --user .
```

Or, for the D-Bus daemon as well:

```bash
python3 -m pip install --user '.[dbus]'
```

## Using the wired USB-C connection

The headset can be plugged in directly with the included USB-C cable. On Linux
it enumerates as `1395:008a` instead of the dongle's `1395:0300`, and it has
far lower latency (~44 ms versus ~1.4 s).

Everything in this project works with both. If you want to prefer the wired
headset when both are connected, tell WirePlumber to prefer it:

```lua
-- ~/.config/wireplumber/wireplumber.conf.d/52-gsp670-prefer-wired.lua
devices.rules = [
  {
    matches = [ { device.name = "~alsa_card.*GSP_?670.*" } ]
    actions = {
      update-props = {
        device.priority = 2000
      }
    }
  }
]
```

The default `Game`/`Chat` profile set expects the *dongle* layout, so the wired
headset may expose a single device instead of two. Check with:

```bash
wpctl status | grep -i 'GSP 670'
```

## Uninstall

```bash
sudo ./scripts/install.sh --uninstall
```

This removes the udev rules, the systemd unit and the WirePlumber
configuration. It leaves an installed Python package alone — remove that with
`pip uninstall gsp670` if you want to.
