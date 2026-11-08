# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-08

First public release.

### Added

#### Setup and diagnostics
- `scripts/install.sh` — generic, idempotent installer for any systemd
  distribution, with `--user`, `--dry-run`, `--no-python`, `--with-dbus` and
  `--uninstall` modes.
- `scripts/distros.sh` — distribution detection and package-name mapping for
  apt, dnf, pacman, zypper, apk, xbps and emerge.
- `scripts/gsp670-audio-doctor.sh` — read-only diagnostic that checks the USB
  device, the ALSA card, the PipeWire nodes and their state, whether the
  idle-suspend override is actually applied, whether a host DSP stage is
  attached to your apps, and whether the default sink/source are stale.
- `scripts/gsp670-audio-guard.sh` — re-probes `snd-usb-audio` when the ALSA
  card went missing, leaving the headset completely silent.
- `scripts/setup-virtual-surround.sh` — downloads and verifies the HeSuVi GSX
  impulse response and installs the host-side 7.1 virtualisation.

#### Configuration
- `udev/99-gsp670.rules` — grants `audio`-group access to the device's
  `hidraw` node and creates the `/dev/gsp670-dongle` and `/dev/gsp670-headset`
  symlinks.
- `udev/99-gsp670-audio.rules` — starts the audio guard when the dongle is
  plugged in.
- `contrib/wireplumber/50-gsp670.conf` — stops WirePlumber from suspending
  the idle USB-audio node. Without this the suspend/resume cycle races any
  host DSP stage, which breaks Discord (`no-audio-input-detected`) and
  EasyEffects.
- `contrib/pipewire/gsp670-virtual-surround-7.1.conf` — optional host-side 7.1
  virtualisation using a HeSuVi GSX impulse response.
- `contrib/easyeffects/` — EQ, limiter and voice presets.
- `systemd/gsp670-audio-guard.service` — the audio recovery unit.

#### Python library and CLI
- `gsp670` package with the Capricorn HID protocol implementation, device
  abstraction, discovery, controls, telemetry and event decoding.
- `gsp670` CLI: `info`, `status`, `battery`, `controls`, `monitor`, `events`,
  `protocol inspect`.
- Optional D-Bus daemon exposing device controls and link state
  (`pip install 'gsp670[dbus]'`).

#### Packaging
- `Makefile` with `install`, `uninstall`, `test`, `lint` and `format` targets.
- `rules.d/` — packaging rules for Debian, Arch and RPM.
- GitHub Actions CI running the test suite on Python 3.9–3.13 plus shellcheck.

#### Documentation
- `README.md`, `docs/install.md`, `docs/quick-start.md`, `docs/audio-setup.md`,
  `docs/troubleshooting.md`, `docs/limitations.md`, `docs/compatibility.md`,
  `docs/virtual-surround.md`, `docs/cli-reference.md`.
- Protocol documentation: `docs/protocol-reference.md`,
  `docs/verified-secom-opcodes.md`, `docs/opcode-database.md`.

### Fixed
- The audio guard matched the vendor ID only, so it would reload
  `snd-usb-audio` for unrelated Sennheiser devices. It now matches the full
  `1395:0300` product ID.
- `hidapi`, `dbus-python` and `PyGObject` are no longer imported at module
  scope, so `import gsp670` works without them and reports an actionable
  install hint if a feature genuinely needs one.
- Removed the duplicate `src/setup.py` build backend.
- Removed hardcoded developer paths from the systemd units.

### Legal and provenance

- Added `docs/legal.md` — the project's legal position: no proprietary
  material is redistributed, the device protocol has no protection measure
  (no encryption, access control, licence validation or authentication), so
  no circumvention is involved, and the interoperability exceptions that
  would apply if it were otherwise are recorded for Australia (s47D), the
  United States (17 USC §1201(f)) and the EU (InfoSoc Art. 6).
- Added `scripts/check-provenance.sh`, wired into CI as a **required** check.
  It fails the build on vendor binaries, oversized files, vendor code
  addresses, internal symbol names, disassembly listings, the vendor's
  executable name, and licence-key artefacts. A small allow-list
  (`scripts/provenance-allowlist.txt`) lets the legal documentation discuss
  those patterns.
- The detailed reverse-engineering notes were moved out of this repository
  into the maintainer's private workbench. The published
  `docs/analysis/README.md` keeps only the high-level method and findings.
- Rewrote `docs/hid-protocol.md` and the evidence sections of
  `docs/verified-secom-opcodes.md` and `docs/current-status.md` to describe
  observed behaviour rather than the vendor's implementation.
- Removed vendor-internal references from the source and test docstrings.
- Rewrote `rules.d/debian/copyright` to state plainly that no third-party or
  proprietary material is redistributed.

### Notes
- The "Game" (stereo) and "Chat" (mono) outputs come from the stock
  `usb-gaming-headset.conf` ALSA profile set that ships with PulseAudio/ALSA.
  This project ships no custom ALSA profile and no kernel module.
- The GSA 70 dongle firmware adds roughly 1.4 seconds of audio latency. The
  wired Micro-USB mode has about 44 ms. See `docs/limitations.md`.
