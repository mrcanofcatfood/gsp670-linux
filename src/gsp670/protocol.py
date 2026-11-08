#!/usr/bin/env python3
"""
Capricorn protocol implementation for EPOS|Sennheiser GSP 670 headset and GSA 70 dongle.

Wire layout (report coords, /dev/hidraw):
    report[0]    = 0x01 report id
    report[1..4] = EB FE 01 00  sync
    report[5..6] = marker       host=04 00, device=10 01, ack=05 30, nak=04 10
                                device events=00 01 / ff 01 (opcode 0x0004)
    report[7..8] = opcode LE
    report[9..10]= size LE      (payload length)
    report[11]   = CRC-8(poly 0x07, init 0xFF) over payload
    report[12]   = 0x00 filler
    report[13..] = payload

Reply classification:
    NAK  = marker 04 10, size 0, crc FF
    ACK  = marker 05 30, size N, crc = crc8(payload)
    EVENT= marker 00 01 / ff 01, opcode 0x0004, crc = crc8(payload)

Opcode transform (request → reply):
    reply_opcode = (req & 0xFF00) | ((req & 0xFF) >> 2)

Reference: docs/verified-secom-opcodes.md
"""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Tuple

# Vendor ID for EPOS|Sennheiser devices
VID = 0x1395

# Product IDs
PID_GSA70 = 0x0300        # GSA 70 dongle (normal mode)
PID_GSP670 = 0x008a       # GSP 670 headset (when in device mode)
PID_UPGRADE_MODE = 0x8300  # EPOS GSA 70 upgrade mode
PIDS_UPGRADE = (0x8300, 0x8303, 0x8089, 0x808A)  # All known upgrade PIDs

# HID usage page and usage for the vendor interface
USAGE_PAGE = 0xFFFF
USAGE = 0x01

# Report dimensions (106 bytes after report id)
RPT = 106                 # data bytes after report id
REPORT_LEN = RPT + 1      # total including report id (107)

# Markers
MARKER_HOST = b'\x04\x00'       # Host → Device
MARKER_DEVICE = b'\x10\x01'     # Device → Host (unsolicited data / events)
MARKER_ACK = b'\x05\x30'        # ACK response
MARKER_NAK = b'\x04\x10'        # NAK response
# Unsolicited device → host *event* markers (live-verified 2026-10-12).
# Observed on the dongle while the RF-linked GSP 670's battery button was
# pressed; the opcode field is 0x0004 in both.  See docs section 5.2.
MARKER_EVENT_BURST = b'\x00\x01'  # burst of ~70 frames on a button press
MARKER_EVENT_POLL = b'\xff\x01'   # recurring ~1-2 s keepalive/config frame

# Sync bytes
SYNC = b'\xEB\xFE\x01\x00'

# Filler byte
FILLER = 0x00


class Opcode(IntEnum):
    """Capricorn protocol opcodes."""
    # FWU (Firmware Update) family (0x4F00-0x4F15)
    FWU_ENABLE_REQ = 0x4F00
    FWU_ENABLE_CFM = 0x4F01
    FWU_DEVICE_NOTIFY_IND = 0x4F02
    FWU_UPDATE_REQ = 0x4F03
    FWU_UPDATE_CFM = 0x4F04
    FWU_UPDATE_IND = 0x4F05
    FWU_UPDATE_RES = 0x4F06
    FWU_GET_BLOCK_IND = 0x4F07
    FWU_GET_BLOCK_RES = 0x4F08
    FWU_GET_CRC_IND = 0x4F09
    FWU_GET_CRC_RES = 0x4F0A
    FWU_COMPLETE_IND = 0x4F0B
    FWU_STATUS_IND = 0x4F0C
    FWU_MULTI_CRC_IND = 0x4F0D
    FWU_MULTI_CRC_RES = 0x4F0E
    # 0x4F0F undefined
    FWU_SET_FEATURES_REQ = 0x4F10
    FWU_SET_FEATURES_CFM = 0x4F11
    FWU_GET_FEATURES_REQ = 0x4F12
    FWU_GET_FEATURES_CFM = 0x4F13
    FWU_CRC32_IND = 0x4F14
    FWU_CRC32_RES = 0x4F15


