# PipeWire Integration Guide

How the EPOS|Sennheiser GSP 670 / GSA 70 behaves under PipeWire + WirePlumber,
and how to configure it without breaking apps.

Everything below was written against **WirePlumber 0.5.x** (this project tested
on 0.5.18). The old WirePlumber **0.4 Lua** configuration path
(`~/.config/wireplumber/main.lua.d/*.lua`) **no longer exists** and is not used
anywhere in this guide.

## What the device exposes

The GSA 70 dongle (`1395:0300`) creates one ALSA card with **two playback
PCMs** and one capture PCM:

| Role | PipeWire node name | ALSA | Format |
|---|---|---|---|
| Game output | `alsa_output.usb-Sennheiser_EPOS_GSA_70-00.stereo-game` | `hw:C,1,0` | stereo 48 kHz |
| Chat output | `alsa_output.usb-Sennheiser_EPOS_GSA_70-00.mono-chat` | `hw:C,0,0` | mono 48 kHz |
| Mic input | `alsa_input.usb-Sennheiser_EPOS_GSA_70-00.mono-chat` | `hw:C,0,0` | mono 16 kHz |

The card's PipeWire object is `alsa_card.usb-Sennheiser_EPOS_GSA_70-00`
(description "EPOS GSA 70"). In **wired Micro-USB** mode the headset (`1395:008a`)
produces the same shape with `GSP_670` in the name.

> Do not hardcode the card index (`hw:2`) — it moves. Match on the node name.

Both playback PCMs can stream **simultaneously**; the device is not limited to
one output stream. If one app's audio kills another's, the cause is in the
session layer (suspend churn or a virtual DSP node), not the dongle.

## Configuration location (WirePlumber 0.5)

Drop-ins go in:

- `~/.config/wireplumber/wireplumber.conf.d/*.conf` (user)
- `/etc/wireplumber/wireplumber.conf.d/*.conf` (system)

They use the SPA-JSON syntax (`monitor.alsa.rules = [ { matches = [...] actions
= { update-props = { ... } } } ]`). A string value prefixed with `~` is a PCRE2
regular expression; `!~` negates it.

## Stop the idle-suspend churn (recommended)

WirePlumber suspends an idle ALSA node after `session.suspend-timeout-seconds`
(default **5**). On this headset the suspend → resume cycle races any host DSP
stage in front of the device, and the audible result is voice chat dropping out
and apps stealing each other's audio. Disable it for these nodes:

```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cp contrib/wireplumber/50-gsp670.conf ~/.config/wireplumber/wireplumber.conf.d/
systemctl --user restart wireplumber
```

The drop-in matches `~alsa_(output|input).*GSA_70.*` and
`~alsa_(output|input).*GSP_?670.*` and sets `session.suspend-timeout-seconds = 0`.
See `contrib/wireplumber/50-gsp670.conf` for the full rationale.

## Virtual 7.1 surround

Surround is **host DSP**, not a device feature — there is no SECOM opcode for
it. It is implemented as a PipeWire filter-chain
(`contrib/pipewire/gsp670-virtual-surround-7.1.conf`), not as an EasyEffects
preset. Setup and objective verification live in
[`docs/virtual-surround.md`](virtual-surround.md):

```bash
scripts/setup-virtual-surround.sh --persist
systemctl --user restart pipewire wireplumber
python3 scripts/surround_verify.py --test
```

**Keep voice chat out of the surround sink.** A multi-channel HRTF convolver
adds latency and it is the wrong node for two-channel voice. Route Discord and
other voice apps to the raw `...stereo-game` node, not to the surround sink.

## EasyEffects

The EasyEffects presets in `contrib/easyeffects/` are optional EQ/limiter
chains. Two cautions:

- If EasyEffects is running, it inserts `easyeffects_sink` /
  `easyeffects_source` between apps and the hardware, and apps that were using
  the hardware directly will end up attached to those virtual nodes. That is
  usually fine for music, but **not** what you want for voice chat.
- The mic presets include a noise **Gate**. A gate that is too aggressive
  (e.g. threshold −40 dB, 20 dB reduction) closes on quiet input and makes
  Discord report *"No audio input detected"*. The shipped
  `GSP 670 - Voice` preset now **bypasses the gate** by default, and the
  thresholds are relaxed (−55 / −60 dB, 12 dB reduction) for anyone who
  re-enables it.

## Setting the default device

```bash
wpctl status                 # find the node IDs
wpctl set-default <id>       # default sink (use the stereo-game node)
wpctl set-default <id>       # default source (use the mono-chat node)

wpctl set-volume <id> 0.8
wpctl set-mute <id> toggle
```

A **stale default** is a common silent failure: if
`default.configured.audio.source` points at a node that no longer exists (for
example a removed EasyEffects node), apps that follow the default get silence.
`scripts/gsp670-audio-doctor.sh` flags this.

## Diagnostics

```bash
scripts/gsp670-audio-doctor.sh          # device, nodes, suspend state, DSP stack, stale defaults
pw-top                                  # live graph activity
pw-link -l | grep -i gsa_70             # what links to what
journalctl --user -u wireplumber -f
```

If the dongle is plugged in but no ALSA card appears,
`scripts/gsp670-audio-guard.sh` re-probes `snd-usb-audio`; that is a different
failure mode from suspend.

## Troubleshooting

- **No card at all** → `scripts/gsp670-audio-guard.sh` / replug / different port.
- **Discord "no audio input detected", or audio flapping** →
  `docs/troubleshooting.md` § *Discord / voice chat*.
- **One app's audio stops another's** → disable idle suspend (above) and take
  voice apps off the EasyEffects / surround nodes.
- **Crackling / dropouts** → reserve RT priority:
  `/etc/security/limits.d/audio.conf` with `@audio - rtprio 90` and
  `@audio - memlock unlimited`.
- **Sample rates** differ (48 kHz playback / 16 kHz capture); PipeWire
  resamples automatically.
