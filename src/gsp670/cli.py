#!/usr/bin/env python3
"""
Command-line interface for GSP 670 headset control.

Usage:
    gsp670 info                      - Show device information
    gsp670 status                    - Show current headset status
    gsp670 controls list             - List available controls
    gsp670 controls get <control>   - Get control value
    gsp670 controls set <control> <value> - Set control value
    gsp670 battery                  - Show battery status
    gsp670 monitor                  - Monitor control events
"""

import argparse
import asyncio
import logging
import signal
import sys
import time

from . import (
    BatteryEvent,
    ChargingEvent,
    CommunicationError,
    DeviceError,
    DeviceNotFoundError,
    GSA70Device,
    GSP670Device,
    LinkEvent,
    SubDevicesEvent,
    enumerate_audio,
    find_devices,
    format_event_key,
    load_device_config,
    parse_frame_event,
    print_audio_devices,
    print_devices,
    save_device_config,
)


def get_device(args):
    """
    Get and open the appropriate device.

    Args:
        args: Parsed command-line arguments

    Returns:
        Open device instance

    Raises:
        DeviceNotFoundError: If device not found
        DeviceError: If device cannot be opened
    """
    # Try dongle first (primary interface)
    if args.device == 'auto' or args.device == 'dongle':
        try:
            dev = GSA70Device()
            dev.open()
            return dev
        except DeviceNotFoundError:
            if args.device == 'dongle':
                raise

    # Try headset
    if args.device == 'auto' or args.device == 'headset':
        try:
            dev = GSP670Device()
            dev.open()
            return dev
        except DeviceNotFoundError:
            if args.device == 'headset':
                raise

    raise DeviceNotFoundError(
        "No GSP 670 device found. Is the headset/dongle connected?"
    )


def cmd_info(args):
    """Show device information."""
    import json

    def bytes_to_str(val):
        """Convert bytes to string for JSON serialization."""
        if isinstance(val, bytes):
            return val.decode('utf-8', errors='replace')
        return val

    info = {
        'device': 'EPOS|Sennheiser GSP 670',
        'hid': {'devices': [], 'audio': []},
        'dongle': None,
    }

    # HID devices
    try:
        devices = find_devices()
        for d in devices:
            info['hid']['devices'].append({
                'path': bytes_to_str(d.get('path', b'')),
                'product': d.get('product_string', ''),
                'manufacturer': d.get('manufacturer_string', ''),
                'serial': d.get('serial_number', ''),
            })
    except Exception as e:
        info['hid']['error'] = str(e)

    # Audio devices
    try:
        info['hid']['audio'] = enumerate_audio()
    except Exception as e:
        info['hid']['audio_error'] = str(e)

    # Dongle info
    try:
        with GSA70Device() as dev:
            dongle_info = {
                'path': bytes_to_str(dev.info.path),
                'product': dev.info.product_string,
                'manufacturer': dev.info.manufacturer_string,
                'serial': dev.info.serial,
            }
            # Test communication using a valid SECOM opcode (GET_FW_VERSION = 0x00)
            try:
                resp = dev.exchange(0x00, timeout_ms=1000)
                dongle_info['communication'] = {
                    'kind': resp.kind,
                    'opcode': f'0x{resp.opcode:04X}',
                    'payload': resp.payload.hex() if resp.payload else '',
                }
            except Exception as e:
                dongle_info['communication_error'] = str(e)
            info['dongle'] = dongle_info
    except DeviceNotFoundError:
        info['dongle'] = {'error': 'not found'}
    except DeviceError as e:
        info['dongle'] = {'error': str(e)}

    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    # Human-readable output
    print("EPOS|Sennheiser GSP 670 Device Information")
    print("=" * 50)

    # HID devices
    print("\nHID Devices:")
    print("-" * 30)
    try:
        devices = find_devices()
        if devices:
            print_devices(devices)
        else:
            print("No HID devices found.")
    except Exception as e:
        print(f"Error enumerating HID: {e}")

    # Audio devices
    print("\nAudio Devices:")
    print("-" * 30)
    try:
        print_audio_devices()
    except Exception as e:
        print(f"Error enumerating audio: {e}")

    # Try to communicate with dongle
    print("\nDongle Communication Test:")
    print("-" * 30)
    try:
        with GSA70Device() as dev:
            print(f"  Path: {dev.info.path}")
            print(f"  Product: {dev.info.product_string}")
            print(f"  Manufacturer: {dev.info.manufacturer_string}")
            print(f"  Serial: {dev.info.serial}")

            # Try to get firmware version (valid SECOM opcode)
            print("\n  Testing communication...")
            try:
                resp = dev.exchange(0x00, timeout_ms=1000)
                print(f"  GET_FW_VERSION response: kind={resp.kind}, opcode=0x{resp.opcode:04X}")
                print(f"    payload ({len(resp.payload)} bytes): {resp.payload.hex()}")
            except Exception as e:
                print(f"  Communication test: {e}")
    except DeviceNotFoundError:
        print("  Dongle not found")
    except DeviceError as e:
        print(f"  Error: {e}")


