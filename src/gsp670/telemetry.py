#!/usr/bin/env python3
"""
Telemetry and status reporting for GSP 670 headset.

Provides dataclasses and functions for battery, link, and headset state.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from .protocol import Frame, Opcode


class BatteryLevel(IntEnum):
    """Battery level percentage."""
    CRITICAL = 10
    LOW = 20
    MEDIUM = 50
    HIGH = 80
    FULL = 100


class ChargingState(IntEnum):
    """Charging state."""
    NOT_CHARGING = 0
    CHARGING = 1
    FULL = 2
    ERROR = 3


class LinkQuality(IntEnum):
    """Wireless link quality."""
    NONE = 0
    POOR = 1
    FAIR = 2
    GOOD = 3
    EXCELLENT = 4


class HeadsetState(IntEnum):
    """Headset connection state."""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3


@dataclass
class BatteryState:
    """Battery status."""
    level: int = 0  # 0-100 percentage
    charging: ChargingState = ChargingState.NOT_CHARGING
    critical: bool = False
    low: bool = False

    def is_charging(self) -> bool:
        """Check if battery is currently charging."""
        return self.charging == ChargingState.CHARGING

    def is_full(self) -> bool:
        """Check if battery is fully charged."""
        return self.charging == ChargingState.FULL

    def is_critical(self) -> bool:
        """Check if battery level is critical (<10%)."""
        return self.level < BatteryLevel.CRITICAL or self.critical

    def is_low(self) -> bool:
        """Check if battery level is low (<20%)."""
        return self.level < BatteryLevel.LOW or self.low


@dataclass
class LinkState:
    """Wireless link status."""
    quality: LinkQuality = LinkQuality.NONE
    rssi: int = 0  # Received Signal Strength Indicator
    channel: int = 0
    hopping: bool = False

    def is_connected(self) -> bool:
        """Check if link is established."""
        return self.quality >= LinkQuality.FAIR


@dataclass
class HeadsetStatus:
    """Complete headset status."""
    battery: BatteryState = None
    link: LinkState = None
    firmware_version: Optional[str] = None
    dongle_firmware: Optional[str] = None
    headset_firmware: Optional[str] = None
    device_mode: str = "unknown"

    def __post_init__(self):
        if self.battery is None:
            self.battery = BatteryState()
        if self.link is None:
            self.link = LinkState()

    def is_connected(self) -> bool:
        """Check if headset is connected and operational."""
        return self.link.is_connected() and self.battery.level > 0


def parse_fwu_status_ind(frame: Frame) -> Optional[HeadsetStatus]:
    """
    Parse FWU_STATUS_IND (0x4F0C) notification into HeadsetStatus.

    .. warning::
        The FWU family travels on the **Rtx** channel (64-byte ``0x58``
        reports, ``0xEE``-padded). These notifications are **not** delivered
        as SECOM ``04 00`` ``Frame`` objects on the normal path; this parser
        only applies to a ``Frame`` already extracted from an Rtx report, and
        its payload layout was never confirmed by a live capture.

    The status notification format is device-specific and partially documented.
    The notification format includes:
    - Sequence/counter byte
    - Status byte(s)
    - Battery information
    - Link quality data

    Args:
        frame: Parsed Capricorn frame

    Returns:
        HeadsetStatus or None if parsing fails
    """
    if frame.opcode != Opcode.FWU_STATUS_IND:
        return None

    payload = frame.payload
    if len(payload) < 4:
        return None

    status = HeadsetStatus()

    # Try to parse status bytes
    # Note: The exact format of status notifications is not fully documented
    # This is a best-effort parser based on observed data

    # Sequence/counter byte at offset 0
    # Status byte at offset 1 (varies by device state)

    # Battery level (observed to be around byte 3-4 in some captures)
    # The byte at offset 4 changed between captures (0x10 vs 0xff)

    # Link quality indicator may be present in later bytes

    return status


def parse_device_notify_ind(frame: Frame) -> Optional[dict]:
    """
    Parse FWU_DEVICE_NOTIFY_IND (0x4F02) notification.

    .. warning::
        Same Rtx-channel caveat as :func:`parse_fwu_status_ind`: FWU
        notifications ride the 64-byte ``0x58`` Rtx reports, not SECOM
        ``04 00`` frames.

    Args:
        frame: Parsed Capricorn frame

    Returns:
        Dict with notification data or None
    """
    if frame.opcode != Opcode.FWU_DEVICE_NOTIFY_IND:
        return None

    payload = frame.payload
    if len(payload) < 2:
        return None

    # Sub-opcode/module selector at byte 1 (0xFE in observed data)
    # Data follows

    return {
        'sub_opcode': payload[0] if len(payload) > 0 else 0,
        'data': payload[1:]
    }


def format_battery_status(battery: BatteryState) -> str:
    """
    Format battery status as human-readable string.

    Args:
        battery: BatteryState

    Returns:
        Formatted string
    """
    level_str = f"{battery.level}%"

    if battery.is_charging():
        level_str += " (charging)"
    elif battery.is_full():
        level_str += " (full)"

    if battery.is_critical():
        level_str += " [CRITICAL]"
    elif battery.is_low():
        level_str += " [low]"

    return level_str


def format_link_status(link: LinkState) -> str:
    """
    Format link status as human-readable string.

    Args:
        link: LinkState

    Returns:
        Formatted string
    """
    quality_names = {
        LinkQuality.NONE: "No link",
        LinkQuality.POOR: "Poor",
        LinkQuality.FAIR: "Fair",
        LinkQuality.GOOD: "Good",
        LinkQuality.EXCELLENT: "Excellent"
    }

    status = quality_names.get(link.quality, "Unknown")

    if link.rssi != 0:
        status += f" (RSSI: {link.rssi} dBm)"

    return status


def format_headset_status(status: HeadsetStatus) -> str:
    """
    Format complete headset status as human-readable string.

    Args:
        status: HeadsetStatus

    Returns:
        Formatted multi-line string
    """
    lines = []

    lines.append("Headset Status")
    lines.append("-" * 40)

    lines.append(f"Connection: {status.device_mode}")

    if status.headset_firmware:
        lines.append(f"Headset FW: {status.headset_firmware}")

    if status.dongle_firmware:
        lines.append(f"Dongle FW: {status.dongle_firmware}")

    lines.append(f"Battery: {format_battery_status(status.battery)}")
    lines.append(f"Link: {format_link_status(status.link)}")

    return "\n".join(lines)
