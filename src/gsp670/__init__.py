#!/usr/bin/env python3
"""
EPOS|Sennheiser GSP 670 Python Library

A Python library for interacting with the GSP 670 gaming headset and GSA 70 dongle
via the Capricorn HID protocol.

Usage:
    from gsp670 import GSA70Device, find_devices

    # Find and open the dongle
    devices = find_devices()
    dongle = GSA70Device()
    dongle.open()

    # Send a verified SECOM command
    response = dongle.get_device_name()   # opcode 0x02 -> "EPOS GSA 70"
    print(response)

Modules:
    protocol - Capricorn protocol implementation (frame encoding/decoding)
    device   - Device abstraction (GSP670Device, GSA70Device)
    discovery - Device discovery (find_devices, enumerate_hid, enumerate_audio)
    controls - Device controls (volume, mute, sidetone)
    telemetry - Status reporting (battery, link, headset state)
    cli      - Command-line interface

Reference: docs/verified-secom-opcodes.md
"""

__version__ = "0.1.0"
__author__ = "GSP 670 Reverse Engineering Project"

# Protocol module - core Capricorn implementation
# Config module
from .config import (
    DeviceConfig,
    EQPreset,
    get_default_config,
    load_device_config,
    save_device_config,
)

# Controls module
from .controls import (
    ControlsState,
    MuteControl,
    SecomControl,
    SidetoneControl,
    VolumeControl,
    volume_delta_to_level,
)

# Device module
from .device import (
    CommunicationError,
    DeviceDisconnectedError,
    DeviceError,
    DeviceInfo,
    DeviceNotFoundError,
    GSA70Device,
    GSP670Device,
)

# Discovery module
from .discovery import (
    enumerate_audio,
    enumerate_hid,
    find_audio_card,
    find_devices,
    find_dongle,
    find_headset,
    find_hid_device,
    get_device_path,
    print_audio_devices,
    print_devices,
)

# Events module
from .events import (
    ANCHearThroughEvent,
    ANCLevelEvent,
    ANCStateEvent,
    AutoPowerOffStatusEvent,
    AutoPowerOffTimerEvent,
    BatteryEvent,
    ChargingEvent,
    ComponentStatusEvent,
    ConnectionChangeEvent,
    LinkEvent,
    MMIConfigEvent,
    MultipointScoEvent,
    PairingStatusEvent,
    PcSoundPriorityEvent,
    PdlModeEvent,
    SidetoneEvent,
    SpeakerMicSettingEvent,
    SubDevicesEvent,
    TalkWhileMuteEvent,
    TonePromptEvent,
    VirtualButtonEvent,
    VolumeLimiterEvent,
    parse_event_payload,
    parse_frame_event,
)
from .protocol import (
    EVENT_KEYS,
    # Event keys (Phase 3, recovered dispatcher table)
    EVENT_NAMESPACE,
    EVENT_PAYLOAD,
    EVENT_WORDS,
    FILLER,
    MARKER_ACK,
    MARKER_DEVICE,
    MARKER_HOST,
    MARKER_NAK,
    PID_GSA70,
    PID_GSP670,
    PID_UPGRADE_MODE,
    PIDS_UPGRADE,
    REPORT_LEN,
    RPT,
    RTX_FWU_IDS,
    RTX_PAD,
    # Rtx FWU channel (Phase 3, session-handshake.md §6.3/§6.5)
    RTX_REPORT_PREFIX,
    RTX_REPORT_SIZE,
    SYNC,
    USAGE,
    USAGE_PAGE,
    # Constants
    VID,
    Frame,
    # Classes
    Opcode,
    SecomOpcode,
    classify,
    # Functions
    crc8,
    decode_event_key,
    expected_reply_opcode,
    format_event_key,
    frame,
    make_fwu_frame,
    marker_transform,
    rtx_fwu_enable,
    rtx_fwu_packet,
    secom_request,
    secom_value,
    validate_frame,
)

# Telemetry module
from .telemetry import (
    BatteryLevel,
    BatteryState,
    ChargingState,
    HeadsetState,
    HeadsetStatus,
    LinkQuality,
    LinkState,
    format_battery_status,
    format_headset_status,
    format_link_status,
    parse_device_notify_ind,
    parse_fwu_status_ind,
)

__all__ = [
    # Version
    "__version__",
    # Protocol
    "VID",
    "PID_GSA70",
    "PID_GSP670",
    "PID_UPGRADE_MODE",
    "PIDS_UPGRADE",
    "USAGE_PAGE",
    "USAGE",
    "RPT",
    "REPORT_LEN",
    "MARKER_HOST",
    "MARKER_DEVICE",
    "MARKER_ACK",
    "MARKER_NAK",
    "SYNC",
    "FILLER",
    "Opcode",
    "SecomOpcode",
    "Frame",
    "crc8",
    "frame",
    "classify",
    "validate_frame",
    "expected_reply_opcode",
    "secom_request",
    "secom_value",
    "marker_transform",
    "make_fwu_frame",
    # Rtx FWU channel (Phase 3, session-handshake.md §6.3/§6.5)
    "RTX_REPORT_PREFIX",
    "RTX_REPORT_SIZE",
    "RTX_PAD",
    "RTX_FWU_IDS",
    "rtx_fwu_packet",
    "rtx_fwu_enable",
    # Event keys (Phase 3, f000 namespace)
    "EVENT_NAMESPACE",
    "EVENT_WORDS",
    "EVENT_KEYS",
    "EVENT_PAYLOAD",
    "decode_event_key",
    "format_event_key",
    # Device
    "DeviceInfo",
    "DeviceError",
    "DeviceNotFoundError",
    "DeviceDisconnectedError",
    "CommunicationError",
    "GSP670Device",
    "GSA70Device",
    # Discovery
    "find_devices",
    "enumerate_hid",
    "enumerate_audio",
    "find_hid_device",
    "find_dongle",
    "find_headset",
    "get_device_path",
    "find_audio_card",
    "print_devices",
    "print_audio_devices",
    # Controls
    "SecomControl",
    "VolumeControl",
    "MuteControl",
    "SidetoneControl",
    "ControlsState",
    "volume_delta_to_level",
    # Telemetry
    "BatteryLevel",
    "ChargingState",
    "LinkQuality",
    "HeadsetState",
    "BatteryState",
    "LinkState",
    "HeadsetStatus",
    "parse_fwu_status_ind",
    "parse_device_notify_ind",
    "format_battery_status",
    "format_link_status",
    "format_headset_status",
    # Events
    "BatteryEvent",
    "ChargingEvent",
    "SidetoneEvent",
    "ANCHearThroughEvent",
    "ANCLevelEvent",
    "ANCStateEvent",
    "LinkEvent",
    "SubDevicesEvent",
    "VolumeLimiterEvent",
    "PcSoundPriorityEvent",
    "TalkWhileMuteEvent",
    "VirtualButtonEvent",
    "MMIConfigEvent",
    "AutoPowerOffTimerEvent",
    "AutoPowerOffStatusEvent",
    "ComponentStatusEvent",
    "TonePromptEvent",
    "PairingStatusEvent",
    "ConnectionChangeEvent",
    "MultipointScoEvent",
    "SpeakerMicSettingEvent",
    "PdlModeEvent",
    "parse_event_payload",
    "parse_frame_event",
    # Config
    "DeviceConfig",
    "EQPreset",
    "get_default_config",
    "save_device_config",
    "load_device_config",
]