def cmd_status(args):
    """Show current headset status."""
    import json

    def bytes_to_str(val):
        """Convert bytes to string for JSON serialization."""
        if isinstance(val, bytes):
            return val.decode('utf-8', errors='replace')
        return val

    status = {
        'device': None,
        'notifications': [],
        'status_response': None,
        'error': None,
    }

    try:
        with GSA70Device() as dev:
            status['device'] = {
                'product': dev.info.product_string,
                'path': bytes_to_str(dev.info.path),
            }

            # Drain notifications
            notifications = dev.drain(0.5)

            for frame in notifications:
                status['notifications'].append({
                    'opcode': f'0x{frame.opcode:04X}',
                    'kind': frame.kind,
                    'marker': frame.marker.hex(),
                    'size': frame.size,
                    'payload': frame.payload.hex() if frame.payload else '',
                })
            # Note: 0x4F0C (FWU_STATUS_IND) is a device-to-host notification, not a query opcode
            # It cannot be used with exchange() - attempting to do so would NAK
            # The drain() call above already captures device notifications
    except DeviceNotFoundError:
        status['error'] = 'Dongle not found'
        if not args.json:
            print("Error: Dongle not found. Is it connected?")
            return 1
    except DeviceError as e:
        status['error'] = str(e)
        if not args.json:
            print(f"Error: {e}")
            return 1

    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    # Human-readable output
    print("GSP 670 Status")
    print("=" * 50)

    if status['error']:
        return 1

    print(f"\nDevice: {status['device']['product'] or 'GSA 70 Dongle'}")
    print(f"Path: {status['device']['path']}")

    if status['notifications']:
        print(f"\nReceived {len(status['notifications'])} notification(s)")
        for i, notif in enumerate(status['notifications']):
            print(f"\n  [{i+1}] opcode={notif['opcode']} kind={notif['kind']}")
            print(f"       marker={notif['marker']} size={notif['size']}")
            print(f"       payload ({len(notif['payload'])//2} bytes): {notif['payload']}")
    else:
        print("\nNo notifications received.")
        print("Try adjusting volume or pressing a button on the headset.")

    if status['status_response']:
        print("\nRequesting status...")
        print(f"  Status response: kind={status['status_response']['kind']}, opcode={status['status_response']['opcode']}")
    elif status.get('status_response_error'):
        print(f"\n  Status request: {status['status_response_error']}")

    return 0


def cmd_controls_list(args):
    """List available controls."""
    print("GSP 670 Controls")
    print("=" * 50)

    controls = [
        ("device_name",   "Device name (SECOM 0x02)",              "string"),
        ("firmware",      "Firmware version (SECOM 0x00)",         "x.y.z"),
        ("serial",        "Serial number (SECOM 0x01)",            "string"),
        ("device_address","Device address (SECOM 0x03)",           "hex"),
        ("subdevices",    "Connected sub-devices (SECOM 0x04)",    "int"),
        ("battery",       "Battery percent (SECOM 0x0E)",          "0-100"),
        ("sidetone",      "Sidetone level (SECOM 0x10/0x11)",      "0-255"),
        ("noise_reduction","Noise reduction (SECOM 0x12/0x13)",    "0-255"),
        ("latency",       "Latency level (SECOM 0x16/0x17)",       "int"),
        ("auto_power_off","Auto power off (SECOM 0x1A/0x1B)",      "int"),
        ("volume",        "Master volume (OS mixer, not a device command)", "0-100"),
        ("mic_gain",      "Microphone gain (OS/APO, not a device command)", "0-100"),
        ("reverb",        "Reverb (APO only, not a device command)", "0-100"),
    ]

    print(f"\n{'Control':<16} {'Description':<42} {'Range'}")
    print("-" * 74)
    for name, desc, range_str in controls:
        print(f"{name:<16} {desc:<42} {range_str}")

    print("\nUse 'gsp670 controls get <control>' to read a value")
    print("Use 'gsp670 controls set <control> <value>' to set a value")
    print("\nSee docs/verified-secom-opcodes.md for the wire protocol.")