class SecomOpcode(IntEnum):
    """
    Capricorn / SECOM command opcodes (the *normal-mode* control protocol).

    Verified 2026-10-12 by:
      * static analysis of ``EPOSGamingSuiteService``
        (``CCapricornDatagram::getHIDBuffers`` / ``getPayload`` /
        ``EncodeDatagram`` / ``parseDatagram``), and
      * live probing of a GSA 70 dongle (1395:0300) via ``/dev/hidraw1``.

    The opcode lives in the frame header (bytes 7..8, LE). It is *not* the
    ``FeatureIndex`` scheme that was previously guessed. Each opcode carries a
    fixed 4-byte (or 4-byte + 1-byte value) request payload; see
    ``SECOM_REQUEST_PAYLOAD``.

    Live behaviour of the dongle:
      * 0x00-0x03 -> real data response (marker 04 00, opcode 0x0000)
      * 0x04/0x05 -> sub-device reply (marker 04 00, class 0x0004); with the
        headset RF-linked 0x04 echoes the request and appends value 00 00
      * 0x06,0x0c,0x0e,0x10,0x13,0x14,0x17,0x19,0x1b -> link ACK only
        (marker 05 30, opcode = req >> 2; 0x14/0x15 use class 0x0008)
      * 0x08,0x0b,0x0d,0x0f -> "Opcode not supported" in the service and
        are not emitted.

    A get reply for a value opcode (e.g. 0x0e battery) is
    ``<request header echo> <value lo> <value hi>``; parse it with
    :func:`secom_value`. The reply class field (bytes 7..9) is not a strict
    echo: 0x0000 plain data, 0x0004 device-event/sub-device, req>>2 ACKs.
    """
    GET_FW_VERSION = 0x00            # -> parseSwVersion
    GET_SERIAL_NO = 0x01             # -> parseGetSerialNumber
    GET_DEVICE_NAME = 0x02           # -> parseDeviceName ("EPOS GSA 70")
    GET_DEVICE_ADDRESS = 0x03        # -> parseBDAddr (Bluetooth address)
    GET_SUBDEVICES_CONNECTED = 0x04  # -> parsesubDevicesConnected
    # 0x05 unknown
    GET_DFU_TYPE = 0x06              # -> parseDfuType
    ENTER_DFU = 0x07                 # -> parseEnterDfu
    # 0x08 / 0x0b / 0x0d / 0x0f -> "Opcode not supported"
    # 0x09 unknown
    # 0x0a unknown
    GET_NESTED_DEVICE_BT_NAME = 0x0C  # -> parseDeviceBtName
    GET_BATTERY_PERCENTAGE = 0x0E     # -> GetBatPercentage
    GET_SIDETONE = 0x10               # -> GetSideToneGain
    SET_SIDETONE = 0x11               # value byte appended
    SET_NOISE_REDUCTION = 0x12        # value byte appended
    GET_NOISE_REDUCTION = 0x13        # -> GetNoiseReductionLevel
    GET_NESTED_DEVICE_PID = 0x14      # -> parsePIDNumber
    # 0x15 unknown
    SEND_LATENCY = 0x16               # value byte appended
    GET_LATENCY = 0x17                # -> GetLatencyLevel
    GET_REMOTE_DEVICE_INFO = 0x18     # value byte appended -> GetRemoteDeviceInfo
    GET_NBR_LINK_KEYS = 0x19          # -> GetNbrLinkKeys
    SET_AUTO_POWER_OFF = 0x1A         # value byte appended
    GET_AUTO_POWER_OFF = 0x1B
    # 0x1C unknown


