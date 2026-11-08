#!/usr/bin/env python3
"""
Unit tests for the events module.

Tests event key parsing and value decoding for the 22 device->host
Modi event keys recovered from EPOSGamingSuiteService.

Reference: analysis/session-handshake.md §6.1 (corrected 2026-10-13).
"""

import sys
import unittest

sys.path.insert(0, 'src')

from gsp670.events import (
    ANCHearThroughEvent,
    ANCLevelEvent,
    BatteryEvent,
    ChargingEvent,
    SidetoneEvent,
    SubDevicesEvent,
    VirtualButtonEvent,
    VolumeLimiterEvent,
    _key_length,
    parse_event_payload,
)
from gsp670.protocol import EVENT_KEYS, EVENT_PAYLOAD, decode_event_key


class TestEventKeyDecoding(unittest.TestCase):
    """Test decode_event_key matches the EVENT_KEYS table."""

    def test_battery_percentage_key(self):
        """Battery_Events_Percentage: 12 00 0F 00 04 00"""
        payload = bytes.fromhex('12 00 0F 00 04 00 50 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertEqual(result[0], 'Battery_Events_Percentage')
        self.assertEqual(result[1], 0x0012)  # word0
        self.assertEqual(result[2], 0x000F)  # word1 (battery!)
        self.assertEqual(result[3], 0x0004)  # variant

    def test_battery_charging_changed_key(self):
        """Battery_Events_ChargingChanged: 12 00 0F 00 03 00"""
        payload = bytes.fromhex('12 00 0F 00 03 00 01 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertEqual(result[0], 'Battery_Events_ChargingChanged')
        self.assertEqual(result[2], 0x000F)  # word1 (battery!)

    def test_sidetone_key(self):
        """Sound_Events_SideToneGainChanged: 0A 00 F0 00 02 00"""
        payload = bytes.fromhex('0A 00 F0 00 02 00 32 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertEqual(result[0], 'Sound_Events_SideToneGainChanged')
        self.assertEqual(result[2], 0x00F0)  # word1 (default)

    def test_anc_hearthrough_key(self):
        """ANC_Events_HearThroughChanged: 17 00 F0 00 01 00"""
        payload = bytes.fromhex('17 00 F0 00 01 00 01 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertEqual(result[0], 'ANC_Events_HearThroughChanged')

    def test_anc_state_two_word_key(self):
        """ANC_AdaptiveNoiseCancelationStateChanged: 17 00 07 00 (4 bytes, no variant)"""
        payload = bytes.fromhex('17 00 07 00 01 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertEqual(result[0], 'ANC_AdaptiveNoiseCancelationStateChanged')
        self.assertEqual(result[2], 0x0007)  # word1 (ANC-state!)
        self.assertIsNone(result[3])  # no variant

    def test_sub_devices_key(self):
        """Service_Events_SubDevicesChanged: 01 00 F0 00 01 00"""
        payload = bytes.fromhex('01 00 F0 00 01 00 01 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertEqual(result[0], 'Service_Events_SubDevicesChanged')

    def test_invalid_word1(self):
        """Unknown word1 returns None."""
        payload = bytes.fromhex('FF FF 99 99 01 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertIsNone(result)


class TestValueParsing(unittest.TestCase):
    """Test value byte parsing per EVENT_PAYLOAD schemas."""

    def test_battery_percentage_u8(self):
        """Battery_Events_Percentage has u8 value at byte 6."""
        payload = bytes.fromhex('12 00 0F 00 04 00 50 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, BatteryEvent)
        self.assertEqual(event.level, 0x50)  # u8

    def test_battery_charging_u16(self):
        """Battery_Events_ChargingChanged has u16 value."""
        payload = bytes.fromhex('12 00 0F 00 03 00 01 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, ChargingEvent)
        self.assertEqual(event.state, 0x0001)  # u16 LE

    def test_sidetone_u16(self):
        """Sound_Events_SideToneGainChanged has u16 value."""
        payload = bytes.fromhex('0A 00 F0 00 02 00 32 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, SidetoneEvent)
        self.assertEqual(event.level, 0x0032)  # u16 LE

    def test_volume_limiter_u8(self):
        """Sound_Events_VolumeLimiterModeChanged has u8 value."""
        payload = bytes.fromhex('0A 00 F0 00 04 00 01 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, VolumeLimiterEvent)
        self.assertEqual(event.mode, 0x01)

    def test_anc_hearthrough_u8(self):
        """ANC_Events_HearThroughChanged has u8 value."""
        payload = bytes.fromhex('17 00 F0 00 01 00 01 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, ANCHearThroughEvent)
        self.assertEqual(event.enabled, 0x01)

    def test_anc_level_u16(self):
        """ANC_Events_AdaptiveNoiseCancelationLevelChanged has u16 value."""
        payload = bytes.fromhex('17 00 F0 00 02 00 03 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, ANCLevelEvent)
        self.assertEqual(event.level, 0x0003)

    def test_virtual_button_4_u8(self):
        """Input_Events_VirtualButtonEvent has 4 x u8 values."""
        payload = bytes.fromhex('08 00 F0 00 03 00 01 02 03 04'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, VirtualButtonEvent)
        self.assertEqual(event.b0, 0x01)
        self.assertEqual(event.b1, 0x02)
        self.assertEqual(event.b2, 0x03)
        self.assertEqual(event.b3, 0x04)

    def test_sub_devices_u16(self):
        """Service_Events_SubDevicesChanged has u16 value."""
        payload = bytes.fromhex('01 00 F0 00 01 00 01 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsInstance(event, SubDevicesEvent)
        self.assertEqual(event.count, 0x0001)


class TestKeyLength(unittest.TestCase):
    """Test _key_length returns correct byte count."""

    def test_two_word_keys(self):
        """Two-word keys (no variant) are 4 bytes."""
        two_word = ['ANC_AdaptiveNoiseCancelationStateChanged',
                    'SpeakerMic_OptimizedMicSettingChanged',
                    'Tone_AudioPromptsModeChanged',
                    'Device_DevicePdlModeChangeIndication']
        for name in two_word:
            self.assertEqual(_key_length(name), 4, f"{name} should be 4 bytes")

    def test_three_word_keys(self):
        """Three-word keys (with variant) are 6 bytes."""
        three_word = ['Battery_Events_Percentage',
                      'Sound_Events_SideToneGainChanged',
                      'Service_Events_SubDevicesChanged']
        for name in three_word:
            self.assertEqual(_key_length(name), 6, f"{name} should be 6 bytes")


class TestUnknownPayload(unittest.TestCase):
    """Test handling of unknown payloads."""

    def test_unknown_payload_returns_none(self):
        """Unknown event keys return None."""
        # Random bytes that don't match any known key
        payload = bytes.fromhex('FF FF 00 00 00 00'.replace(' ', ''))
        event = parse_event_payload(payload)
        self.assertIsNone(event)

    def test_decode_event_key_unknown_returns_none(self):
        """decode_event_key returns None for unknown word1."""
        payload = bytes.fromhex('12 00 99 99 04 00'.replace(' ', ''))
        result = decode_event_key(payload)
        self.assertIsNone(result)


class TestEventPayloadSchemas(unittest.TestCase):
    """Verify all EVENT_PAYLOAD entries have matching event classes."""

    def test_all_events_have_schema(self):
        """Every event name in EVENT_PAYLOAD should be parseable."""
        for (w0, w1, var), name in EVENT_KEYS.items():
            if name not in EVENT_PAYLOAD:
                continue
            # Construct a minimal valid payload for this event
            key_len = _key_length(name)
            if key_len == 0:
                continue  # Unknown key
            schema = EVENT_PAYLOAD[name]
            value_len = sum(1 if s == 'u8' else 2 for s in schema)
            payload = bytearray(key_len + value_len)
            # Set correct key bytes
            payload[0:2] = w0.to_bytes(2, 'little')
            payload[2:4] = w1.to_bytes(2, 'little')
            if var is not None:
                payload[4:6] = var.to_bytes(2, 'little')
            event = parse_event_payload(bytes(payload))
            self.assertIsNotNone(event, f"Failed to parse {name}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