def cmd_controls_get(args):
    """Get a control value from the device."""
    control = args.control.lower()

    # Map CLI control names to device methods. Only the SECOM-backed controls
    # are real device commands; volume/mic-gain/reverb are OS/APO controls.
    GETTERS = {
        'volume': ('get_volume', "Master volume (OS mixer, not a device command)"),
        'mic_gain': ('get_mic_gain', "Microphone gain (OS/APO, not a device command)"),
        'sidetone': ('get_sidetone', "Sidetone level (opcode 0x10)"),
        'noise_reduction': ('get_noise_reduction', "Noise reduction level (opcode 0x13)"),
        'latency': ('get_latency', "Latency level (opcode 0x17)"),
        'battery': ('get_battery_percentage', "Battery percent (opcode 0x0E)"),
        'auto_power_off': ('get_auto_power_off', "Auto power off (opcode 0x1B)"),
        'subdevices': ('get_subdevices_connected', "Connected sub-devices (opcode 0x04)"),
        'device_name': ('get_device_name', "Device name (opcode 0x02)"),
        'firmware': ('get_firmware_version', "Firmware version (opcode 0x00)"),
        'serial': ('get_serial_number', "Serial number (opcode 0x01)"),
        'device_address': ('get_device_address', "Device address (opcode 0x03)"),
        'reverb': ('get_reverb', "Reverb level (APO only, not a device command)"),
    }

    if control not in GETTERS:
        print(f"Unknown control: {control}")
        print("Available controls: " + ", ".join(GETTERS.keys()))
        return 1

    method_name, _desc = GETTERS[control]

    try:
        with GSA70Device() as dev:
            getter = getattr(dev, method_name)
            value = getter()

            if isinstance(value, (bytes, bytearray)):
                print(f"{control}: {bytes(value).hex()}")
                return 0

            if value is None:
                print(f"{control}: unavailable (needs the headset linked and powered on)")
                return 1

            if value == -1:
                print(f"{control}: not a device control (use the OS mixer / APO)")
                return 1

            print(f"{control}: {value}")

    except DeviceNotFoundError:
        print("Error: GSA 70 dongle not found. Is it connected?")
        return 1
    except CommunicationError as e:
        print(f"Communication error: {e}")
        return 1
    except DeviceError as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_controls_set(args):
    """Set a control value on the device."""
    control = args.control.lower()
    value_str = args.value

    # Map CLI control names to device methods. Only SECOM setters are real
    # device commands; volume/mic-gain/reverb are OS/APO controls.
    SETTERS = {
        'volume': ('set_volume', int, 0, 100),
        'mic_gain': ('set_mic_gain', int, 0, 100),
        'sidetone': ('set_sidetone', int, 0, 255),
        'noise_reduction': ('set_noise_reduction', int, 0, 255),
        'auto_power_off': ('set_auto_power_off', int, 0, 255),
        'reverb': ('set_reverb', int, 0, 100),
    }

    # Config field mapping for persistence
    CONFIG_FIELDS = {
        'sidetone': 'sidetone_level',
        'noise_reduction': 'noise_reduction_level',
        'auto_power_off': 'auto_power_off_minutes',
    }

    if control not in SETTERS:
        print(f"Unknown control: {control}")
        print("Available controls: " + ", ".join(SETTERS.keys()))
        return 1

    method_name, parser, min_val, max_val = SETTERS[control]

    # Parse value
    try:
        if parser is int:
            value = int(value_str)
            if not min_val <= value <= max_val:
                print(f"Value must be between {min_val} and {max_val}")
                return 1
    except ValueError:
        print(f"Invalid value: {value_str}")
        return 1

    try:
        with GSA70Device() as dev:
            setter = getattr(dev, method_name)
            success = setter(value)

            if success:
                print(f"Set {control} to {value}")

                # Persist to config if it's a device setting
                if control in CONFIG_FIELDS:
                    config = load_device_config()
                    config.serial = dev.get_serial_number()
                    setattr(config, CONFIG_FIELDS[control], value)
                    save_device_config(config, serial=config.serial)
                    print("  (saved to config)")
            else:
                print(f"Device rejected the request for {control}")
                return 1

    except DeviceNotFoundError:
        print("Error: GSA 70 dongle not found. Is it connected?")
        return 1
    except CommunicationError as e:
        print(f"Communication error: {e}")
        return 1
    except DeviceError as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_controls_restore(args):
    """Restore settings from config file to device."""
    # Load saved config
    config = load_device_config()

    if config.serial is None:
        print("No saved configuration found. Set some controls first.")
        return 1

    print(f"Restoring settings for device {config.serial}")

    # Settings that can be restored
    setters = []
    if config.sidetone_level > 0:
        setters.append(('sidetone', config.sidetone_level, 'set_sidetone'))
    if config.noise_reduction_level >= 0:
        setters.append(('noise_reduction', config.noise_reduction_level, 'set_noise_reduction'))
    if config.auto_power_off_minutes >= 0:
        setters.append(('auto_power_off', config.auto_power_off_minutes, 'set_auto_power_off'))

    if not setters:
        print("No device settings to restore.")
        return 0

    try:
        with GSA70Device() as dev:
            actual_serial = dev.get_serial_number()
            if actual_serial != config.serial:
                print(f"Warning: connected device serial {actual_serial} != saved {config.serial}")

            for name, value, method in setters:
                setter = getattr(dev, method)
                success = setter(value)
                status = "OK" if success else "FAILED"
                print(f"  {name}: {value} [{status}]")

    except DeviceNotFoundError:
        print("Error: GSA 70 dongle not found. Is it connected?")
        return 1
    except CommunicationError as e:
        print(f"Communication error: {e}")
        return 1
    except DeviceError as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_battery(args):
    """Show battery status."""
    import json

    battery = {
        'device': None,
        'notifications': [],
        'led_indicator': {
            'red_flash': 'Critical (<10%)',
            'red_solid': 'Low (10-20%)',
            'orange': 'Medium (20-50%)',
            'green_solid': 'Good (>50%)',
            'green_pulse': 'Charging',
        },
        'error': None,
    }

    # Try to get status via dongle
    try:
        with GSA70Device() as dev:
            battery['device'] = {
                'product': dev.info.product_string,
            }

            # Drain to see if any battery notifications come in
            dev.drain(0.2)  # Clear buffer

            # Request status and listen
            try:
                dev.write(0x4F0C)  # STATUS_IND request
                time.sleep(0.5)
                notifications = dev.drain(1.0)

                for frame in notifications:
                    battery['notifications'].append({
                        'opcode': f'0x{frame.opcode:04X}',
                        'payload': frame.payload.hex() if frame.payload else '',
                    })
            except Exception as e:
                battery['status_request_error'] = str(e)

    except DeviceNotFoundError:
        battery['error'] = 'Dongle not found'
        if not args.json:
            print("Error: Dongle not found.")
            return 1
    except DeviceError as e:
        battery['error'] = str(e)
        if not args.json:
            print(f"Error: {e}")
            return 1

    if args.json:
        print(json.dumps(battery, indent=2))
        return 0

    # Human-readable output
    print("Battery Status")
    print("=" * 50)

    if battery['error']:
        return 1

    print(f"\nDevice: {battery['device']['product'] or 'GSA 70 Dongle'}")

    if battery['notifications']:
        print(f"\nReceived {len(battery['notifications'])} status notification(s)")
        for i, notif in enumerate(battery['notifications']):
            print(f"\n  [{i+1}] opcode={notif['opcode']}")
            print(f"      payload: {notif['payload']}")
    else:
        print("\nNo status notifications received.")
        print("Battery status may only be available through audio notifications.")

    # Note about battery LED
    print("\n" + "=" * 50)
    print("Battery LED indicator on headset:")
    print("  Red flashing  - Critical (<10%)")
    print("  Red solid      - Low (10-20%)")
    print("  Orange         - Medium (20-50%)")
    print("  Green solid    - Good (>50%)")
    print("  Green pulsing  - Charging")

    return 0