#: Request payload for each SECOM opcode, exactly as recovered from
#: ``CCapricornDatagram::getHIDBuffers``. Opcodes listed in
#: ``SECOM_VALUE_OPCODES`` append one value byte (stored as a u16 LE, i.e.
#: ``<value> 00``) and therefore use a length of 6.
SECOM_REQUEST_PAYLOAD = {
    0x00: bytes.fromhex('01000300'),
    0x01: bytes.fromhex('01000b00'),
    0x02: bytes.fromhex('09000100'),
    0x03: bytes.fromhex('06001400'),
    0x04: bytes.fromhex('01000900'),
    0x05: bytes.fromhex('01000a00'),
    0x06: bytes.fromhex('01000d00'),
    0x07: bytes.fromhex('01000600'),
    0x09: bytes.fromhex('06000900') + b'\x00' * 10,
    0x0A: bytes.fromhex('06001300'),
    0x0C: bytes.fromhex('06002700'),
    0x0E: bytes.fromhex('12000300'),
    0x10: bytes.fromhex('0a000c00'),
    0x11: bytes.fromhex('0a000b00'),
    0x12: bytes.fromhex('0a001100'),
    0x13: bytes.fromhex('0a001200'),
    0x14: bytes.fromhex('01001400'),
    0x15: bytes.fromhex('0800f000'),
    0x16: bytes.fromhex('0a001600'),
    0x17: bytes.fromhex('0a001700'),
    0x18: bytes.fromhex('06003200'),
    0x19: bytes.fromhex('06001100'),
    0x1A: bytes.fromhex('01001f00'),
    0x1B: bytes.fromhex('01002000'),
    0x1C: bytes.fromhex('06001c00'),
}

#: Opcodes that append a single-byte value (sent as ``<value> 00``).
SECOM_VALUE_OPCODES = frozenset({0x11, 0x12, 0x16, 0x18, 0x1A})

#: A device -> host event key is a short array of little-endian u16 words at the
#: start of the datagram body: ``<word0> <word1> [<variant>]``. The dispatcher
#: ``FUN_00643b10`` compares three words with ``FUN_00642d30`` and two words
#: with ``FUN_00642cf0`` (Ghidra + ``objdump``, 2026-10-13).
#:
#: The **second word is not a fixed namespace**. It is ``0x00F0`` for most
#: notifications but varies by source component: battery uses ``0x000F``,
#: ANC-state / tone use ``0x0007``, speaker-mic ``0x001D`` and device PDL
#: ``0x0029``. Earlier notes claiming a uniform ``f0 00`` word were an
#: over-generalisation (see ``analysis/session-handshake.md`` section 6.1).
EVENT_NAMESPACE = 0x00F0  # the most common word1 value (NOT universal)

#: Word1 values seen in the recovered dispatcher table.
EVENT_WORDS = frozenset({0x00F0, 0x000F, 0x0007, 0x001D, 0x0029})

#: Recovered device -> host event keys: ``(word0, word1, variant) -> name``.
#: ``variant`` is ``None`` for the two-word (4-byte key) form.
EVENT_KEYS = {
    (0x0023, 0x00F0, 0x0001): 'Component_Events_StatusChange',
    (0x0017, 0x0007, None): 'ANC_AdaptiveNoiseCancelationStateChanged',
    (0x0017, 0x00F0, 0x0001): 'ANC_Events_HearThroughChanged',
    (0x0017, 0x00F0, 0x0002): 'ANC_Events_AdaptiveNoiseCancelationLevelChanged',
    (0x0012, 0x000F, 0x0003): 'Battery_Events_ChargingChanged',
    (0x0012, 0x000F, 0x0004): 'Battery_Events_Percentage',
    (0x0010, 0x001D, None): 'SpeakerMic_OptimizedMicSettingChanged',
    (0x0010, 0x00F0, 0x0001): 'SpeakerMic_Events_TalkWhileMuteStatus',
    (0x000A, 0x00F0, 0x0002): 'Sound_Events_SideToneGainChanged',
    (0x000A, 0x00F0, 0x0003): 'Sound_Events_PcSoundPriority',
    (0x000A, 0x00F0, 0x0004): 'Sound_Events_VolumeLimiterModeChanged',
    (0x0008, 0x00F0, 0x0003): 'Input_Events_VirtualButtonEvent',
    (0x0008, 0x00F0, 0x0007): 'Input_Events_MMIConfigurationUpdate',
    (0x0007, 0x0007, None): 'Tone_AudioPromptsModeChanged',
    (0x0006, 0x0029, None): 'Device_DevicePdlModeChangeIndication',
    (0x0006, 0x00F0, 0x0001): 'Device_ConnectionEvents_ConnectionStatus',
    (0x0006, 0x00F0, 0x0004): 'Device_ConnectionEvents_PairingStatusIndication',
    (0x0006, 0x00F0, 0x0005): 'Device_ConnectionEvents_ConnectionChangeEvent',
    (0x0006, 0x00F0, 0x0007): 'Device_ConnectionEvents_MultipointConnectionInScoStatus',
    (0x0001, 0x00F0, 0x0001): 'Service_Events_SubDevicesChanged',
    (0x0001, 0x00F0, 0x0002): 'Service_Events_AutoPowerOffTimerValue',
    (0x0001, 0x00F0, 0x0003): 'Service_Events_AutoPowerOffTimerStatus',
}

