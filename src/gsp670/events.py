#!/usr/bin/env python3
"""
Event parsing for device->host notifications.

Provides dataclasses and parsers for the 22 device event types that the
headset and dongle emit unsolicited.

Event key format: ``<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]``
- word1 is NOT a uniform namespace: battery uses 0x000F, ANC 0x0007,
  speaker-mic 0x001D, device PDL 0x0029, default 0x00F0.
- Value bytes follow the key; their schema is in EVENT_PAYLOAD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .protocol import (
    EVENT_KEYS,
    EVENT_PAYLOAD,
    Frame,
    decode_event_key,
)

# ---------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------

@dataclass
class BatteryEvent:
    """Battery status event."""
    level: int  # 0-100 percentage
    charging_changed: int | None = None  # u16 charging state
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Battery_Events_Percentage'


@dataclass
class ChargingEvent:
    """Charging state change event."""
    state: int  # u16: 0=not charging, 1=charging, 2=full
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Battery_Events_ChargingChanged'


@dataclass
class SidetoneEvent:
    """Sidetone gain change event."""
    level: int  # u16: 0-255 sidetone level
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Sound_Events_SideToneGainChanged'


@dataclass
class ANCHearThroughEvent:
    """ANC HearThrough change event."""
    enabled: int  # u8: 0=off, 1=on
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'ANC_Events_HearThroughChanged'


@dataclass
class ANCLevelEvent:
    """ANC adaptive noise cancellation level change event."""
    level: int  # u16: ANC level
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'ANC_Events_AdaptiveNoiseCancelationLevelChanged'


@dataclass
class ANCStateEvent:
    """ANC state change event (two-word key form)."""
    state: int  # u16: ANC state
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'ANC_AdaptiveNoiseCancelationStateChanged'


@dataclass
class LinkEvent:
    """Device connection/link event."""
    status: int  # u16
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Device_ConnectionEvents_ConnectionStatus'


@dataclass
class SubDevicesEvent:
    """Sub-devices (headset link) change event."""
    count: int  # u16: number of linked sub-devices
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Service_Events_SubDevicesChanged'


@dataclass
class VolumeLimiterEvent:
    """Volume limiter mode change event."""
    mode: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Sound_Events_VolumeLimiterModeChanged'


@dataclass
class PcSoundPriorityEvent:
    """PC sound priority change event."""
    priority: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Sound_Events_PcSoundPriority'


@dataclass
class TalkWhileMuteEvent:
    """Speaker/mic talk-while-mute status event."""
    status: int  # u16
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'SpeakerMic_Events_TalkWhileMuteStatus'


@dataclass
class VirtualButtonEvent:
    """Virtual button press event."""
    # 4 x u8 fields from payload
    b0: int
    b1: int
    b2: int
    b3: int
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Input_Events_VirtualButtonEvent'


@dataclass
class MMIConfigEvent:
    """MMI configuration update event."""
    # 2 x u8 fields
    b0: int
    b1: int
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Input_Events_MMIConfigurationUpdate'


@dataclass
class AutoPowerOffTimerEvent:
    """Auto power off timer event."""
    value: int  # u16 timer value
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Service_Events_AutoPowerOffTimerValue'


@dataclass
class AutoPowerOffStatusEvent:
    """Auto power off status event."""
    status: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Service_Events_AutoPowerOffTimerStatus'


@dataclass
class ComponentStatusEvent:
    """Component status change event."""
    # u8 + u16 fields
    b0: int
    w0: int
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Component_Events_StatusChange'


@dataclass
class TonePromptEvent:
    """Audio prompt/tone mode change event."""
    mode: int  # u16
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Tone_AudioPromptsModeChanged'


@dataclass
class PairingStatusEvent:
    """Device pairing status change event."""
    status: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Device_ConnectionEvents_PairingStatusIndication'


@dataclass
class ConnectionChangeEvent:
    """Connection change event."""
    # 2 x u8 fields
    b0: int
    b1: int
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Device_ConnectionEvents_ConnectionChangeEvent'


@dataclass
class MultipointScoEvent:
    """Multipoint SCO status event."""
    status: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Device_ConnectionEvents_MultipointConnectionInScoStatus'


@dataclass
class SpeakerMicSettingEvent:
    """Speaker/mic optimized setting change event (two-word key)."""
    setting: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'SpeakerMic_OptimizedMicSettingChanged'


@dataclass
class PdlModeEvent:
    """Device PDL mode change event (two-word key)."""
    mode: int  # u8
    raw_payload: bytes = b''

    @property
    def name(self) -> str:
        return 'Device_DevicePdlModeChangeIndication'


# ---------------------------------------------------------------------
# Event parsing helpers
# ---------------------------------------------------------------------

def _key_length(name: str) -> int:
    """Return the byte length of an event key (4 or 6)."""
    # Two-word keys (no variant): 4 bytes
    # Three-word keys (with variant): 6 bytes
    for (_w0, _w1, var), n in EVENT_KEYS.items():
        if n == name:
            return 6 if var is not None else 4
    return 0  # Unknown key


def _parse_value(name: str, payload: bytes) -> tuple[Any, ...]:
    """
    Parse value bytes from an event payload based on EVENT_PAYLOAD schema.

    Args:
        name: Event name (e.g. 'Battery_Events_Percentage')
        payload: Full event payload bytes

    Returns:
        Tuple of parsed value(s) per the schema

    Raises:
        ValueError: If schema is unknown or payload too short
    """
    if name not in EVENT_PAYLOAD:
        return ()

    schema = EVENT_PAYLOAD[name]
    key_len = _key_length(name)
    offset = key_len

    values = []
    for field in schema:
        if offset + 1 > len(payload):
            break
        if field == 'u8':
            values.append(payload[offset])
            offset += 1
        elif field == 'u16':
            if offset + 2 > len(payload):
                break
            values.append(int.from_bytes(payload[offset:offset + 2], 'little'))
            offset += 2
    return tuple(values)


def parse_event_payload(payload: bytes):
    """
    Parse a device->host event payload into the appropriate event dataclass.

    Args:
        payload: The event payload bytes (from Frame.payload)

    Returns:
        An event dataclass instance, or None if the payload is not a known
        event key.
    """
    decoded = decode_event_key(payload)
    if decoded is None or decoded[0] is None:
        return None

    name, _word0, _word1, _variant = decoded
    values = _parse_value(name, payload)

    # Battery events
    if name == 'Battery_Events_Percentage' and len(values) >= 1:
        return BatteryEvent(level=values[0], raw_payload=payload)
    if name == 'Battery_Events_ChargingChanged' and len(values) >= 1:
        return ChargingEvent(state=values[0], raw_payload=payload)

    # Sound events
    if name == 'Sound_Events_SideToneGainChanged' and len(values) >= 1:
        return SidetoneEvent(level=values[0], raw_payload=payload)
    if name == 'Sound_Events_PcSoundPriority' and len(values) >= 1:
        return PcSoundPriorityEvent(priority=values[0], raw_payload=payload)
    if name == 'Sound_Events_VolumeLimiterModeChanged' and len(values) >= 1:
        return VolumeLimiterEvent(mode=values[0], raw_payload=payload)

    # ANC events
    if name == 'ANC_Events_HearThroughChanged' and len(values) >= 1:
        return ANCHearThroughEvent(enabled=values[0], raw_payload=payload)
    if name == 'ANC_Events_AdaptiveNoiseCancelationLevelChanged' and len(values) >= 1:
        return ANCLevelEvent(level=values[0], raw_payload=payload)
    if name == 'ANC_AdaptiveNoiseCancelationStateChanged' and len(values) >= 1:
        return ANCStateEvent(state=values[0], raw_payload=payload)

    # Link/connection events
    if name == 'Device_ConnectionEvents_ConnectionStatus' and len(values) >= 1:
        return LinkEvent(status=values[0], raw_payload=payload)
    if name == 'Service_Events_SubDevicesChanged' and len(values) >= 1:
        return SubDevicesEvent(count=values[0], raw_payload=payload)
    if name == 'Device_ConnectionEvents_PairingStatusIndication' and len(values) >= 1:
        return PairingStatusEvent(status=values[0], raw_payload=payload)
    if name == 'Device_ConnectionEvents_ConnectionChangeEvent' and len(values) >= 2:
        return ConnectionChangeEvent(b0=values[0], b1=values[1], raw_payload=payload)
    if name == 'Device_ConnectionEvents_MultipointConnectionInScoStatus' and len(values) >= 1:
        return MultipointScoEvent(status=values[0], raw_payload=payload)

    # Input events
    if name == 'Input_Events_VirtualButtonEvent' and len(values) >= 4:
        return VirtualButtonEvent(b0=values[0], b1=values[1], b2=values[2], b3=values[3],
                                 raw_payload=payload)
    if name == 'Input_Events_MMIConfigurationUpdate' and len(values) >= 2:
        return MMIConfigEvent(b0=values[0], b1=values[1], raw_payload=payload)

    # Auto power off
    if name == 'Service_Events_AutoPowerOffTimerValue' and len(values) >= 1:
        return AutoPowerOffTimerEvent(value=values[0], raw_payload=payload)
    if name == 'Service_Events_AutoPowerOffTimerStatus' and len(values) >= 1:
        return AutoPowerOffStatusEvent(status=values[0], raw_payload=payload)

    # Speaker/mic events
    if name == 'SpeakerMic_Events_TalkWhileMuteStatus' and len(values) >= 1:
        return TalkWhileMuteEvent(status=values[0], raw_payload=payload)
    if name == 'SpeakerMic_OptimizedMicSettingChanged' and len(values) >= 1:
        return SpeakerMicSettingEvent(setting=values[0], raw_payload=payload)

    # Other events
    if name == 'Component_Events_StatusChange' and len(values) >= 2:
        return ComponentStatusEvent(b0=values[0], w0=values[1], raw_payload=payload)
    if name == 'Tone_AudioPromptsModeChanged' and len(values) >= 1:
        return TonePromptEvent(mode=values[0], raw_payload=payload)
    if name == 'Device_DevicePdlModeChangeIndication' and len(values) >= 1:
        return PdlModeEvent(mode=values[0], raw_payload=payload)

    return None


def parse_frame_event(frame: Frame):
    """
    Parse a Frame as a device->host event into an event dataclass.

    Args:
        frame: A Frame object (kind='event')

    Returns:
        An event dataclass instance, or None if the frame is not a known
        event or parse_event_payload returns None.
    """
    if frame.kind != 'event':
        return None
    return parse_event_payload(frame.payload)
