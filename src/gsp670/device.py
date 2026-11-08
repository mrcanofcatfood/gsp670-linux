#!/usr/bin/env python3
"""
Device abstraction for EPOS|Sennheiser GSP 670 and GSA 70 devices.

Provides high-level interface to HID communication with the headset and dongle.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

from ._compat import require_hid
from .events import (
    BatteryEvent,
    LinkEvent,
    SubDevicesEvent,
    parse_frame_event,
)
from .protocol import (
    MARKER_DEVICE,
    MARKER_HOST,
    PID_GSA70,
    PID_GSP670,
    RPT,
    USAGE,
    USAGE_PAGE,
    VID,
    Frame,
    SecomOpcode,
    classify,
    frame,
    secom_request,
    secom_value,
)


@dataclass
class DeviceInfo:
    """Information about a discovered device."""
    vid: int
    pid: int
    firmware_version: str | None = None
    path: str | None = None
    usage_page: int = 0
    usage: int = 0
    serial: str | None = None
    product_string: str | None = None
    manufacturer_string: str | None = None
    interface: int = -1
    is_dongle: bool = False
    is_headset: bool = False


class DeviceError(Exception):
    """Base exception for device errors."""
    pass


class DeviceNotFoundError(DeviceError):
    """Device was not found."""
    def __init__(self, message=None, device_type=None):
        if message is None:
            if device_type == 'dongle':
                message = (
                    "GSA 70 dongle not found. "
                    "Make sure the dongle is connected to a USB port. "
                    "Try running 'gsp670 info' to see detected devices."
                )
            elif device_type == 'headset':
                message = (
                    "GSP 670 headset not found. "
                    "Make sure the headset is connected via the USB dongle. "
                    "Try running 'gsp670 info' to see detected devices."
                )
            else:
                message = (
                    "No GSP 670 device found. "
                    "Is the headset/dongle connected? "
                    "Try running 'gsp670 info' to see detected devices."
                )
        super().__init__(message)
        self.device_type = device_type


class DeviceDisconnectedError(DeviceError):
    """Device was disconnected."""
    pass


class CommunicationError(DeviceError):
    """Communication error with device."""
    def __init__(self, message=None, opcode=None, timeout_ms=None):
        if message is None:
            if timeout_ms:
                message = (
                    f"Communication timeout ({timeout_ms}ms) waiting for device response. "
                    "Check device connection and try again. "
                    "If the issue persists, try a different USB port or cable."
                )
            else:
                message = "Communication error with device."
        super().__init__(message)
        self.opcode = opcode
        self.timeout_ms = timeout_ms


class GSP670Device:
    """
    GSP 670 headset device.

    Represents the headset HID interface (PID 0x008a).
    Typically accessed through the GSA 70 dongle, but can also be
    accessed directly when the headset is in device mode.
    """

    def __init__(self, path: str | None = None, device_info: DeviceInfo | None = None):
        """
        Initialize device handle.

        Args:
            path: HID device path (if not using device_info)
            device_info: DeviceInfo from discovery (optional)
        """
        self._dev: Any | None = None
        self._path = path
        self._info = device_info or DeviceInfo(
            vid=VID, pid=PID_GSP670, is_headset=True
        )
        self._connected = False
        self._read_callbacks: list[Callable[[Frame], None]] = []

    @property
    def info(self) -> DeviceInfo:
        """Get device information."""
        return self._info

    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self._connected

    def open(self) -> None:
        """Open the HID device."""
        if self._connected:
            return

        if self._path is None and self._info.path is None:
            # Try to find device
            hid = require_hid()
            for d in hid.enumerate(VID, PID_GSP670):
                if d['usage_page'] == USAGE_PAGE and d['usage'] == USAGE:
                    self._path = d['path']
                    self._update_info_from_enumeration(d)
                    break
            else:
                raise DeviceNotFoundError("GSP 670 headset not found", device_type='headset')

        try:
            hid = require_hid()
            self._dev = hid.device()
            self._dev.open_path(self._path.encode() if isinstance(self._path, str) else self._path)
            self._dev.set_nonblocking(True)
            self._connected = True
        except PermissionError as e:
            self._connected = False
            raise DeviceError(
                f"Permission denied accessing the device: {e}. "
                "Try adding your user to the 'audio' group: 'sudo usermod -aG audio $USER'. "
                "You may need to log out and back in for changes to take effect, "
                "or run the application with sudo for a quick test."
            ) from e
        except Exception as e:
            self._connected = False
            error_str = str(e).lower()
            if 'permission' in error_str or 'access' in error_str:
                raise DeviceError(
                    f"Permission denied: {e}. "
                    "Add your user to the 'audio' group: 'sudo usermod -aG audio $USER'. "
                    "Then log out and back in."
                ) from e
            raise DeviceError(f"Failed to open device: {e}") from e

    def close(self) -> None:
        """Close the HID device."""
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None
        self._connected = False

    def _update_info_from_enumeration(self, d: dict) -> None:
        """Update device info from hidapi enumeration."""
        self._info.path = d['path']
        self._info.serial = d.get('serial')
        self._info.product_string = d.get('product')
        self._info.manufacturer_string = d.get('manufacturer')
        self._info.usage_page = d.get('usage_page', 0)
        self._info.usage = d.get('usage', 0)
        self._info.interface = d.get('interface_number', -1)

    def write(self, opcode: int, payload: bytes = b'') -> int:
        """
        Send a Capricorn frame to the device.

        Args:
            opcode: Capricorn opcode
            payload: Payload bytes

        Returns:
            Number of bytes written

        Raises:
            DeviceDisconnectedError: If device is disconnected
            CommunicationError: If write fails
        """
        if not self._connected or not self._dev:
            raise DeviceDisconnectedError("Device not connected")

        data = frame(opcode, payload, MARKER_HOST)
        try:
            n = self._dev.write(data)
            if n < 0:
                raise CommunicationError(f"Write failed with code {n}")
            return n
        except OSError as e:
            raise DeviceDisconnectedError(f"Device disconnected: {e}") from e

    def read(self, timeout_ms: int = 100) -> Frame | None:
        """
        Read and parse a frame from the device.

        Args:
            timeout_ms: Read timeout in milliseconds

        Returns:
            Parsed Frame or None if no data available
        """
        if not self._connected or not self._dev:
            return None

        try:
            raw = self._dev.read(RPT + 1, timeout_ms)
        except OSError:
            return None

        if not raw:
            return None

        f = classify(bytes(raw))
        for cb in list(self._read_callbacks):
            try:
                cb(f)
            except Exception:
                pass
        return f

    def drain(self, seconds: float = 0.5) -> list[Frame]:
        """
        Drain all pending frames from the device.

        Args:
            seconds: Drain duration

        Returns:
            List of received frames
        """
        frames = []
        end = time.time() + seconds
        while time.time() < end:
            f = self.read(50)
            if f:
                frames.append(f)
        return frames

    def exchange(self, opcode: int, payload: bytes = b'',
                 timeout_ms: int = 500, retry: int = 3) -> Frame:
        """
        Send a frame and wait for a response.

        Args:
            opcode: Capricorn opcode
            payload: Payload bytes
            timeout_ms: Response timeout
            retry: Number of retries on communication error

        Returns:
            Response frame

        Raises:
            CommunicationError: If no response received
        """
        last_error = None
        for attempt in range(retry):
            try:
                # Drain any pending data
                self.drain(0.05)

                # Send request
                self.write(opcode, payload)

                # Wait for response
                end = time.time() + (timeout_ms / 1000)
                while time.time() < end:
                    f = self.read(timeout_ms=min(100, timeout_ms))
                    if f and f.kind in ('ack', 'nak'):
                        return f

                # No response
                last_error = CommunicationError(
                    f"No response to opcode 0x{opcode:04X} after {timeout_ms}ms. "
                    "Check device connection. Try pressing a button on the headset to wake it.",
                    opcode=opcode,
                    timeout_ms=timeout_ms
                )
            except DeviceDisconnectedError:
                raise
            except CommunicationError as e:
                last_error = e
                if attempt < retry - 1:
                    time.sleep(0.1)

        raise last_error or CommunicationError(
            f"Failed to communicate with device after {retry} attempts. "
            "Try checking the device connection or using a different USB port."
        )

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor."""
        self.close()


    def add_read_callback(self, callback: Callable[[Frame], None]) -> None:
        """
        Register a callback invoked for every frame returned by :meth:`read`.

        Args:
            callback: ``fn(frame)`` — exceptions raised are swallowed.
        """
        self._read_callbacks.append(callback)

    def on_event(self, callback: Callable[[Frame], None]) -> None:
        """
        Register a callback invoked only for unsolicited event frames.

        Event frames have ``kind == 'event'`` (device→host markers ``00 01`` /
        ``ff 01``, opcode field ``0x0004``) — e.g. headset button presses.

        Args:
            callback: ``fn(frame)`` — exceptions raised are swallowed.
        """
        def _event_filter(f: Frame) -> None:
            if f.kind == 'event':
                callback(f)
        self._read_callbacks.append(_event_filter)

    def listen(self, seconds: float = 5.0):
        """
        Yield every frame received within ``seconds`` (events included).

        Args:
            seconds: Listening window.

        Yields:
            :class:`Frame` — each parsed frame, in arrival order.
        """
        end = time.time() + seconds
        while time.time() < end:
            f = self.read(50)
            if f is not None:
                yield f