#: Value schema (bytes after the key) per event, recovered from the dispatcher's
#: in-byte-stream reads: ``FUN_006b3cf0`` = u8, ``FUN_006b3d40`` = u16 LE. The
#: tuple lists the fields in order; e.g. ``('u8', 'u16')`` is 3 value bytes.
EVENT_PAYLOAD = {
    'Component_Events_StatusChange': ('u8', 'u16'),
    'ANC_AdaptiveNoiseCancelationStateChanged': ('u16',),
    'ANC_Events_HearThroughChanged': ('u8',),
    'ANC_Events_AdaptiveNoiseCancelationLevelChanged': ('u16',),
    'Battery_Events_ChargingChanged': ('u16',),
    'Battery_Events_Percentage': ('u8',),
    'SpeakerMic_OptimizedMicSettingChanged': ('u8',),
    'SpeakerMic_Events_TalkWhileMuteStatus': ('u16',),
    'Sound_Events_SideToneGainChanged': ('u16',),
    'Sound_Events_PcSoundPriority': ('u8',),
    'Sound_Events_VolumeLimiterModeChanged': ('u8',),
    'Input_Events_VirtualButtonEvent': ('u8', 'u8', 'u8', 'u8'),
    'Input_Events_MMIConfigurationUpdate': ('u8', 'u8'),
    'Tone_AudioPromptsModeChanged': ('u16',),
    'Device_DevicePdlModeChangeIndication': ('u8',),
    'Device_ConnectionEvents_ConnectionStatus': ('u16',),
    'Device_ConnectionEvents_PairingStatusIndication': ('u8',),
    'Device_ConnectionEvents_ConnectionChangeEvent': ('u8', 'u8'),
    'Device_ConnectionEvents_MultipointConnectionInScoStatus': ('u8',),
    'Service_Events_SubDevicesChanged': ('u16',),
    'Service_Events_AutoPowerOffTimerValue': ('u16',),
    'Service_Events_AutoPowerOffTimerStatus': ('u8',),
}


def decode_event_key(payload: bytes):
    """
    Decode a device -> host event key.

    Args:
        payload: The event payload (as delivered in a ``Frame.payload``).

    Returns:
        ``(name, word0, word1, variant)`` where ``name`` is ``None`` when the
        key is not in the recovered table and ``variant`` is ``None`` for the
        two-word (4-byte key) form. Returns ``None`` when ``payload`` is not a
        Modi event key at all (too short, or ``word1`` is not a known event
        word).
    """
    if len(payload) < 4:
        return None
    word0 = int.from_bytes(payload[0:2], 'little')
    word1 = int.from_bytes(payload[2:4], 'little')
    if word1 not in EVENT_WORDS:
        return None
    variant = int.from_bytes(payload[4:6], 'little') if len(payload) >= 6 else None
    if (word0, word1, variant) in EVENT_KEYS:
        return (EVENT_KEYS[(word0, word1, variant)], word0, word1, variant)
    # A two-word key with a two-byte value is also six bytes long, so the
    # three-word lookup above must miss before this fallback can match.
    if (word0, word1, None) in EVENT_KEYS:
        return (EVENT_KEYS[(word0, word1, None)], word0, word1, None)
    return (None, word0, word1, variant)


