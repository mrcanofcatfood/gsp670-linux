# GSP 670 CLI Reference

Command-line interface for the EPOS|Sennheiser GSP 670 headset.

## Installation

```bash
pip install -e .
```

Or with the project in your PYTHONPATH:

```bash
PYTHONPATH=src python3 -m gsp670 <command>
```

## Commands

### `gsp670 info`

Show detailed device information including HID devices and ALSA audio devices.

```bash
gsp670 info
```

**Output includes:**
- HID device paths (dongle and headset)
- Audio device cards (playback and capture)
- Dongle communication test results

### `gsp670 status`

Show current headset status and pending notifications.

```bash
gsp670 status
```

**Output includes:**
- Device path and product name
- Any pending notification frames
- Status response from the device

### `gsp670 battery`

Show battery status and LED indicator legend.

```bash
gsp670 battery
```

**Output includes:**
- Battery level percentage (if available via notifications)
- Charging state
- LED color legend:
  - Red flashing: Critical (<10%)
  - Red solid: Low (10-20%)
  - Orange: Medium (20-50%)
  - Green solid: Good (>50%)
  - Green pulsing: Charging

### `gsp670 controls`

Manage headset controls.

#### `gsp670 controls list`

List available controls.

```bash
gsp670 controls list
```

#### `gsp670 controls get <control>`

Get current value of a control.

```bash
gsp670 controls get volume
gsp670 controls get mute
gsp670 controls get sidetone
```

#### `gsp670 controls set <control> <value>`

Set a control value.

```bash
gsp670 controls set mute on
gsp670 controls set mute off
```

**Note:** Software control of hardware buttons is not fully supported. These commands primarily track the local state.

### `gsp670 monitor`

Monitor and display control events in real-time.

```bash
gsp670 monitor               # Show all parsed events + raw frames
gsp670 monitor --watch battery  # Battery-only view with poll fallback
gsp670 monitor --watch link     # Link/sub-device state changes
gsp670 monitor --watch battery --timeout 120  # Run 2 minutes then exit
```

Press Ctrl+C to exit.

**Mode `all` (default)** shows every parsed frame plus the decoded event
dataclass (`BatteryEvent`, `ChargingEvent`, `LinkEvent`, …).

**Mode `battery`** listens passively for pushed battery events and falls back
to a `secom_exchange(0x0e)` poll every 30 s if the headset is linked but quiet.

**Mode `link`** reports headset link state changes (`SubDevicesEvent.count`
and raw `ConnectionStatus`).

**Note:** battery events arrive only when the headset is actively RF-linked
(push model — no subscription needed, see `docs/analysis/session-handshake.md`
Revision 2).

## Options

### `-d, --device`

Select which device to use.

```bash
gsp670 -d dongle status   # Use GSA 70 dongle
gsp670 -d headset status  # Use GSP 670 in device mode
gsp670 -d auto status     # Auto-detect (default)
```

- `auto` - Try dongle first, then headset (default)
- `dongle` - Use GSA 70 USB dongle
- `headset` - Use GSP 670 in wired USB device mode

### `-v, --version`

Show version information.

```bash
gsp670 --version
```

## Exit Codes

- `0` - Success
- `1` - Error (device not found, communication error, etc.)

## Examples

### Check if device is connected

```bash
$ gsp670 info
EPOS|Sennheiser GSP 670 Device Information
==================================================

HID Devices:
------------------------------
Type          PID    VID Path                 Product
----------------------------------------------------------------------
Dongle     0x0300  0x1395  /dev/hidraw3         
Headset    0x008A  0x1395  /dev/hidraw4         

Audio Devices:
------------------------------
Type        Card Name            ID
--------------------------------------------------
playback       4 G670            GSP 670
capture        4 G670            GSP 670
```

### Monitor volume changes

```bash
$ gsp670 monitor
GSP 670 Control Monitor
==================================================
Press Ctrl+C to exit

[0.52s] Frame received:
  opcode=0x4F02 kind=ack
  -> Control event: Volume Up
```

## Permissions

On Linux, accessing hidraw devices requires appropriate permissions. Install the udev rules:

```bash
sudo cp udev/99-gsp670.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# Log out and back in for group membership to take effect
```

Users need to be in the `audio` group to access the devices.
