#!/usr/bin/env python3
"""
Device discovery for EPOS|Sennheiser GSP 670 and GSA 70 devices.

Provides functions to find and enumerate HID and audio devices.
"""

from __future__ import annotations

import re
import subprocess

from ._compat import require_hid
from .device import DeviceInfo
from .protocol import PID_GSA70, PID_GSP670, PIDS_UPGRADE, USAGE, USAGE_PAGE, VID


def find_devices() -> list[DeviceInfo]:
    """
    Find all EPOS|Sennheiser devices.

    Returns:
        List of DeviceInfo for all discovered devices (deduplicated by path)
    """
    devices = []
    seen_paths = set()

    # Enumerate all EPOS VID devices
    hid = require_hid()
    for d in hid.enumerate(VID, 0):
        path = d.get('path')
        if path and path in seen_paths:
            continue  # Skip duplicate interfaces
        if path:
            seen_paths.add(path)

        info = _parse_device_info(d)

        # Classify device type
        if info.pid == PID_GSA70:
            info.is_dongle = True
        elif info.pid == PID_GSP670:
            info.is_headset = True
        elif info.pid in PIDS_UPGRADE:
            # Upgrade mode device
            pass

        devices.append(info)

    return devices


def _parse_device_info(d: dict) -> DeviceInfo:
    """Parse hidapi enumeration dict to DeviceInfo."""
    return DeviceInfo(
        vid=d.get('vendor_id', 0),
        pid=d.get('product_id', 0),
        path=d.get('path'),
        serial=d.get('serial'),
        product_string=d.get('product'),
        manufacturer_string=d.get('manufacturer'),
        usage_page=d.get('usage_page', 0),
        usage=d.get('usage', 0),
        interface=d.get('interface_number', -1)
    )


def enumerate_hid() -> list[DeviceInfo]:
    """
    Enumerate all HID interfaces for EPOS devices.

    Returns:
        List of DeviceInfo for HID interfaces
    """
    devices = []

    hid = require_hid()
    for d in hid.enumerate(VID, 0):
        # Check if it's the vendor usage page (Capricorn interface)
        if d['usage_page'] == USAGE_PAGE and d['usage'] == USAGE:
            info = _parse_device_info(d)
            devices.append(info)

    return devices


def enumerate_audio() -> list[dict]:
    """
    Enumerate ALSA audio devices using aplay/arecord.

    Returns:
        List of dicts with 'card', 'name', 'id', 'device', 'subdevice', 'type'
    """
    devices = []

    # Get playback devices (speakers/headphones)
    try:
        result = subprocess.run(
            ['aplay', '-l'],
            capture_output=True, text=True, timeout=5
        )
        devices.extend(_parse_alsa_output(result.stdout, 'playback'))
    except Exception:
        pass

    # Get capture devices (microphones)
    try:
        result = subprocess.run(
            ['arecord', '-l'],
            capture_output=True, text=True, timeout=5
        )
        devices.extend(_parse_alsa_output(result.stdout, 'capture'))
    except Exception:
        pass

    return devices


def _parse_alsa_output(output: str, device_type: str) -> list[dict]:
    """
    Parse aplay/arecord output.

    Output format:
        card 4: G670 [G670], device 0: USB Audio [USB Audio]
          Subdevice: 0/1
          Subdevice #1: subdevice #1

    Returns:
        List of device dicts
    """
    devices = []
    current_card = None

    for line in output.strip().split('\n'):
        # Card line
        m = re.match(r'card (\d+): (\S+)\s+\[(.+?)\](?:,\s+device (\d+):)?', line)
        if m:
            current_card = {
                'card': int(m.group(1)),
                'name': m.group(2),
                'id': m.group(3),
                'device': int(m.group(4)) if m.group(4) else 0,
                'type': device_type
            }
            continue

        # Subdevice line
        if current_card and 'Subdevice' in line:
            m = re.search(r'Subdevice #(\d+)', line)
            if m:
                current_card['subdevice'] = int(m.group(1))
            devices.append(current_card.copy())
            current_card = None

    return devices


def find_hid_device(pid: int = PID_GSA70, usage_page: int = USAGE_PAGE,
                     usage: int = USAGE) -> DeviceInfo | None:
    """
    Find a specific HID device by PID and usage.

    Args:
        pid: Product ID to find
        usage_page: HID usage page
        usage: HID usage

    Returns:
        DeviceInfo or None if not found
    """
    hid = require_hid()
    for d in hid.enumerate(VID, pid):
        if d['usage_page'] == usage_page and d['usage'] == usage:
            return _parse_device_info(d)
    return None


def find_dongle() -> DeviceInfo | None:
    """
    Find the GSA 70 dongle.

    Returns:
        DeviceInfo for dongle or None
    """
    return find_hid_device(PID_GSA70)


def find_headset() -> DeviceInfo | None:
    """
    Find the GSP 670 headset.

    Returns:
        DeviceInfo for headset or None
    """
    return find_hid_device(PID_GSP670)


def get_device_path(dev: DeviceInfo) -> str | None:
    """
    Get the /dev/hidraw* path for a device.

    Args:
        dev: DeviceInfo

    Returns:
        Device path string or None
    """
    if dev.path:
        # The path from hidapi is bytes that can be decoded
        if isinstance(dev.path, bytes):
            return dev.path.decode('utf-8')
        return dev.path

    # Try to find it again
    found = find_hid_device(dev.pid)
    return found.path if found else None


def find_audio_card(name_substring: str = "G670") -> int | None:
    """
    Find ALSA card number by name substring.

    Args:
        name_substring: Substring to match in card name

    Returns:
        Card number or None
    """
    devices = enumerate_audio()
    for d in devices:
        if name_substring.lower() in d.get('name', '').lower():
            return d['card']
    return None


def print_devices(devices: list[DeviceInfo] | None = None) -> None:
    """
    Print discovered devices in a formatted table.

    Args:
        devices: List of DeviceInfo (calls find_devices() if None)
    """
    if devices is None:
        devices = find_devices()

    if not devices:
        print("No EPOS devices found.")
        return

    print(f"{'Type':<10} {'PID':>6} {'VID':>6} {'Path':<20} {'Product'}")
    print("-" * 70)

    for d in devices:
        dev_type = []
        if d.is_dongle:
            dev_type.append("Dongle")
        if d.is_headset:
            dev_type.append("Headset")
        if not dev_type:
            dev_type.append("Unknown")

        path_str = d.path.decode('utf-8') if isinstance(d.path, bytes) else (d.path or "")
        # Truncate long paths
        if len(path_str) > 20:
            path_str = "..." + path_str[-17:]

        print(f"{','.join(dev_type):<10} 0x{d.pid:04X}  0x{d.vid:04X}  {path_str:<20} {d.product_string or ''}")


def print_audio_devices() -> None:
    """Print discovered audio devices."""
    devices = enumerate_audio()

    if not devices:
        print("No audio devices found.")
        return

    print(f"{'Type':<10} {'Card':>5} {'Name':<15} {'ID'}")
    print("-" * 50)

    for d in devices:
        print(f"{d['type']:<10} {d['card']:>5} {d['name']:<15} {d.get('id', '')}")