def cmd_monitor(args):
    """Monitor control events."""
    if args.watch in ('battery', 'link'):
        return _cmd_watch(args)

    print("GSP 670 Control Monitor")
    print("=" * 50)
    print("Press Ctrl+C to exit")
    print()

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        print("\n\nStopping monitor...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    try:
        with GSA70Device() as dev:
            print(f"Monitoring device: {dev.info.product_string or 'GSA 70'}")
            print("-" * 50)

            last_event_time = time.time()

            while running:
                # Read with short timeout
                frame = dev.read(timeout_ms=100)

                if frame:
                    now = time.time()
                    elapsed = now - last_event_time
                    last_event_time = now

                    print(f"\n[{elapsed:.2f}s] Frame received:")
                    print(f"  opcode=0x{frame.opcode:04X} kind={frame.kind}")
                    print(f"  marker={frame.marker.hex()} size={frame.size}")
                    print(f"  payload ({len(frame.payload)} bytes): {frame.payload.hex()}")

                    # Decode device -> host event keys with parsed values
                    event_key = format_event_key(frame.payload)
                    if event_key:
                        print(f"  -> Event: {event_key}")

                    # Parse the full event with value bytes decoded
                    event = parse_frame_event(frame)
                    if event:
                        # Show the event dataclass representation
                        print(f"  -> Parsed: {event}")
                        # Show key fields for known event types
                        if hasattr(event, 'level'):
                            print(f"      level={event.level}%")
                        if hasattr(event, 'state') and isinstance(event, ChargingEvent):
                            charging_names = {0: "not charging", 1: "charging", 2: "full"}
                            print(f"      state={event.state} ({charging_names.get(event.state, 'unknown')})")

                time.sleep(0.01)  # Small sleep to prevent CPU spinning

    except DeviceNotFoundError:
        print("Error: Dongle not found.")
        return 1
    except DeviceError as e:
        print(f"Error: {e}")
        return 1

    return 0


async def _run_watch_battery(dev, timeout, poll_interval=30.0):
    """
    Watch battery events with a poll fallback that is independent of traffic.

    Reads parallel to :meth:`GSA70Device.watch_events` (no subscription), but
    drives the read loop directly so the poll fallback also fires when the
    dongle pushes nothing (previously it was buried inside the event loop body
    and never ran on a silent link).
    """
    last_poll = time.time()
    deadline = time.time() + timeout if timeout > 0 else None

    while True:
        if deadline is not None and time.time() >= deadline:
            break

        f = dev.read(50)  # blocking up to 50 ms, same as watch_events
        if f is not None:
            evt = parse_frame_event(f)
            if isinstance(evt, BatteryEvent):
                ts = time.strftime('%H:%M:%S')
                charging_str = ""
                if evt.charging_changed is not None:
                    state_map = {0: "not charging", 1: "charging", 2: "full"}
                    charging_str = f" ({state_map.get(evt.charging_changed, '?')})"
                print(f"[{ts}] Battery: {evt.level}%{charging_str}")
                last_poll = time.time()
            elif isinstance(evt, SubDevicesEvent):
                ts = time.strftime('%H:%M:%S')
                status = "LINKED" if evt.count > 0 else "UNLINKED"
                print(f"[{ts}] link: {status} (sub-devices: {evt.count}) — "
                      "battery events flow only while the headset is linked")
                last_poll = time.time()

        # Poll fallback (fire-and-forget) on its own timer.
        if time.time() - last_poll >= poll_interval:
            try:
                level = dev.get_battery_percentage()
                if level is not None:
                    ts = time.strftime('%H:%M:%S')
                    print(f"[{ts}] Battery (polled): {level}%")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Battery: no response "
                          "(headset not linked?)")
                last_poll = time.time()
            except Exception:
                pass

        await asyncio.sleep(0.05)  # pace the loop; real reads block ~50 ms anyway


