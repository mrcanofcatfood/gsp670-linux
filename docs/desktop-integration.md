# Desktop Integration Guide

This guide covers integrating the GSP 670 with Linux desktop environments.

## GNOME Shell Extension Idea

### Battery Indicator Extension

A GNOME Shell extension could provide:

- **Battery percentage** in the status bar
- **Link quality indicator** (based on connection stability)
- **Quick controls** (mute toggle, volume adjustment)

**Key APIs to use:**
```javascript
// Get device info via gsp670 CLI
Main.util.spawnCommandLine('gsp670 battery --json');

// Parse JSON output and update indicator
```

**Extension structure:**
```
gsp670-battery@extension/
├── extension.js      # Main extension logic
├── metadata.json     # Extension metadata
├── stylesheet.css    # UI styling
└── README.md        # Documentation
```

### Implementation Notes

1. Use `Meta.star_handle` for status bar integration
2. Poll battery status every 60 seconds (avoid excessive polling)
3. Use `Main.util.spawnCommandLineAsync` for async CLI calls
4. Handle device disconnection gracefully

### Alternative: GSConnect

[GSConnect](https://extensions.gnome.org/extension/1319/gsconnect/) can be configured to:
- Display phone battery (but can be extended for headset)
- Execute custom commands
- Show notifications

## KDE Plasma Widget Idea

### GSP 670 System Tray Widget

A Plasma widget could provide:

- **System tray icon** with battery/connection status
- **Popup widget** with detailed status
- **Plasmoid** for the desktop

**Key APIs:**
```cpp
// KDE System Tray integration
#include <KStatusNotifierItem>

// Execute CLI command
KShell::run("gsp670 battery --json", this);
```

**Widget structure:**
```
plasma-applet-gsp670/
├── package/
│   ├── metadata.json
│   ├── main.qml
│   ├── qml/
│   │   └── BatteryStatus.qml
│   └── contents/
│       └── config/main.xml
└── README.md
```

### Alternative: KDE KRunner

Configure KRunner to execute `gsp670` commands:
```ini
# ~/.config/krunnerrc
[Plugins]
ExternalCommands]
BinaryPatterns=gsp670:*
```

## Auto-Startup Configuration

### Systemd User Service

Create `~/.config/systemd/user/gsp670-monitor.service`:

```ini
[Unit]
Description=GSP 670 Status Monitor
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m gsp670 monitor
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable with:
```bash
systemctl --user enable gsp670-monitor
systemctl --user start gsp670-monitor
```

### D-Bus Activation

For desktop environment integration without polling:

```xml
<!-- ~/.local/share/dbus-1/services/com.gsp670.service -->
[D-BUS Service]
Name=com.gsp670
Exec=/usr/bin/gsp670 monitor --dbus
```

## UDev Rules for Device Tagging

Create `/etc/udev/rules.d/99-gsp670.rules`:

```udev
# GSP 670 Headset
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1395", ATTRS{idProduct}=="008a", \
    TAG+="systemd", ENV{SYSTEMD_WANTS}="gsp670-headset.service"

# GSA 70 Dongle
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1395", ATTRS{idProduct}=="0300", \
    TAG+="systemd", ENV{SYSTEMD_WANTS}="gsp670-dongle.service"

# Set device permissions for audio group
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1395", ATTRS{idProduct}=="008a", \
    GROUP="audio", MODE="0660"

SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1395", ATTRS{idProduct}=="0300", \
    GROUP="audio", MODE="0660"
```

Reload udev rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## PulseAudio/PipeWire Integration

### ALSA Configuration

Create `~/.asoundrc` for direct ALSA access:

```ini
pcm.gsp670 {
    type hw
    card "G670"
    device 0
}

ctl.gsp670 {
    type hw
    card "G670"
}
```

### Volume Control Integration

The GSP 670 volume wheel sends HID reports. To make it work with system volume:

1. Install `hid_listen` or use `evtest` to monitor events
2. Create a script to translate wheel events to volume changes:
```bash
#!/bin/bash
# ~/.local/bin/gsp670-volume.sh

evtest /dev/input/eventX | while read event; do
    if [[ $event == *"REL REL"*"* ]]; then
        # Extract delta and adjust volume
        volume=$(pactl get-sink-volume @DEFAULT_SINK@ | cut -d'%' -f1)
        pactl set-sink-volume @DEFAULT_SINK@ "${volume}%+$delta"
    fi
done
```

## Troubleshooting

### Device Not Detected

1. Check udev rules are loaded:
   ```bash
   lsusb | grep -i sennheiser
   hidraw-list
   ```

2. Verify permissions:
   ```bash
   ls -la /dev/hidraw*
   groups
   ```

### Audio Not Working

1. Check PulseAudio/PipeWire:
   ```bash
   pactl list sinks
   pw-cli list objects | grep -i gsp
   ```

2. Verify ALSA configuration:
   ```bash
   aplay -l
   arecord -l
   ```

### Battery Status Not Available

The GSP 670 doesn't expose battery via standard HID. Use the CLI:
```bash
gsp670 battery --json
```

## See Also

- [Troubleshooting Guide](troubleshooting.md)
- [Protocol Reference](protocol-reference.md)
- [Installation Guide](install.md)