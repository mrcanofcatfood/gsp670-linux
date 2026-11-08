# Virtual 7.1 Surround for the GSP 670 (verified working)

The GSP 670 has no SECOM device opcode for 7.1 surround (see
`docs/verified-secom-opcodes.md`); the Windows "7.1" button was backed by the
EPOS Gaming Suite APO on the host, not the dongle. The GSA 70 exposes only a
stereo ALSA "Game" device, so all surround virtualization happens on the host:
a PipeWire `filter-chain` sink that accepts 8-channel input, convolves every
channel with a head-related transfer function (HRTF), and outputs stereo to
the headset.

> The EPOS Gaming Suite itself is Windows-only, is not redistributable, and
> its vendor has wound down the gaming division — see
> [vendor-status.md](vendor-status.md). The host-side approach below is what
> replaces it on Linux.

This is now **implemented and objectively verified** on this project's test
system: `scripts/surround_verify.py --test` reports 8/8 channels reaching the
headset with correct interaural level and time differences.

## Components

| File | Purpose |
|---|---|
| `contrib/pipewire/gsp670-virtual-surround-7.1.conf` | The filter-chain sink definition (16 convolvers + 2 mixers) |
| `scripts/setup-virtual-surround.sh` | Downloads + verifies the HRTF IR, installs it, installs the PipeWire drop-in |
| `scripts/surround_verify.py` | Objective per-channel verification (see below) |

## Setup

```bash
scripts/setup-virtual-surround.sh --persist
systemctl --user restart pipewire wireplumber
```

Notes:
- The IR comes from the HeSuVi 2.0.0.1 installer (SourceForge); the setup
  script pins SHA-256 checksums of both the installer and the extracted
  preset. The default preset is `gsx.wav` — the HRTF captured from the
  Sennheiser GSX virtualization — with `--preset atmos` as an alternative.
- The IR is installed to `~/.local/share/pipewire/hrir_hesuvi/hrir.wav`, and
  the drop-in embeds its **absolute** path: relative IR paths resolve against
  the pipewire process CWD, not the data dir, on current PipeWire versions.
- `pactl load-module module-filter-chain` is **not supported** by
  pipewire-pulse 1.6.x (module table limitation) — use the conf.d drop-in and
  restart the user services. A brief audio interruption is normal.
- The sink routes its output straight to the GSA 70 Game device
  (`node.target`), bypassing EasyEffects and the default-sink path.

## Using it

```bash
# default for everything:
wpctl set-default "$(wpctl status | grep -oP '^\s+\K[0-9]+(?=\. GSP670_Surround)' | head -1)"
# ...or route a single app from your mixer (KDE audio widget / pavucontrol).
```

In games: select the output device "GSP 670 Virtual Surround 7.1" and set the
in-game speaker configuration to **7.1**. The game's per-channel audio is what
the HRTF needs — stereo content stays stereo (front-only).

## Verifying it works

Ear-based testing of stereo content cannot distinguish surround from stereo,
so verification is objective:

```bash
python3 scripts/surround_verify.py --test   # surround path
python3 scripts/surround_verify.py --ab     # + control run through raw stereo sink
python3 scripts/surround_verify.py --listen --set-default   # spoken positions by ear
```

`--test` plays an 8-channel file (one distinct tone per channel, sequential
time slots) into the surround sink while recording the GSA 70 Game monitor —
exactly the signal the headset receives — then measures per channel:

- **presence** (tone SNR vs noise floor),
- **ILD** (interaural level difference),
- **ITD** (interaural phase delay — the dominant cue real HRTFs provide at
  low frequency, where level differences are physically small).

PASS requires every tone present *and* positioned on its correct side.
`--ab` contrasts this with the raw stereo sink, where all channels are simply
folded down with no spatial processing. Capture uses `ffmpeg -f pulse` on the
sink monitor; `pw-record --target` silently fell back to the default source
on this setup and is not used.

Measured reference run (2026-10, HeSuVi gsx IR):

```
FL  220Hz  ILD -1.7dB  ITD -0.37ms   PASS      SL  560Hz  ILD -3.4dB  ITD -0.73ms  PASS
FR  305Hz  ILD -2.0dB  ITD +0.15ms   PASS      SR  645Hz  ILD +5.8dB  ITD +0.66ms  PASS
FC  390Hz  ILD +0.9dB  ITD -0.00ms   PASS      RL  730Hz  ILD -0.5dB  ITD -0.42ms  PASS
LFE 475Hz  ILD -3.2dB  ITD -0.44ms   PASS      RR  815Hz  ILD +5.5dB  ITD +0.21ms  PASS
```

## gsx.wav channel layout (important!)

HeSuVi preset WAVs are 14-channel (7 positions × left/right ear taps), but
**the per-preset channel order is not universal**. The canonical order
assumed by PipeWire's reference config
(`/usr/share/pipewire/filter-chain/sink-virtual-surround-7.1-hesuvi.conf`) is
`FL FL SL SL RL RL FC FR FR SR SR RR RR FC`, while **gsx.wav stores the
surround pairs rear-first**: `FL FL RL RL SL SL FC FR FR RR RR SR SR FC`.
Using the reference indices with gsx.wav silently crosses the side/rear
pairs (and mirrors their time/level cues), which is exactly the kind of error
ear-testing cannot catch. The shipped conf uses the measured gsx layout; if
you switch presets (`--preset atmos`), re-run
`python3 scripts/surround_verify.py --test` — a mismatch shows up as
`FAIL (positioned ...)` rows.

## Troubleshooting

- **Sink missing after restart**: `journalctl --user -u pipewire | grep -i hrir`
  — a `failed file hrir_hesuvi/hrir.wav` means the drop-in still has the
  relative path; re-run the setup script (`--persist`).
- **Graph loads but outputs silence**: same journal line — with `nofail` the
  sink exists even when the IR failed to load.
- **Only 2/8 channels in `--test`**: you are testing a stereo path; check the
  sink under test name (`--sink`).
- **EasyEffects**: the surround sink bypasses it by design. Keep EasyEffects
  for the microphone chain and (optional) speaker EQ on other outputs.

## License / provenance

HeSuVi — Headphone Surround Virtualizations for Equalizer APO — is
open-source software distributed at
https://sourceforge.net/projects/hesuvi/. The IR captures ship with the
installer; see its included license/readme for the per-preset credits.