async def _run_watch_link(dev, timeout):
    """Watch link events."""
    async for evt in dev.watch_events(timeout=timeout):
        if isinstance(evt, (LinkEvent, SubDevicesEvent)):
            ts = time.strftime('%H:%M:%S')
            if isinstance(evt, SubDevicesEvent):
                # count = number of linked sub-devices (documented link indicator)
                status = "LINKED" if evt.count > 0 else "UNLINKED"
                print(f"[{ts}] Headset: {status} (sub-devices: {evt.count})")
            else:
                # ConnectionStatus raw value; semantics not yet documented
                print(f"[{ts}] ConnectionStatus: raw={evt.status}")


def _cmd_watch(args):
    """Handle --watch mode: async event generators."""
    print(f"GSP 670 Event Watch — {args.watch}")
    print("=" * 50)
    print("Press Ctrl+C to exit")
    print()

    try:
        with GSA70Device() as dev:
            print(f"Device: {dev.info.product_string or 'GSA 70'}")
            print("-" * 50)
            print("Note: battery events arrive only when the headset is linked.\n")

            if args.watch == 'battery':
                coro = _run_watch_battery(dev, args.timeout or 0)
            else:  # link
                coro = _run_watch_link(dev, args.timeout or 0)

            # Default SIGINT handler raises KeyboardInterrupt inside the loop,
            # which we catch to exit cleanly (device closes via the with).
            try:
                asyncio.run(coro)
            except KeyboardInterrupt:
                print("\n\nStopping watch...")
    except DeviceNotFoundError:
        print("Error: Dongle not found.")
        return 1
    except DeviceError as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_protocol_inspect(args):
    """Show all known protocol opcodes and their status."""

    print("GSP 670 Protocol Opcode Inspector")
    print("=" * 60)
    print()

    # FWU Opcodes (0x4F00-0x4F15)
    fwu_opcodes = [
        (0x4F00, "FWU_ENABLE_REQ", "host->device", "Enable firmware update mode"),
        (0x4F01, "FWU_ENABLE_CFM", "device->host", "Enable confirmation"),
        (0x4F02, "FWU_DEVICE_NOTIFY_IND", "device->host", "Device notification"),
        (0x4F03, "FWU_UPDATE_REQ", "host->device", "Start firmware update"),
        (0x4F04, "FWU_UPDATE_CFM", "device->host", "Update confirmation"),
        (0x4F05, "FWU_UPDATE_IND", "device->host", "Update progress indicator"),
        (0x4F06, "FWU_UPDATE_RES", "device->host", "Update result"),
        (0x4F07, "FWU_GET_BLOCK_IND", "device->host", "Request firmware block"),
        (0x4F08, "FWU_GET_BLOCK_RES", "host->device", "Send firmware block"),
        (0x4F09, "FWU_GET_CRC_IND", "device->host", "Request CRC check"),
        (0x4F0A, "FWU_GET_CRC_RES", "host->device", "CRC result"),
        (0x4F0B, "FWU_COMPLETE_IND", "device->host", "Update complete"),
        (0x4F0C, "FWU_STATUS_IND", "device->host", "Status notification"),
        (0x4F0D, "FWU_MULTI_CRC_IND", "device->host", "Multi-region CRC request"),
        (0x4F0E, "FWU_MULTI_CRC_RES", "host->device", "Multi-region CRC result"),
        (0x4F10, "FWU_SET_FEATURES_REQ", "host->device", "Set features"),
        (0x4F11, "FWU_SET_FEATURES_CFM", "device->host", "Set features confirmation"),
        (0x4F12, "FWU_GET_FEATURES_REQ", "host->device", "Get features"),
        (0x4F13, "FWU_GET_FEATURES_CFM", "device->host", "Get features confirmation"),
        (0x4F14, "FWU_CRC32_IND", "device->host", "CRC32 request"),
        (0x4F15, "FWU_CRC32_RES", "host->device", "CRC32 result"),
    ]

    print("FWU (Firmware Update) Opcodes — Rtx channel, NOT SECOM")
    print("-" * 60)
    print(f"{'Opcode':<8} {'Name':<28} {'Direction':<16} Transport")
    print("-" * 60)

    for opcode, name, direction, _description in fwu_opcodes:
        # FWU never rides SECOM 04 00; it is an Rtx 64-byte 0x58 channel.
        print(f"0x{opcode:04X}   {name:<28} {direction:<16} Rtx")

    print()
    print("Notes:")
    print("  - The FWU family travels on the Rtx datagram channel (64-byte")
    print("    reports, byte 0 = 0x58, 0xEE-padded).")
    print("  - Sending 0x4F* as SECOM 04 00 frames is the WRONG transport and")
    print("    is NAKed by the dongle; no '0x4F00 FWU_ENABLE_REQ' will ever")
    print("    switch PIDs on this path.")
    print("  - Build reports with gsp670.protocol.rtx_fwu_packet() /")
    print("    rtx_fwu_enable() (deprecated make_fwu_frame() is SECOM-only).")

    # Try to query device for more info
    print()
    print("Device Communication Test (SECOM path only — demonstrates the NAK):")
    print("-" * 60)
    print("  FWU lives on the Rtx channel; these exchanges only show that the")
    print("  dongle does not serve FWU over SECOM 04 00.")

    try:
        with GSA70Device() as dev:
            # Try GET_FEATURES
            print("Testing 0x4F12 (GET_FEATURES_REQ) over SECOM...", end=" ")
            try:
                resp = dev.exchange(0x4F12, timeout_ms=1000)
                if resp.kind == 'nak':
                    print("NAK (expected — FWU is Rtx, not SECOM)")
                else:
                    print(f"ACK - payload: {resp.payload.hex()}")
            except CommunicationError as e:
                print(f"FAILED: {e}")

            # Try STATUS_IND
            print("Testing 0x4F0C (FWU_STATUS_IND request) over SECOM...", end=" ")
            dev.drain(0.2)  # Clear buffer
            dev.write(0x4F0C)  # SECOM form: does not trigger the Rtx channel
            time.sleep(0.5)
            notifications = dev.drain(0.5)
            if notifications:
                print(f"Received {len(notifications)} notification(s)")
                for i, n in enumerate(notifications):
                    print(f"  [{i+1}] opcode=0x{n.opcode:04X} kind={n.kind}")
            else:
                print("No notifications")

    except DeviceNotFoundError:
        print("  No device found")
    except DeviceError as e:
        print(f"  Error: {e}")

    return 0


