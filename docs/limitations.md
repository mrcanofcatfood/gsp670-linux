# Limitations

Everything on this page is a property of the hardware or its firmware. None of
it is a bug in this project, and none of it can be worked around in software.

## 1. The wireless dongle adds ~1.4 s of latency

**Symptom.** You speak into the microphone and your voice reaches the other
side about 1.4 seconds later. The same happens to incoming audio.

**Cause.** The GSA 70 dongle runs at USB Full-Speed (12 Mbps) and its
firmware bridges the wireless link to USB with an insufficiently sized buffer.
The buffer is refilled rarely enough that roughly 1.4 seconds of audio
accumulates.

**Is it fixable?** No. Every publicly released dongle firmware (3.3.43) has
the same behaviour. The buffer size is baked into the firmware, and the
firmware cannot be updated — see limitation 3.

**What to do.** Use the wired Micro-USB connection for anything latency-sensitive.
It delivers about **44 ms** latency, which is fine for gaming. The dongle is
still useful if you want to move around; accept the delay for voice chat.

On Linux the two modes are distinct USB devices:

| Mode | USB ID | Latency |
|---|---|---|
| GSA 70 dongle (wireless) | `1395:0300` | ~1.4 s |
| GSP 670 headset, wired Micro-USB | `1395:008a` | ~44 ms |

Both work. This project supports both.

## 2. Battery percentage is not readable

**Symptom.** `gsp670 battery` reports the LED state but never a percentage.

**Cause.** The battery query opcode (`0x0e`) returns a link acknowledgement
instead of a value. This was confirmed against the vendor's own software: the
Windows suite reads the percentage through a different path that has not been
reproduced, and exhaustive analysis of the firmware's command dispatcher found
no host-side "enable battery events" command.

**What to do.** Use the headset's own LED indicator. The `gsp670 battery`
command prints the LED legend so you can interpret it.

The headset does report *charging* state and *link* state — those work.

## 3. Firmware cannot be updated

**Symptom.** There is no firmware update path.

**Cause.** Two independent reasons:

1. The device already runs the final known firmware — dongle 3.3.43, headset
   3.2.6 — so there is nothing to flash.
2. Even so, the firmware-update command is rejected at the firmware level. The
   vendor's Windows software reaches update mode through an orchestrated
   sequence (normal → recovery → service → update, with USB re-enumeration
   between stages) that a single raw HID write cannot reproduce. Both candidate
   enable payloads are NAKed by the device.

**What to do.** Nothing. Do not downgrade the headset's firmware either: some
vendor firmware versions change the USB descriptor in a way that breaks Linux
compatibility.

## 4. 7.1 surround is host-side only

**Symptom.** There is no "surround" mode in the headset itself.

**Cause.** The hardware DSP is stereo-only. The 7.1 modes in the vendor's
Windows software are implemented in software on the PC, not in the headset.

**What to do.** Use the host-side virtualisation in this repository. See
[virtual-surround.md](virtual-surround.md). It convolves an 8-channel stream
with a head-related impulse response and folds it down to the headset's stereo
output.

## 5. Volume and mute are not device commands

**Symptom.** `gsp670 controls set volume` does not change what you hear.

**Cause.** The GSP 670's volume wheel and mute are handled by the host audio
stack. The headset sends *notifications* when you turn the wheel, but the
level itself lives in the OS mixer.

**What to do.** Use the system mixer (`wpctl`, `pavucontrol`, `alsamixer`).
This project does not attempt to shadow the mixer.

The controls that *are* device-side and therefore work through this library:
sidetone, noise reduction, and the auto-power-off timer.

## 6. Older kernels expose the device as mono only

**Symptom.** On kernels older than about 5.14.15, the headset appears as a
single mono device. The "Game"/"Chat" split is missing and stereo output is
unavailable.

**Cause.** The kernel's USB audio driver enumerated the device's interfaces in
descriptor order, which puts the mono "Communication Audio" interface first.
Everything then bound to that interface.

**What to do.** Upgrade the kernel. The interface-ordering quirk is upstream
since ~5.14.15; no patching or out-of-tree module is needed.

For reference, the original community workaround was to recompile
`snd-usb-audio` with a reversed interface-creation order. That is no longer
necessary on any current distribution.

## 7. Audio can go silent until the dongle is replugged

**Symptom.** The headset is plugged in and powered, but there is no sink and
no microphone. `/proc/asound/cards` has no "EPOS GSA 70" entry.

**Cause.** Occasionally `snd-usb-audio` comes back from a device
re-enumeration having *bound* the dongle's audio interfaces without ever
creating an ALSA card.

**What to do.** This project installs `gsp670-audio-guard.service`, which
detects exactly this state and re-probes the module. It is a no-op when the
card is healthy. You can also run it by hand:

```bash
sudo /usr/lib/gsp670/gsp670-audio-guard.sh
```

## 8. Per-user udev rules are not reliable

The installer offers `--user`, which writes the udev rules to
`~/.config/udev/rules.d/`. Many distributions' `systemd-udevd` does not read
that directory, so those rules may be ignored. A system-wide install (the
default) is the reliable path. The audio guard in particular needs a system
unit.

## Summary

| Limitation | Workaround |
|---|---|
| Dongle latency ~1.4 s | Use the wired Micro-USB connection (~44 ms) |
| No battery percentage | Use the headset's LED indicator |
| No firmware updates | Nothing to do — the firmware is already final |
| No device-side 7.1 | Host-side virtualisation (this repo) |
| Volume/mute are OS-side | Use the system mixer |
| Mono-only on old kernels | Upgrade to kernel ≥ 5.14.15 |
| Occasional silent headset | The installed audio guard re-probes automatically |