def format_event_key(payload: bytes) -> Optional[str]:
    """
    Format a device -> host event key as a human-readable string.

    Args:
        payload: The event payload (as delivered in a ``Frame.payload``).

    Returns:
        A string such as ``Battery_Events_Percentage (12 00 0f 00 04 00)``, or
        ``None`` when ``payload`` is not a Modi event key. Unknown keys within
        the event words are rendered with their raw bytes.
    """
    decoded = decode_event_key(payload)
    if decoded is None:
        return None
    name, _word0, _word1, variant = decoded
    width = 4 if variant is None else 6
    raw = payload[:width].hex(' ')
    if name is None:
        return f'unknown event ({raw})'
    return f'{name} ({raw})'


def secom_request(opcode: int, value: Optional[int] = None) -> bytes:
    """
    Build the request payload for a SECOM opcode.

    Args:
        opcode: A :class:`SecomOpcode` value.
        value: Value byte for ``SECOM_VALUE_OPCODES``.

    Returns:
        Request payload bytes.

    Raises:
        ValueError: If the opcode has no known payload or a required value is
            missing.
    """
    opcode = int(opcode)
    if opcode not in SECOM_REQUEST_PAYLOAD:
        raise ValueError(f"No known SECOM payload for opcode 0x{opcode:04X}")
    payload = SECOM_REQUEST_PAYLOAD[opcode]
    if opcode in SECOM_VALUE_OPCODES:
        if value is None:
            raise ValueError(f"Opcode 0x{opcode:04X} requires a value")
        payload = payload + bytes([value & 0xFF, 0x00])
    return payload


def secom_value(reply: 'Frame') -> bytes:
    """
    Extract the value bytes from a SECOM data reply.

    A get reply (marker ``04 00``) echoes the 4-byte request payload and then
    appends the value, e.g. ``01 00 09 00 | 00 00``.
    """
    return reply.payload[4:] if len(reply.payload) > 4 else b''


@dataclass
class Frame:
    """Parsed Capricorn frame."""
    report_id: int
    sync: bytes
    marker: bytes
    opcode: int
    size: int
    crc: int
    filler: int
    payload: bytes
    tail: bytes  # bytes after claimed payload
    kind: str = 'unknown'  # 'ack', 'nak', 'event', 'subreply', 'other', 'short'
    expected_opcode: Optional[int] = None

    @property
    def event_name(self) -> Optional[str]:
        """
        Recovered Modi event name for this payload.

        Returns ``None`` when ``payload`` is not a Modi event key; unknown keys
        using a known event word are described with their raw bytes (see
        :func:`format_event_key`).
        """
        return format_event_key(self.payload)


def crc8(data: bytes, init: int = 0xFF) -> int:
    """
    Compute CRC-8 of data using polynomial 0x07, initial value 0xFF.
    
    Args:
        data: Bytes to compute CRC over
        init: Initial CRC value (default 0xFF)
    
    Returns:
        CRC-8 value (0-255)
    """
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def expected_reply_opcode(request_opcode: int) -> int:
    """
    Compute the expected reply opcode for a given request opcode.
    
    Transform: reply_opcode = (req & 0xFF00) | ((req & 0xFF) >> 2)
    
    Args:
        request_opcode: The request opcode
    
    Returns:
        Expected reply opcode
    """
    return (request_opcode & 0xFF00) | ((request_opcode & 0xFF) >> 2)


