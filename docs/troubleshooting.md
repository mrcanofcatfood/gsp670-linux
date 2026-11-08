# Troubleshooting the GSP 670 / GSA 70 on Linux

## Start here: run the doctor

```bash
./scripts/gsp670-audio-doctor.sh
```

It is read-only, changes nothing, and prints what it finds about the USB
device, the ALSA card, the PipeWire nodes, the idle-suspend override, any host
DSP stage attached to your apps, and stale default devices. Most problems are
identified by it.

## Quick triage

| Symptom | Likely cause | Fix |
|---|---|---|
| No sound at all, no sink in `wpctl status` | the ALSA card failed to register | `sudo /usr/lib/gsp670/gsp670-audio-guard.sh` |
| Only one mono device, no "Game" | kernel older than 5.14.15 | upgrade the kernel |
| Voice is delayed by ~1.4 s | the dongle's firmware latency bug | use the wired Micro-USB connection |
| Discord says "no audio input detected" | idle-suspend churn, or chat routed through a DSP sink | install the WirePlumber drop-in; keep chat on the hardware nodes |
| Starting one app's audio stops another's | same as above | same as above |
| `gsp670` says "device not found" | udev rules missing, or user not in the `audio` group | `ls /etc/udev/rules.d/99-gsp670.rules`; `groups \| grep audio` |
| `PermissionError: /dev/hidraw*` | udev rules missing or not reloaded | `sudo udevadm control --reload-rules && sudo udevadm trigger` |
| Battery percentage missing | the device does not report it | nothing — see [limitations.md](limitations.md) §2 |

## Table of Contents