class GSA70Device:
    """
    GSA 70 dongle device.

    Represents the dongle HID interface (PID 0x0300).
    This is the primary interface for communicating with the GSP 670 headset.
    """

    def __init__(self, path: str | None = None, device_info: DeviceInfo | None = None):
        """
        Initialize device handle.

        Args:
            path: HID device path (if not using device_info)
            device_info: DeviceInfo from discovery (optional)
        """
        self._dev: Any | None = None
        self._path = path
        self._info = device_info or DeviceInfo(
            vid=VID, pid=PID_GSA70, is_dongle=True
        )
        self._connected = False
        self._read_callbacks: list[Callable[[Frame], None]] = []

    @property
    def info(self) -> DeviceInfo:
        """Get device information."""
        return self._info

    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self._connected

    def open(self) -> None:
        """Open the HID device."""
        if self._connected:
            return

        if self._path is None and self._info.path is None:
            # Try to find device
            hid = require_hid()
            for d in hid.enumerate(VID, PID_GSA70):
                if d['usage_page'] == USAGE_PAGE and d['usage'] == USAGE:
                    self._path = d['path']
                    self._update_info_from_enumeration(d)
                    break
            else:
                raise DeviceNotFoundError("GSA 70 dongle not found", device_type='dongle')

        try:
            hid = require_hid()
            self._dev = hid.device()
            self._dev.open_path(self._path.encode() if isinstance(self._path, str) else self._path)
            self._dev.set_nonblocking(True)
            self._connected = True
        except PermissionError as e:
            self._connected = False
            raise DeviceError(
                f"Permission denied accessing the device: {e}. "
                "Try adding your user to the 'audio' group: 'sudo usermod -aG audio $USER'. "
                "You may need to log out and back in for changes to take effect, "
                "or run the application with sudo for a quick test."
            ) from e
        except Exception as e:
            self._connected = False
            error_str = str(e).lower()
            if 'permission' in error_str or 'access' in error_str:
                raise DeviceError(
                    f"Permission denied: {e}. "
                    "Add your user to the 'audio' group: 'sudo usermod -aG audio $USER'. "
                    "Then log out and back in."
                ) from e
            raise DeviceError(f"Failed to open device: {e}") from e

    def close(self) -> None:
        """Close the HID device."""
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None
        self._connected = False

    def _update_info_from_enumeration(self, d: dict) -> None:
        """Update device info from hidapi enumeration."""
        self._info.path = d['path']
        self._info.serial = d.get('serial')
        self._info.product_string = d.get('product')
        self._info.manufacturer_string = d.get('manufacturer')
        self._info.usage_page = d.get('usage_page', 0)
        self._info.usage = d.get('usage', 0)
        self._info.interface = d.get('interface_number', -1)

    def write(self, opcode: int, payload: bytes = b'') -> int:
        """
        Send a Capricorn frame to the device.

        Args:
            opcode: Capricorn opcode
            payload: Payload bytes

        Returns:
            Number of bytes written

        Raises:
            DeviceDisconnectedError: If device is disconnected
            CommunicationError: If write fails
        """
        if not self._connected or not self._dev:
            raise DeviceDisconnectedError("Device not connected")

        data = frame(opcode, payload, MARKER_HOST)
        try:
            n = self._dev.write(data)
            if n < 0:
                raise CommunicationError(f"Write failed with code {n}")
            return n
        except OSError as e:
            raise DeviceDisconnectedError(f"Device disconnected: {e}") from e

    def read(self, timeout_ms: int = 100) -> Frame | None:
        """
        Read and parse a frame from the device.

        Args:
            timeout_ms: Read timeout in milliseconds

        Returns:
            Parsed Frame or None if no data available
        """
        if not self._connected or not self._dev:
            return None

        try:
            raw = self._dev.read(RPT + 1, timeout_ms)
        except OSError:
            return None

        if not raw:
            return None

        f = classify(bytes(raw))
        for cb in list(self._read_callbacks):
            try:
                cb(f)
            except Exception:
                pass
        return f

    def drain(self, seconds: float = 0.5) -> list[Frame]:
        """
        Drain all pending frames from the device.

        Args:
            seconds: Drain duration

        Returns:
            List of received frames
        """
        frames = []
        end = time.time() + seconds
        while time.time() < end:
            f = self.read(50)
            if f:
                frames.append(f)
        return frames

    def exchange(self, opcode: int, payload: bytes = b'',
                 timeout_ms: int = 500, retry: int = 3) -> Frame:
        """
        Send a frame and wait for a response.

        Args:
            opcode: Capricorn opcode
            payload: Payload bytes
            timeout_ms: Response timeout
            retry: Number of retries on communication error

        Returns:
            Response frame

        Raises:
            CommunicationError: If no response received
        """
        last_error = None
        for attempt in range(retry):
            try:
                # Drain any pending data
                self.drain(0.05)

                # Send request
                self.write(opcode, payload)

                # Wait for response
                end = time.time() + (timeout_ms / 1000)
                while time.time() < end:
                    f = self.read(timeout_ms=min(100, timeout_ms))
                    if f and f.kind in ('ack', 'nak'):
                        return f

                # No response
                last_error = CommunicationError(
                    f"No response to opcode 0x{opcode:04X} after {timeout_ms}ms. "
                    "Check device connection. Try pressing a button on the headset to wake it.",
                    opcode=opcode,
                    timeout_ms=timeout_ms
                )
            except DeviceDisconnectedError:
                raise
            except CommunicationError as e:
                last_error = e
                if attempt < retry - 1:
                    time.sleep(0.1)

        raise last_error or CommunicationError(
            f"Failed to communicate with device after {retry} attempts. "
            "Try checking the device connection or using a different USB port."
        )

    def add_read_callback(self, callback: Callable[[Frame], None]) -> None:
        """
        Register a callback invoked for every frame returned by :meth:`read`.

        Args:
            callback: ``fn(frame)`` — exceptions raised are swallowed.
        """
        self._read_callbacks.append(callback)

    def on_event(self, callback: Callable[[Frame], None]) -> None:
        """
        Register a callback invoked only for unsolicited event frames.

        Event frames have ``kind == 'event'`` (device→host markers ``00 01`` /
        ``ff 01``, opcode field ``0x0004``) — e.g. headset button presses
        arriving over the RF link. See ``docs/verified-secom-opcodes.md`` §5.2.

        Args:
            callback: ``fn(frame)`` — exceptions raised are swallowed.
        """
        def _event_filter(f: Frame) -> None:
            if f.kind == 'event':
                callback(f)
        self._read_callbacks.append(_event_filter)

    def listen(self, seconds: float = 5.0):
        """
        Yield every frame received within ``seconds`` (events included).

        Args:
            seconds: Listening window.

        Yields:
            :class:`Frame` — each parsed frame, in arrival order.
        """
        end = time.time() + seconds
        while time.time() < end:
            f = self.read(50)
            if f is not None:
                yield f

    def secom_exchange(self, opcode: int, value: int | None = None,
                       timeout_ms: int = 1000) -> Frame | None:
        """
        Send a verified Capricorn/SECOM command and return the reply.

        Unlike :meth:`exchange`, this accepts *data* replies as well as link
        ACKs. A data reply has marker ``04 00``, opcode ``0x0000`` and a payload
        that echoes the 4-byte request header followed by the value bytes
        (use :func:`gsp670.protocol.secom_value`). A link ACK has marker
        ``05 30`` and echoes the request payload.

        Args:
            opcode: A :class:`gsp670.protocol.SecomOpcode` value.
            value: Value byte for the writable opcodes.
            timeout_ms: Response timeout.

        Returns:
            The first data reply if one arrives, otherwise the link ACK, or
            ``None`` on timeout.
        """
        if not self._connected or not self._dev:
            raise DeviceDisconnectedError("Device not connected")

        payload = secom_request(opcode, value)
        self.drain(0.05)
        self.write(opcode, payload)

        ack: Frame | None = None
        end = time.time() + (timeout_ms / 1000)
        while time.time() < end:
            f = self.read(timeout_ms=100)
            if f is None:
                continue
            if f.marker == MARKER_DEVICE or f.kind in ('other', 'subreply'):
                # A device data reply (marker 04 00, class 0x0000 or 0x0004).
                if len(f.payload) > 4:
                    return f
            if f.kind in ('ack', 'nak'):
                if f.kind == 'nak':
                    return f
                ack = ack or f
        return ack

    def get_firmware_version(self) -> str | None:
        """Return the device firmware version, e.g. ``'3.14.2'``."""
        f = self.secom_exchange(SecomOpcode.GET_FW_VERSION)
        if f is None:
            return None
        v = secom_value(f)
        if len(v) < 6:
            return None
        major, minor, patch = (int.from_bytes(v[i:i + 2], 'little')
                               for i in (0, 2, 4))
        return f"{major}.{minor}.{patch}"

    def get_serial_number(self) -> str | None:
        """Return the serial number (ASCII, NUL padded)."""
        f = self.secom_exchange(SecomOpcode.GET_SERIAL_NO)
        if f is None:
            return None
        return secom_value(f).split(b'\x00', 1)[0].decode('ascii', 'replace') or None

    def get_device_name(self) -> str | None:
        """Return the device name (UTF-16LE), e.g. ``'EPOS GSA 70'``."""
        f = self.secom_exchange(SecomOpcode.GET_DEVICE_NAME)
        if f is None:
            return None
        raw = secom_value(f)
        # The name is UTF-16LE, NUL-terminated on a 2-byte boundary.
        chars = bytearray()
        for i in range(0, len(raw) - 1, 2):
            if raw[i] == 0 and raw[i + 1] == 0:
                break
            chars += raw[i:i + 2]
        return chars.decode('utf-16-le', 'replace') or None

    def get_device_address(self) -> bytes | None:
        """Return the raw Bluetooth/device address blob."""
        f = self.secom_exchange(SecomOpcode.GET_DEVICE_ADDRESS)
        return None if f is None else secom_value(f)

    def get_subdevices_connected(self) -> int | None:
        """Return the number of connected sub-devices (headset link status)."""
        f = self.secom_exchange(SecomOpcode.GET_SUBDEVICES_CONNECTED)
        if f is None:
            return None
        v = secom_value(f)
        return int.from_bytes(v[:2], 'little') if len(v) >= 2 else None

    def get_battery_percentage(self) -> int | None:
        """
        Return the headset battery percentage, or ``None``.

        Requires the headset to be powered on and linked to the dongle;
        otherwise the dongle only returns a link ACK. The value is read from
        ``payload[4] | payload[5]`` of the ``0x0e`` data reply.

        Note that the device does not answer this query with a percentage in
        practice; see ``docs/limitations.md`` for why.
        """
        f = self.secom_exchange(SecomOpcode.GET_BATTERY_PERCENTAGE)
        if f is None:
            return None
        v = secom_value(f)
        if not v:
            return None
        return (v[0] | (v[1] if len(v) > 1 else 0)) & 0xFF

    def get_sidetone(self) -> int | None:
        """Return the sidetone level (requires a linked headset)."""
        f = self.secom_exchange(SecomOpcode.GET_SIDETONE)
        if f is None:
            return None
        v = secom_value(f)
        return v[0] if v else None

    def set_sidetone(self, level: int) -> bool:
        """Set the sidetone level (0-255)."""
        f = self.secom_exchange(SecomOpcode.SET_SIDETONE, value=int(level) & 0xFF)
        return f is not None and f.kind != 'nak'

    def get_noise_reduction(self) -> int | None:
        """Return the noise-reduction level (requires a linked headset)."""
        f = self.secom_exchange(SecomOpcode.GET_NOISE_REDUCTION)
        if f is None:
            return None
        v = secom_value(f)
        return v[0] if v else None

    def set_noise_reduction(self, level: int) -> bool:
        """Set the noise-reduction level (0-255)."""
        f = self.secom_exchange(SecomOpcode.SET_NOISE_REDUCTION, value=int(level) & 0xFF)
        return f is not None and f.kind != 'nak'

    def get_latency(self) -> int | None:
        """Return the audio latency level (requires a linked headset)."""
        f = self.secom_exchange(SecomOpcode.GET_LATENCY)
        if f is None:
            return None
        v = secom_value(f)
        return v[0] if v else None

    def get_auto_power_off(self) -> int | None:
        """Return the auto-power-off timer status."""
        f = self.secom_exchange(SecomOpcode.GET_AUTO_POWER_OFF)
        if f is None:
            return None
        v = secom_value(f)
        return v[0] if v else None

    def set_auto_power_off(self, level: int) -> bool:
        """Set the auto-power-off timer."""
        f = self.secom_exchange(SecomOpcode.SET_AUTO_POWER_OFF, value=int(level) & 0xFF)
        return f is not None and f.kind != 'nak'

    def get_feature(self, feature_index: int, timeout_ms: int = 500) -> bytes:
        """
        DEPRECATED / INVALID - do not use.

        This sent a ``FWU_GET_FEATURES_REQ`` (0x4F12) with a guessed feature
        index. That command does not carry per-control indices, and the
        ``FeatureIndex`` values are fabricated. Use the verified SECOM methods
        (:meth:`get_sidetone`, :meth:`get_battery_percentage`, ...).
        """
        raise NotImplementedError(
            "get_feature() was based on fabricated FeatureIndex values. "
            "Use the verified SECOM methods (get_sidetone(), "
            "get_battery_percentage(), ...) instead."
        )

    def set_feature(self, feature_index: int, data: bytes = b'',
                    timeout_ms: int = 500) -> bool:
        """
        DEPRECATED / INVALID - do not use.

        See :meth:`get_feature`. Use the verified SECOM setters
        (:meth:`set_sidetone`, :meth:`set_noise_reduction`,
        :meth:`set_auto_power_off`) instead.
        """
        raise NotImplementedError(
            "set_feature() was based on fabricated FeatureIndex values. "
            "Use the verified SECOM setters (set_sidetone(), "
            "set_noise_reduction(), set_auto_power_off()) instead."
        )

    def get_volume(self) -> int:
        """
        Get master volume level.

        Volume is an operating-system / USB Audio Class control (ALSA,
        PipeWire, ``AudioEndpointVolume`` on Windows), not a SECOM/HID device
        command. There is no device-side volume register to read.

        Returns:
            Always -1 (unknown); use the OS mixer instead.
        """
        return -1

    def set_volume(self, volume: int) -> bool:
        """
        Set master volume level.

        Volume is an OS / USB Audio Class control, not a SECOM command. This
        method is intentionally a no-op; use the OS mixer (ALSA/PipeWire).

        Returns:
            False (not a device command).
        """
        return False

    def get_mic_gain(self) -> int:
        """
        Get microphone gain level.

        Mic gain is a software APO parameter on Windows (``SennCom\\SCAPO``),
        not a SECOM/HID device command.

        Returns:
            Always -1 (unknown).
        """
        return -1

    def set_mic_gain(self, gain: int) -> bool:
        """
        Set microphone gain level.

        Mic gain is a software APO parameter, not a SECOM command. No-op.

        Returns:
            False (not a device command).
        """
        return False

    def get_reverb(self) -> int:
        """
        Get reverb level.

        Reverb is a software APO parameter on Windows, not a SECOM command.

        Returns:
            Always -1 (unknown).
        """
        return -1

    def set_reverb(self, level: int) -> bool:
        """
        Set reverb level.

        Reverb is a software APO parameter, not a SECOM command. No-op.

        Returns:
            False (not a device command).
        """
        return False

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor."""
        self.close()

    # ------------------------------------------------------------------
    # Async event generators
    #
    # Events arrive via push from the linked headset/dongle. There is
    # NO subscription handshake — the GSA 70 emits events unconditionally once
    # the headset is linked. These generators passively poll the read loop and
    # yield parsed events. Battery events appear only when the headset is
    # actively linked; link events appear when the RF connection changes.
    # ------------------------------------------------------------------

    async def watch_events(
        self,
        timeout: float = 0.0,
    ):
        """
        Async generator: yields all parsed device-to-host events.

        Polls the device every 100 ms and yields each parsed event dataclass
        (see :mod:`gsp670.events`). Callers can filter for specific types.

        Args:
            timeout: Maximum seconds to run. 0 = run forever (until the
                device is closed).

        Yields:
            Event dataclass instances from :mod:`gsp670.events`:
            - :class:`BatteryEvent` — battery level / charging
            - :class:`LinkEvent` — headset link state changes
            - :class:`SidetoneEvent`, :class:`ANCStateEvent`, etc.

        Raises:
            DeviceDisconnectedError: if the device is not open.

        Example:
            async for event in dev.watch_events(timeout=30):
                print(type(event).__name__, event)
        """
        if not self._connected or not self._dev:
            raise DeviceDisconnectedError("Device not connected")

        deadline = time.time() + timeout if timeout > 0 else None
        while True:
            f = self.read(50)
            if f is not None:
                evt = parse_frame_event(f)
                if evt is not None:
                    yield evt
            await asyncio.sleep(0.1)
            if deadline is not None and time.time() >= deadline:
                break

    async def watch_battery(
        self,
        timeout: float = 0.0,
    ):
        """
        Async generator: yields :class:`BatteryEvent` from the linked headset.

        Battery events are pushed by the dongle when the headset's battery state
        changes (level crossing, charger connect/disconnect). They arrive only
        when the headset is actively linked to the dongle.

        Args:
            timeout: Maximum seconds. 0 = run forever.

        Yields:
            :class:`BatteryEvent` — ``level`` (0-100 %) and ``charging_changed``.

        Raises:
            DeviceDisconnectedError: if the device is not open.
        """
        async for evt in self.watch_events(timeout=timeout):
            if isinstance(evt, BatteryEvent):
                yield evt

    async def watch_link(
        self,
        timeout: float = 0.0,
    ):
        """
        Async generator: yields link-state events when the headset links/unlinks.

        The dongle emits ``Service_Events_SubDevicesChanged`` (as
        :class:`SubDevicesEvent`, ``count`` = number of linked sub-devices) and
        ``Device_ConnectionEvents_ConnectionStatus`` (as :class:`LinkEvent`,
        raw ``status`` u16 — value semantics not yet documented) when a headset
        joins or leaves the DECT link.

        Args:
            timeout: Maximum seconds. 0 = run forever.

        Yields:
            :class:`SubDevicesEvent` — ``count > 0`` means a headset is linked.
            :class:`LinkEvent` — raw connection status ``status``.

        Raises:
            DeviceDisconnectedError: if the device is not open.
        """
        async for evt in self.watch_events(timeout=timeout):
            if isinstance(evt, (LinkEvent, SubDevicesEvent)):
                yield evt