def frame(opcode: int, payload: bytes = b'', marker: bytes = MARKER_HOST) -> bytes:
    """
    Build a 107-byte HID report (report id + 106 data bytes).
    
    Wire format:
        [0]     = 0x01 report id
        [1..4]  = EB FE 01 00 sync
        [5..6]  = marker (host=04 00, device=10 01)
        [7..8]  = opcode LE
        [9..10] = size LE (payload length)
        [11]    = CRC-8(payload) with poly 0x07, init 0xFF
        [12]    = 0x00 filler
        [13..]  = payload
    
    Args:
        opcode: Capricorn opcode
        payload: Payload bytes (max 93 bytes to fit in 106-byte frame)
        marker: Host marker (default: 04 00)
    
    Returns:
        107-byte HID report
    
    Raises:
        AssertionError: If payload is too long
    """
    max_payload = RPT - 12  # 94 bytes max
    assert len(payload) <= max_payload, f'payload too long (max {max_payload})'
    
    data = bytearray(RPT)
    data[0:4] = SYNC
    data[4:6] = marker
    data[6] = opcode & 0xFF
    data[7] = (opcode >> 8) & 0xFF
    data[8] = len(payload) & 0xFF
    data[9] = (len(payload) >> 8) & 0xFF
    data[10] = crc8(payload)
    data[11] = FILLER
    data[12:12 + len(payload)] = payload
    
    return bytes([0x01]) + bytes(data)


def classify(raw: bytes, request_opcode: Optional[int] = None) -> Frame:
    """
    Classify and parse a received Capricorn frame.
    
    Args:
        raw: Raw bytes from HID read
        request_opcode: Original request opcode (for computing expected reply)
    
    Returns:
        Frame dataclass with parsed fields
    """
    out = Frame(
        report_id=0,
        sync=b'',
        marker=b'',
        opcode=0,
        size=0,
        crc=0,
        filler=0,
        payload=b'',
        tail=b'',
        kind='unknown'
    )
    
    d = bytes(raw)
    out.report_id = d[0] if len(d) > 0 else 0
    out.sync = d[1:5] if len(d) > 4 else b''
    out.marker = d[5:7] if len(d) > 6 else b''
    
    if len(d) < 13:
        out.kind = 'short'
        return out
    
    out.opcode = int.from_bytes(d[7:9], 'little')
    out.size = int.from_bytes(d[9:11], 'little')
    out.crc = d[11]
    out.filler = d[12]
    out.payload = d[13:13 + out.size] if len(d) > 13 else b''
    out.tail = d[13 + out.size:] if len(d) > 13 else b''
    
    # Classify based on marker
    marker_hex = out.marker.hex()
    if marker_hex == MARKER_NAK.hex():
        out.kind = 'nak'
    elif marker_hex == MARKER_ACK.hex():
        out.kind = 'ack'
    elif marker_hex in (MARKER_EVENT_BURST.hex(), MARKER_EVENT_POLL.hex()):
        out.kind = 'event'
    elif marker_hex == MARKER_HOST.hex() and out.opcode == 0x0004:
        # Sub-device reply class (opcodes 0x04 / 0x05 when the headset is
        # RF-linked): marker 04 00 with class field 0x0004, echo (+ value).
        out.kind = 'subreply'
    else:
        out.kind = 'other'
    
    # Compute expected reply opcode if request was provided
    if request_opcode is not None:
        out.expected_opcode = expected_reply_opcode(request_opcode)
    
    return out


def make_fwu_frame(opcode: int, payload: bytes = b'') -> bytes:
    """
    (Deprecated) Build a SECOM ``04 00`` frame for an FWU-family opcode.

    .. deprecated::
        FWU does **not** ride the SECOM ``04 00`` transport. Sending
        ``0x4F*`` as a SECOM frame is the wrong path and NAKs — the real
        channel is the **Rtx** datagram channel (64-byte ``0x58`` reports,
        ``0xEE``-padded). See ``analysis/session-handshake.md`` §6.3/§6.5 and
        use :func:`rtx_fwu_packet` / :func:`rtx_fwu_enable` instead.

    Args:
        opcode: FWU opcode (0x4F00-0x4F15)
        payload: Payload bytes

    Returns:
        107-byte HID report
    """
    return frame(opcode, payload, MARKER_HOST)