def cmd_events(args):
    """Show raw HID events (similar to dongle-listener.py)."""
    count = args.count

    print("GSP 670 Raw HID Event Monitor")
    print("=" * 60)
    if count:
        print(f"Will show {count} events then exit")
    else:
        print("Press Ctrl+C to exit")
    print("Showing all raw HID data received from device")
    print()

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        print("\n\nStopping monitor...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    try:
        with GSA70Device() as dev:
            print(f"Monitoring device: {dev.info.product_string or 'GSA 70'}")
            print(f"Path: {dev.info.path}")
            print("-" * 60)

            event_count = 0
            last_event_time = time.time()
            seen_events = set()

            # Send wakeup to ensure dongle is responsive
            print("Sending wakeup bursts...")
            for _ in range(3):
                try:
                    dev.write(0x4F12, b'\x01\x00')
                except Exception:
                    pass
                time.sleep(0.1)
            dev.drain(0.3)
            print()

            while running:
                # Read with short timeout
                raw = dev.read(timeout_ms=100)

                if raw:
                    event_count += 1
                    now = time.time()
                    elapsed = now - last_event_time
                    last_event_time = now

                    # Show frame details
                    print(f"\n[{elapsed:.3f}s] Event #{event_count}:")
                    print(f"  opcode=0x{raw.opcode:04X} kind={raw.kind}")
                    print(f"  marker={raw.marker.hex()} size={raw.size}")
                    print(f"  payload ({len(raw.payload)} bytes): {raw.payload.hex()}")
                    print(f"  full frame: {bytes(raw).hex()}")

                    # Decode device -> host event keys (Phase 3)
                    decoded_event = format_event_key(raw.payload)
                    if decoded_event:
                        print(f"  -> Event: {decoded_event}")

                    # Track unique events
                    event_key = (raw.opcode, raw.kind, raw.payload[:4].hex())
                    if event_key not in seen_events:
                        seen_events.add(event_key)
                        print("  ** NEW event type **")

                    # Check if we've collected enough events
                    if count and event_count >= count:
                        print(f"\n\nCollected {event_count} events as requested.")
                        running = False
                        break

                time.sleep(0.01)  # Small sleep to prevent CPU spinning

            print(f"\n\nTotal events: {event_count}")
            print(f"Unique event types: {len(seen_events)}")

    except DeviceNotFoundError:
        print("Error: Dongle not found.")
        return 1
    except DeviceError as e:
        print(f"Error: {e}")
        return 1

    return 0


def cmd_test_audio(args):
    """Run full-duplex audio test."""
    import os
    import subprocess
    import sys

    print("GSP 670 Audio Test - Full-Duplex")
    print("=" * 60)
    print()

    # Find GSP 670 audio card
    gsp_card = None
    try:
        result = subprocess.run(
            ['aplay', '-l'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'G670' in line or 'USB Audio' in line:
                # Extract card number
                if 'card' in line.lower():
                    parts = line.split(':')[0].split()
                    for p in parts:
                        if p.isdigit():
                            gsp_card = int(p)
                            print(f"Found GSP 670 audio on card {gsp_card}")
                            break
                if gsp_card is not None:
                    break
    except Exception as e:
        print(f"Error detecting audio devices: {e}")

    if gsp_card is None:
        print("GSP 670 audio device not found")
        print("Make sure the headset is connected via USB")
        return 1

    playback_device = f'hw:{gsp_card},0'
    capture_device = f'hw:{gsp_card},0'

    # Import and run the full-duplex test
    # __file__ is src/gsp670/cli.py, project root is 2 levels up
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    test_file = os.path.join(project_root, 'tests', 'hardware', 'test_full_duplex.py')

    if not os.path.exists(test_file):
        print(f"Error: Full-duplex test not found at {test_file}")
        return 1

    # Run the test as a subprocess
    result = subprocess.run(
        [sys.executable, test_file,
         '--playback-device', playback_device,
         '--capture-device', capture_device,
         '--playback-rate', '48000',
         '--capture-rate', '16000',
         '--duration', '3.0'],
        capture_output=False  # Show output in real-time
    )

    return result.returncode


def cmd_log(args):
    """Set logging level and show log messages."""
    import importlib
    importlib.reload(logging)  # Ensure fresh logging configuration

    log_level = getattr(logging, args.level.upper(), None)
    if log_level is None:
        print(f"Error: Unknown log level '{args.level}'")
        print("Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return 1

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set gsp670 module loggers
    gsp_logger = logging.getLogger('gsp670')
    gsp_logger.setLevel(log_level)

    print(f"Logging level set to {args.level.upper()}")

    if args.message:
        # Just log a test message
        gsp_logger.debug("Debug message")
        gsp_logger.info("Info message")
        gsp_logger.warning("Warning message")
        gsp_logger.error("Error message")
    else:
        print("\nTest messages logged (check above for your level):")
        print("  DEBUG - Debug message")
        print("  INFO - Info message")
        print("  WARNING - Warning message")
        print("  ERROR - Error message")

    return 0


def main(argv=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="EPOS|Sennheiser GSP 670 Control Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gsp670 info              Show device information
  gsp670 status            Show current status
  gsp670 controls list     List available controls
  gsp670 controls get volume  Get volume level
  gsp670 battery           Show battery status
  gsp670 monitor           Monitor control events
        """
    )

    parser.add_argument(
        '-d', '--device',
        choices=['auto', 'dongle', 'headset'],
        default='auto',
        help='Device to use (default: auto)'
    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s 0.1.0'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # info command
    info_parser = subparsers.add_parser('info', help='Show device information')
    info_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # status command
    status_parser = subparsers.add_parser('status', help='Show current headset status')
    status_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # controls subcommands
    controls_parser = subparsers.add_parser('controls', help='Control operations')
    controls_subparsers = controls_parser.add_subparsers(dest='subcommand', help='Control subcommands')

    controls_subparsers.add_parser('list', help='List available controls')

    get_parser = controls_subparsers.add_parser('get', help='Get control value')
    get_parser.add_argument('control', help='Control name (volume, mute, sidetone)')

    set_parser = controls_subparsers.add_parser('set', help='Set control value')
    set_parser.add_argument('control', help='Control name')
    set_parser.add_argument('value', help='New value')

    controls_subparsers.add_parser('restore', help='Restore settings from config')

    # battery command
    battery_parser = subparsers.add_parser('battery', help='Show battery status')
    battery_parser.add_argument('--json', action='store_true', help='Output as JSON')

    # monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor control events')
    monitor_parser.add_argument(
        '--watch', '-w',
        choices=['all', 'battery', 'link'],
        default='all',
        help='Event watch mode: show only specific event types '
             '(default: all events are shown)')
    monitor_parser.add_argument(
        '--timeout', '-t',
        type=float,
        default=0,
        help='Run for N seconds then exit (0 = run forever, default: 0)')

    # protocol inspect command
    protocol_parser = subparsers.add_parser('protocol', help='Protocol inspection commands')
    protocol_subparsers = protocol_parser.add_subparsers(dest='subcommand', help='Protocol subcommands')
    protocol_subparsers.add_parser('inspect', help='Show all known opcodes and status')

    # events command
    events_parser = subparsers.add_parser('events', help='Show raw HID events')
    events_parser.add_argument('--count', type=int, default=None,
                               help='Number of events to capture then exit')

    # log command
    log_parser = subparsers.add_parser('log', help='Set logging level')
    log_parser.add_argument('--level', '-l', default='INFO',
                           choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                           help='Log level (default: INFO)')
    log_parser.add_argument('--message', '-m', action='store_true',
                           help='Show a test message at each level')

    # test command
    test_parser = subparsers.add_parser('test', help='Test operations')
    test_subparsers = test_parser.add_subparsers(dest='subcommand', help='Test subcommands')
    test_subparsers.add_parser('audio', help='Run comprehensive audio tests')

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Dispatch to command handlers
    if args.command == 'info':
        return cmd_info(args)
    elif args.command == 'status':
        return cmd_status(args)
    elif args.command == 'controls':
        if args.subcommand == 'list':
            return cmd_controls_list(args)
        elif args.subcommand == 'get':
            return cmd_controls_get(args)
        elif args.subcommand == 'set':
            return cmd_controls_set(args)
        elif args.subcommand == 'restore':
            return cmd_controls_restore(args)
        else:
            controls_parser.print_help()
            return 1
    elif args.command == 'battery':
        return cmd_battery(args)
    elif args.command == 'monitor':
        return cmd_monitor(args)
    elif args.command == 'protocol':
        if args.subcommand == 'inspect':
            return cmd_protocol_inspect(args)
        else:
            protocol_parser.print_help()
            return 1
    elif args.command == 'events':
        return cmd_events(args)
    elif args.command == 'log':
        return cmd_log(args)
    elif args.command == 'test':
        if args.subcommand == 'audio':
            return cmd_test_audio(args)
        else:
            test_parser.print_help()
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