1. [Device Not Detected](#device-not-detected)
2. [Permission Problems](#permission-problems)
3. [Audio Not Working](#audio-not-working)
4. [Communication Errors](#communication-errors)
5. [Dongle Mode Issues](#dongle-mode-issues)
6. [Wired Mode Issues](#wired-mode-issues)
7. [Discord / Voice Chat](#discord--voice-chat)

---

## Device Not Detected

### Symptoms
```
DeviceNotFoundError: GSA 70 dongle not found
```
or
```
DeviceNotFoundError: GSP 670 headset not found
```

### Causes and Solutions

#### 1. Device not connected
**Check:** Run `lsusb | grep -i sennheiser` or `lsusb | grep 1395`

**Solution:** Connect the device and try again.

#### 2. Device in wrong mode
**Check:** `lsusb` shows different PID than expected
- GSA 70 in normal mode: PID 0x0300
- GSP 670 in wired mode: PID 0x008A
- GSA 70 in upgrade mode: PID 0x8300, 0x8303, 0x8089, or 0x808A

**Solution:** 
- For wireless mode, use the GSA 70 dongle
- For wired mode, connect the headset directly via Micro-USB
- For upgrade mode, you may need to reflash firmware (not covered here)

#### 3. USB enumeration issue
**Check:** `dmesg | tail` shows device detected but no hidraw created

**Solution:** Try unplugging and replugging the device, or try a different USB port.

---

## Permission Problems

### Symptoms
```
PermissionError: [Errno 13] Permission denied: '/dev/hidraw3'
```
or
```
hid.device() could not open the device
```

### Causes and Solutions

#### 1. User not in audio group
**Check:** `groups | grep audio` or `id -Gn`

**Solution:**
```bash
sudo usermod -aG audio $USER
# Log out and log back in for changes to take effect
```

#### 2. hidraw permissions too restrictive
**Check:** `ls -l /dev/hidraw*`

**Solution:** Use the provided udev rule:
```bash
sudo cp udev/99-gsp670.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# Then unplug and replug the device
```

Or set permissions manually (temporary):
```bash
sudo chmod 0660 /dev/hidraw*
```

#### 3. Running as root (not recommended)
**Solution:** Add udev rules for proper non-root access.

---

## Audio Not Working

### Symptoms
- Audio playback works but with severe delay
- Recording works but with issues
- ALSA shows device but audio doesn't work

### Causes and Solutions

#### 1. Wrong audio card selected
**Check:** `aplay -l` and `arecord -l` to find the correct card number

**Solution:** Use the correct card number in your application:
```bash
# Find the card
cat /proc/asound/cards

# Test playback
speaker-test -c2 -r48000 -D hw:X,0  # Replace X with card number

# Test capture
arecord -c1 -r16000 -f S16_LE -D hw:X,0 -d 5 test.wav
```

#### 2. Severe latency (wireless mode)
**Symptom:** ~1.4 second audio delay in wireless mode

**Cause:** Known firmware bug in GSA 70 dongle - USB PHY fails high-speed 
handshake and falls back to full-speed, causing massive buffering.

**Solution:** Use wired USB mode instead. The wired mode has excellent latency (~44ms).

#### 3. Sample rate mismatch
**Check:** Device supports 48000 Hz playback and 16000 Hz capture

**Solution:** Ensure your application uses the correct sample rates:
```bash
# For playback
speaker-test -c2 -r48000 -D hw:X,0

# For capture  
arecord -c1 -r16000 -f S16_LE -D hw:X,0
```

#### 4. Audio interface claimed by another program
**Check:** `lsof /dev/snd/*` or pulseaudio check

**Solution:** Stop other audio programs or configure them to not claim the device.

---

## Communication Errors

### Symptoms
```
CommunicationError: No response to opcode 0x4F12
```
or
```
NAK received from device
```

### Causes and Solutions

#### 1. Device in wrong mode
**Check:** Some opcodes only work in specific modes

**Solution:**
- FWU opcodes (0x4F00-0x4F1F) may require firmware mode enabled
- Try reading device notifications instead of sending commands

#### 2. Device not responding
**Check:** `sudo usbhid-dump -a 0x1395:0x0300` to see raw HID traffic

**Solution:** 
- Unplug and replug the device
- Try a different USB port
- Check if device is hung (power cycle may help)

#### 3. Timing issues
**Check:** Is the timeout too short?

**Solution:** Increase timeout in the exchange call:
```python
device.exchange(0x4F12, timeout_ms=1000)  # 1 second timeout
```

---

## Dongle Mode Issues

### Symptoms
- Dongle detected but can't communicate with headset
- Wireless link shows "disconnected"

### Causes and Solutions

#### 1. Headset not paired
**Check:** LED on dongle and headset

**Solution:** 
- Put headset in pairing mode (hold power button)
- Press pairing button on dongle
- Wait for LED to stop blinking

#### 2. Headset out of range
**Solution:** Move headset closer to dongle

#### 3. Headset powered off
**Check:** LED on headset

**Solution:** Power on the headset

---

## Wired Mode Issues

### Symptoms
- Headset detected but audio doesn't work
- Device enumeration shows headset but can't send commands

### Causes and Solutions

#### 1. Using dongle PID instead of headset PID
**Check:** `lsusb` should show PID 0x008A for wired mode

**Solution:** Connect headset directly via Micro-USB cable (not through dongle)

#### 2. Micro-USB cable issues
**Check:** Try a different cable

**Solution:** Some Micro-USB cables are charge-only

#### 3. Port power limitations
**Check:** Try a different USB port (preferably USB 3.0)

---

## Discord / Voice Chat

### Symptoms

- Discord shows **"No audio input detected"** while other apps record fine
- Discord's log flags `[AVError] no-audio-input-detected` and an `[InputWatcher]`
  that flaps `Silence: true` / `Silence: false`
- Starting Discord audio makes a browser tab (or another app) go silent

### Cause 1: a noise gate in the mic chain closes

If Discord's microphone is attached to `easyeffects_source`, every frame passes
through the EasyEffects input preset. The shipped mic presets include a
**Gate**; an aggressive gate (threshold −40 dB, 20 dB reduction) closes on quiet
input, so Discord sees silence.

**Check:**
```bash
scripts/gsp670-audio-doctor.sh
pactl list source-outputs | grep -A3 -i webrtc   # which Source is Discord on?
```
If the `Source:` is `easyeffects_source` (not the hardware `...mono-chat`):

**Fix:** bypass the gate in EasyEffects (Mic page → Gate → bypass), or load the
`GSP 670 - Voice` preset from `contrib/easyeffects/`, which now bypasses the
gate. Best for voice chat: route Discord to the hardware mic directly and keep
EasyEffects out of the voice path.

### Cause 2: idle-suspend churn

WirePlumber suspends the idle node after 5 s; when Discord opens the device the
node is torn down and rebuilt, and any DSP stage in front of it (EasyEffects, a
filter-chain) races the rebuild — producing the flapping silence and the
"one app stops another" behaviour.

**Check:**
```bash
pw-cli info $(pw-cli list-objects Node | grep -B5 mono-chat | grep -oE 'id: [0-9]+' | head -1 | cut -d' ' -f2) | grep state
journalctl --user -b | grep -i pw_manager   # EasyEffects "unknown resource" spam
```

**Fix:** install the drop-in that disables idle suspend for these nodes:
```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cp contrib/wireplumber/50-gsp670.conf ~/.config/wireplumber/wireplumber.conf.d/
systemctl --user restart wireplumber
```

### Cause 3: voice routed through the surround / DSP sink

If Discord outputs to `easyeffects_sink` or the `GSP670_Surround` filter-chain,
its two-channel voice is being run through a multi-channel HRTF convolver. Set
Discord's **Output Device** to `EPOS GSA 70 Game` and, if EasyEffects is
running, take the headset out of its Output chain.

### Not the cause

The dongle itself is **not** limited to one playback stream. The Game (stereo)
and Chat (mono) PCMs run simultaneously, and both PipeWire sinks run at once —
see `docs/hardware-info.md` § *Audio Interfaces*. "One app stops another" is a
host-side policy problem.

---

## Getting Help

### Diagnostic Information
Collect this information when reporting issues:

```bash
# Device info
lsusb -v -d 1395: 2>/dev/null | grep -E "idVendor|idProduct|bcdDevice"

# HID devices
ls -la /dev/hidraw*
cat /sys/kernel/debug/hid/*/rdesc | grep -A5 "1395"

# Audio devices
aplay -l
arecord -l

# Kernel messages
dmesg | tail -50
```

### Debug Mode
Enable debug output in Python:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
# Now run your code
```

### Capture USB Traffic
For detailed protocol analysis (requires a Windows VM with the EPOS Gaming
Suite — see [vendor-status.md](vendor-status.md#getting-the-epos-gaming-suite)):
```bash
# On Linux, you can only capture hidraw traffic
sudo cat /dev/hidrawX | xxd > capture.bin
```

---

## Known Limitations

1. **Wireless Latency**: The GSA 70 dongle has a firmware bug causing ~1.4s latency in wireless mode. This cannot be fixed in software, and there is no firmware update that would fix it — see [vendor-status.md](vendor-status.md).

2. **EPOS Suite Required for Updates**: Firmware updates require the Windows EPOS Gaming Suite application. It is still downloadable — see [Getting the EPOS Gaming Suite](vendor-status.md#getting-the-epos-gaming-suite) for the current and archived links.

3. **Gaming Division Wound Down**: EPOS Gaming was wound down by its parent company in September 2023, so there is no vendor Linux support and no further development for these devices. See [vendor-status.md](vendor-status.md).

4. **Bluetooth Mode**: Not officially supported by this library, though the headset may work natively with Linux BlueZ.
