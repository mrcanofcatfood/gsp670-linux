#!/usr/bin/env python3
"""
Unit tests for the recovered Modi device -> host event key decoder.

The keys were recovered statically from the GSA 70 service image dispatcher
``FUN_00643b10``; see ``analysis/session-handshake.md`` section 6.1.

Key shape: ``<word0 u16 LE> <word1 u16 LE> [<variant u16 LE>]`` where ``word1``
is ``0x00F0`` for most notifications but varies by source component.
"""

import unittest

from gsp670.protocol import (
    EVENT_NAMESPACE,
    EVENT_WORDS,
    EVENT_KEYS,
    EVENT_PAYLOAD,
    decode_event_key,
    format_event_key,
)


class TestDecodeEventKey(unittest.TestCase):
    """Decode known, unknown and non-event payloads."""

    def test_battery_percentage(self):
        # Battery uses word1 0x000F, not 0x00F0.
        self.assertEqual(
            decode_event_key(bytes.fromhex('12000f000400')),
            ('Battery_Events_Percentage', 0x12, 0x000F, 4),
        )

    def test_battery_charging(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('12000f000300')),
            ('Battery_Events_ChargingChanged', 0x12, 0x000F, 3),
        )

    def test_virtual_button(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('0800f0000300')),
            ('Input_Events_VirtualButtonEvent', 0x08, 0x00F0, 3),
        )

    def test_component_status_change(self):
        # word0 0x0023 (previously mis-labelled as the ANC state change).
        self.assertEqual(
            decode_event_key(bytes.fromhex('2300f0000100')),
            ('Component_Events_StatusChange', 0x23, 0x00F0, 1),
        )

    def test_two_word_anc_state(self):
        # Two-word key: no variant, word1 0x0007.
        self.assertEqual(
            decode_event_key(bytes.fromhex('170007000100')),
            ('ANC_AdaptiveNoiseCancelationStateChanged', 0x17, 0x0007, None),
        )

    def test_two_word_speaker_mic_optimized(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('10001d0001')),
            ('SpeakerMic_OptimizedMicSettingChanged', 0x10, 0x001D, None),
        )

    def test_two_word_tone_audio_prompts(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('070007000100')),
            ('Tone_AudioPromptsModeChanged', 0x07, 0x0007, None),
        )

    def test_two_word_device_pdl(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('0600290001')),
            ('Device_DevicePdlModeChangeIndication', 0x06, 0x0029, None),
        )

    def test_connection_family(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('0600f0000400')),
            ('Device_ConnectionEvents_PairingStatusIndication', 0x06, 0x00F0, 4),
        )
        self.assertEqual(
            decode_event_key(bytes.fromhex('0600f0000700')),
            ('Device_ConnectionEvents_MultipointConnectionInScoStatus', 0x06, 0x00F0, 7),
        )

    def test_service_family(self):
        self.assertEqual(
            decode_event_key(bytes.fromhex('0100f0000300')),
            ('Service_Events_AutoPowerOffTimerStatus', 0x01, 0x00F0, 3),
        )

    def test_unknown_variant_returns_none_name(self):
        name, word0, word1, variant = decode_event_key(bytes.fromhex('12000f000900'))
        self.assertIsNone(name)
        self.assertEqual((word0, word1, variant), (0x12, 0x000F, 9))

    def test_non_event_word(self):
        # The legacy Capricorn battery GET payload (0x0e) has no event word.
        self.assertIsNone(decode_event_key(bytes.fromhex('12000300')))

    def test_short_payload(self):
        self.assertIsNone(decode_event_key(bytes.fromhex('1200')))

    def test_live_capture_key(self):
        # Captured link/button frame body: 1d 00 f0 00 01 00 01 00 74 00
        name, word0, word1, variant = decode_event_key(
            bytes.fromhex('1d00f000010001007400')
        )
        self.assertIsNone(name)
        self.assertEqual((word0, word1, variant), (0x1D, 0x00F0, 1))

    def test_namespace_constant(self):
        self.assertEqual(EVENT_NAMESPACE, 0x00F0)
        self.assertIn(EVENT_NAMESPACE, EVENT_WORDS)

    def test_tables_are_non_empty(self):
        self.assertIn((0x0012, 0x000F, 4), EVENT_KEYS)
        self.assertIn((0x0023, 0x00F0, 1), EVENT_KEYS)
        self.assertIn((0x0017, 0x0007, None), EVENT_KEYS)

    def test_payload_schema_covers_every_key(self):
        for name in EVENT_KEYS.values():
            self.assertIn(name, EVENT_PAYLOAD, name)

    def test_payload_schemas(self):
        self.assertEqual(EVENT_PAYLOAD['Battery_Events_Percentage'], ('u8',))
        self.assertEqual(EVENT_PAYLOAD['Battery_Events_ChargingChanged'], ('u16',))
        self.assertEqual(
            EVENT_PAYLOAD['Input_Events_VirtualButtonEvent'],
            ('u8', 'u8', 'u8', 'u8'),
        )
        self.assertEqual(
            EVENT_PAYLOAD['Component_Events_StatusChange'],
            ('u8', 'u16'),
        )


class TestFormatEventKey(unittest.TestCase):
    """Human-readable rendering of recovered event keys."""

    def test_known_event(self):
        self.assertEqual(
            format_event_key(bytes.fromhex('12000f000400')),
            'Battery_Events_Percentage (12 00 0f 00 04 00)',
        )

    def test_frame_event_name_property(self):
        from gsp670.protocol import Frame
        frame = Frame(
            report_id=0x01, sync=b'\xeb\xfe\x01\x00', marker=b'\x00\x01',
            opcode=0x0004, size=6, crc=0, filler=0,
            payload=bytes.fromhex('12000f000400'), tail=b'', kind='event',
        )
        self.assertEqual(
            frame.event_name,
            'Battery_Events_Percentage (12 00 0f 00 04 00)',
        )
        frame.payload = bytes.fromhex('12000300')
        self.assertIsNone(frame.event_name)

    def test_two_word_event(self):
        self.assertEqual(
            format_event_key(bytes.fromhex('170007000100')),
            'ANC_AdaptiveNoiseCancelationStateChanged (17 00 07 00)',
        )

    def test_unknown_event_word_key(self):
        self.assertEqual(
            format_event_key(bytes.fromhex('12000f000900')),
            'unknown event (12 00 0f 00 09 00)',
        )

    def test_non_event_word(self):
        self.assertIsNone(format_event_key(bytes.fromhex('12000300')))

    def test_live_capture_key(self):
        self.assertEqual(
            format_event_key(bytes.fromhex('1d00f000010001007400')),
            'unknown event (1d 00 f0 00 01 00)',
        )


if __name__ == '__main__':
    unittest.main()