#: Rtx datagram channel prefix byte (``RtxDatagramIo::split_request_into_packets``
#: ``FUN_0067a070``): report byte 0, then ≤63 payload bytes, ``0xEE``-padded.
RTX_REPORT_PREFIX = 0x58
#: Length of each Rtx report.
RTX_REPORT_SIZE = 64
#: Pad byte filling the tail of an Rtx report.
RTX_PAD = 0xEE

#: Recovered Rtx FWU command ids: ``purpose -> request id``
#: (``analysis/session-handshake.md`` §6.3).
RTX_FWU_IDS = {
    'enable': 0x4F00,
    'update': 0x4F03,
    'result': 0x4F06,
    'block': 0x4F08,
    'crc': 0x4F0A,
    'multi_crc': 0x4F0E,
    'set_features': 0x4F10,
    'keepalive': 0xF066,
}


def rtx_fwu_packet(request: bytes, pad_to: int = RTX_REPORT_SIZE) -> bytes:
    """
    Wrap a serialized Rtx FWU request into a report frame.

    FWU travels on the **Rtx** datagram channel, not SECOM ``04 00``
    (``analysis/session-handshake.md`` §6.3/§6.5). Reports are 64 bytes:
    byte 0 = ``0x58``, then the request bytes, right-padded with ``0xEE``.

    Args:
        request: Serialized request datagram, request id first — e.g.
            ``00 4F A B`` for the FWU *enable* request ``0x4f00``
            (see :func:`rtx_fwu_enable`).
        pad_to: Report length (default :data:`RTX_REPORT_SIZE`).

    Returns:
        ``bytes`` of length ``pad_to`` ready for a SET_REPORT write.

    Raises:
        ValueError: If ``request`` does not fit inside ``pad_to``.
    """
    if len(request) >= pad_to:
        raise ValueError(
            f"request of {len(request)} bytes does not fit a {pad_to}-byte report"
        )
    return (
        bytes([RTX_REPORT_PREFIX])
        + request
        + bytes([RTX_PAD]) * (pad_to - 1 - len(request))
    )


def rtx_fwu_enable(a: int = 0, b: int = 0) -> bytes:
    """
    Build the Rtx FWU *enable* report (request id ``0x4f00``).

    The serialized request is ``00 4F <A> <B>`` (two caller-supplied bytes)
    plus an expected-response sub-record ``0x4f01, 1, 01 00`` tracked by the
    service; the wire report is ``58 | 00 4F <A> <B> | EE…``.

    Args:
        a, b: The two request bytes (device/bootloader selector).

    Returns:
        A 64-byte Rtx report (see :func:`rtx_fwu_packet`).
    """
    return rtx_fwu_packet(bytes([0x00, 0x4F, a & 0xFF, b & 0xFF]))


def validate_frame(f: Frame) -> Tuple[bool, str]:
    """
    Validate a received frame.
    
    Args:
        f: Parsed Frame
    
    Returns:
        (is_valid, error_message)
    """
    if f.kind == 'short':
        return False, f"Frame too short ({len(f.payload) + 13} bytes)"
    
    if f.report_id != 0x01:
        return False, f"Invalid report ID: 0x{f.report_id:02x}"
    
    if f.sync != SYNC:
        return False, f"Invalid sync: {f.sync.hex()}"
    
    if f.filler != FILLER:
        return False, f"Invalid filler: 0x{f.filler:02x}"
    
    if f.kind in ('ack', 'event', 'subreply'):
        expected_crc = crc8(f.payload)
        if f.crc != expected_crc:
            return False, f"CRC mismatch: got 0x{f.crc:02x}, expected 0x{expected_crc:02x}"
    
    return True, ""


def marker_transform(marker: bytes) -> bytes:
    """
    Transform a host marker to expected device marker.
    
    Transform: byte0 + 1, byte1 + 0x30
    04 00 → 05 30, 03 04 → 04 34, 10 01 → 11 31
    
    Args:
        marker: Host marker (2 bytes)
    
    Returns:
        Expected device marker
    """
    if len(marker) != 2:
        raise ValueError("Marker must be 2 bytes")
    return bytes([marker[0] + 1, marker[1] + 0x30])
