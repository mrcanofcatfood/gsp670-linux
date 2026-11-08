#!/usr/bin/env python3
"""
Device controls for GSP 670 headset.

Provides control classes for volume, mute, sidetone, and other adjustments.
"""

from dataclasses import dataclass
from enum import IntEnum


class SecomControl(IntEnum):
    """
    Verified SECOM controls (alias of :class:`gsp670.protocol.SecomOpcode`).

    Kept here for discoverability; prefer importing from ``gsp670.protocol``.
    """
    GET_FW_VERSION = 0x00
    GET_SERIAL_NO = 0x01
    GET_DEVICE_NAME = 0x02
    GET_DEVICE_ADDRESS = 0x03
    GET_SUBDEVICES_CONNECTED = 0x04
    GET_DFU_TYPE = 0x06
    ENTER_DFU = 0x07
    GET_NESTED_DEVICE_BT_NAME = 0x0C
    GET_BATTERY_PERCENTAGE = 0x0E
    GET_SIDETONE = 0x10
    SET_SIDETONE = 0x11
    SET_NOISE_REDUCTION = 0x12
    GET_NOISE_REDUCTION = 0x13
    GET_NESTED_DEVICE_PID = 0x14
    SEND_LATENCY = 0x16
    GET_LATENCY = 0x17
    GET_REMOTE_DEVICE_INFO = 0x18
    GET_NBR_LINK_KEYS = 0x19
    SET_AUTO_POWER_OFF = 0x1A
    GET_AUTO_POWER_OFF = 0x1B


@dataclass
class VolumeControl:
    """
    Volume control (0-100).

    The GSP 670 has a volume wheel that generates HID notifications
    when adjusted.
    """
    value: int = 50  # 0-100
    min_value: int = 0
    max_value: int = 100

    def set(self, value: int) -> None:
        """
        Set volume level.

        Args:
            value: Volume level (0-100)

        Raises:
            ValueError: If value is out of range
        """
        if not self.min_value <= value <= self.max_value:
            raise ValueError(f"Volume must be between {self.min_value} and {self.max_value}")
        self.value = value

    def increment(self, delta: int = 1) -> int:
        """
        Increment volume by delta.

        Args:
            delta: Amount to increment (negative to decrement)

        Returns:
            New volume level
        """
        new_value = max(self.min_value, min(self.max_value, self.value + delta))
        self.value = new_value
        return new_value

    def is_muted(self) -> bool:
        """Check if volume is at minimum (effectively muted)."""
        return self.value == self.min_value


@dataclass
class MuteControl:
    """Mute control state."""
    muted: bool = False

    def toggle(self) -> bool:
        """
        Toggle mute state.

        Returns:
            New mute state
        """
        self.muted = not self.muted
        return self.muted

    def set(self, muted: bool) -> None:
        """
        Set mute state.

        Args:
            muted: True to mute, False to unmute
        """
        self.muted = muted


@dataclass
class SidetoneControl:
    """
    Sidetone control (0-100).

    Sidetone lets you hear your own voice in the headset.
    Not all firmwares support this.
    """
    value: int = 50  # 0-100
    min_value: int = 0
    max_value: int = 100
    supported: bool = True

    def set(self, value: int) -> None:
        """
        Set sidetone level.

        Args:
            value: Sidetone level (0-100)

        Raises:
            ValueError: If value is out of range or not supported
        """
        if not self.supported:
            raise NotImplementedError("Sidetone not supported on this device")
        if not self.min_value <= value <= self.max_value:
            raise ValueError(f"Sidetone must be between {self.min_value} and {self.max_value}")
        self.value = value

    def increment(self, delta: int = 1) -> int:
        """
        Increment sidetone by delta.

        Args:
            delta: Amount to increment

        Returns:
            New sidetone level
        """
        new_value = max(self.min_value, min(self.max_value, self.value + delta))
        self.value = new_value
        return new_value


@dataclass
class ControlsState:
    """Complete controls state."""
    volume: VolumeControl = None
    mute: MuteControl = None
    sidetone: SidetoneControl = None

    def __post_init__(self):
        if self.volume is None:
            self.volume = VolumeControl()
        if self.mute is None:
            self.mute = MuteControl()
        if self.sidetone is None:
            self.sidetone = SidetoneControl()


def volume_delta_to_level(delta: int, current: int = 50,
                          min_val: int = 0, max_val: int = 100) -> int:
    """
    Convert volume wheel delta to absolute level.

    Args:
        delta: Volume change (-32 to +32 typical)
        current: Current volume level
        min_val: Minimum value
        max_val: Maximum value

    Returns:
        New volume level
    """
    # The delta is typically small (1-5 per notch), so we scale it
    scaled_delta = delta // 4  # Reduce sensitivity
    new_level = max(min_val, min(max_val, current + scaled_delta))
    return new_level
