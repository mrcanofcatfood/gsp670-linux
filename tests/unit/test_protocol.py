#!/usr/bin/env python3
"""
Unit tests for protocol.py - Capricorn protocol implementation.

Tests frame encoding/decoding, CRC-8 calculation, ACK/NAK classification,
and opcode transform.
"""

import unittest

from gsp670.protocol import (
    MARKER_ACK,
    MARKER_DEVICE,
    MARKER_EVENT_BURST,
    MARKER_EVENT_POLL,
    MARKER_HOST,
    MARKER_NAK,
    SYNC,
    classify,
    crc8,
    expected_reply_opcode,
    frame,
    marker_transform,
    secom_value,
    validate_frame,
)


class TestCRC8(unittest.TestCase):
    """Test CRC-8 calculation."""

    def test_crc8_empty(self):
        """CRC-8 of empty data should be 0xFF (initial value)."""
        self.assertEqual(crc8(b''), 0xFF)

    def test_crc8_known_values(self):
        """Test CRC-8 with known reference values."""
        # Polynomial 0x07, init 0xFF
        self.assertEqual(crc8(b'\x00'), 0xF3)
        self.assertEqual(crc8(b'\xFF'), 0x00)
        self.assertEqual(crc8(b'\x01\x02\x03'), 0x63)

    def test_crc8_init_param(self):
        """Test CRC-8 with custom init value."""
        # With init=0x00
        self.assertEqual(crc8(b'\x00', init=0x00), 0x00)
        self.assertEqual(crc8(b'\xFF', init=0x00), 0xF3)


class TestFrameEncoding(unittest.TestCase):
    """Test frame encoding."""

    def test_frame_minimal(self):
        """Test encoding a frame with no payload."""
        data = frame(0x4F12, b'')

        # Should be 107 bytes (1 report id + 106 data)
        self.assertEqual(len(data), 107)

        # Report ID should be 0x01
        self.assertEqual(data[0], 0x01)

        # Sync bytes at offset 1-4
        self.assertEqual(data[1:5], SYNC)

        # Marker at offset 5-6
        self.assertEqual(data[5:7], MARKER_HOST)

        # Opcode at offset 7-8 (little endian)
        self.assertEqual(data[7:9], b'\x12\x4F')

        # Size at offset 9-10 (little endian)
        self.assertEqual(data[9:11], b'\x00\x00')

    def test_frame_with_payload(self):
        """Test encoding a frame with payload."""
        payload = b'\x01\x02\x03\x04\x05'
        data = frame(0x4F12, payload)

        # Size should be 5
        self.assertEqual(data[9:11], b'\x05\x00')

        # CRC should be computed over payload only
        expected_crc = crc8(payload)
        self.assertEqual(data[11], expected_crc)

        # Payload at offset 13+
        self.assertEqual(data[13:18], payload)

    def test_frame_payload_too_long(self):
        """Test that oversized payload raises assertion."""
        # Max payload is RPT - 12 = 94 bytes
        with self.assertRaises(AssertionError):
            frame(0x4F12, b'\x00' * 95)


class TestFrameClassification(unittest.TestCase):
    """Test frame classification (ACK/NAK/other)."""

    def test_classify_ack(self):
        """Test ACK frame classification."""
        # ACK marker is 05 30
        raw = bytes([0x01]) + SYNC + MARKER_ACK + b'\x12\x4F' + b'\x00\x00' + b'\xFF' + b'\x00'
        raw += b'\x00' * 94  # Padding

        f = classify(raw)
        self.assertEqual(f.kind, 'ack')

    def test_classify_nak(self):
        """Test NAK frame classification."""
        # NAK marker is 04 10
        raw = bytes([0x01]) + SYNC + MARKER_NAK + b'\x00\x00' + b'\x00\x00' + b'\xFF' + b'\x00'
        raw += b'\x00' * 94

        f = classify(raw)
        self.assertEqual(f.kind, 'nak')

    def test_classify_other(self):
        """Test device frame classification."""
        # Device marker is 10 01
        raw = bytes([0x01]) + SYNC + MARKER_DEVICE + b'\x00\x4F' + b'\x00\x00' + b'\x00' + b'\x00'
        raw += b'\x00' * 94

        f = classify(raw)
        self.assertEqual(f.kind, 'other')

    def test_classify_short(self):
        """Test short frame classification."""
        # Less than 13 bytes is "short"
        raw = bytes([0x01, 0x02, 0x03])
        f = classify(raw)
        self.assertEqual(f.kind, 'short')

    def test_classify_event_burst(self):
        """Real unsolicited device event captured on the dongle (2026-10-12).

        Marker ``00 01``, opcode field 0x0004, 10-byte payload.  CRC-8 over the
        payload must validate.
        """
        payload = bytes.fromhex('1d00f000010001007400')
        raw = bytes([0x01]) + SYNC + MARKER_EVENT_BURST + b'\x04\x00'
        raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
        raw += b'\x00' * (107 - len(raw))

        f = classify(raw)
        self.assertEqual(f.kind, 'event')
        self.assertEqual(f.opcode, 0x0004)
        self.assertEqual(f.size, 10)
        self.assertEqual(f.payload, payload)
        self.assertEqual(validate_frame(f), (True, ''))

    def test_classify_event_poll(self):
        """Recurring ``ff 01`` device event frame."""
        payload = bytes.fromhex('0800f00003000100000000000000')
        raw = bytes([0x01]) + SYNC + MARKER_EVENT_POLL + b'\x04\x00'
        raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
        raw += b'\x00' * (107 - len(raw))

        f = classify(raw)
        self.assertEqual(f.kind, 'event')
        self.assertEqual(f.opcode, 0x0004)
        self.assertEqual(f.size, 14)
        self.assertEqual(validate_frame(f), (True, ''))

    def test_classify_subreply_0x04(self):
        """0x04 sub-device reply: marker 04 00, class 0x0004, value 00 00."""
        payload = bytes.fromhex('010009000000')
        raw = bytes([0x01]) + SYNC + MARKER_HOST + b'\x04\x00'
        raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
        raw += b'\x00' * (107 - len(raw))

        f = classify(raw)
        self.assertEqual(f.kind, 'subreply')
        self.assertEqual(f.opcode, 0x0004)
        self.assertEqual(f.size, 6)
        self.assertEqual(validate_frame(f), (True, ''))
        self.assertEqual(secom_value(f), b'\x00\x00')

    def test_classify_subreply_0x05(self):
        """0x05 sub-device reply: marker 04 00, class 0x0004, echo only."""
        payload = bytes.fromhex('01000a00')
        raw = bytes([0x01]) + SYNC + MARKER_HOST + b'\x04\x00'
        raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
        raw += b'\x00' * (107 - len(raw))

        f = classify(raw)
        self.assertEqual(f.kind, 'subreply')
        self.assertEqual(f.opcode, 0x0004)
        self.assertEqual(validate_frame(f), (True, ''))

    def test_classify_data_reply_stays_other(self):
        """A plain data reply stays 'other' (marker 04 00, class 0x0000)."""
        payload = bytes.fromhex('0100030003000e000200')  # fw 3.14.2
        raw = bytes([0x01]) + SYNC + MARKER_HOST + b'\x00\x00'
        raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
        raw += b'\x00' * (107 - len(raw))

        f = classify(raw)
        self.assertEqual(f.kind, 'other')
        self.assertEqual(f.opcode, 0x0000)
        self.assertEqual(secom_value(f), bytes.fromhex('03000e000200'))


class TestOpcodeTransform(unittest.TestCase):
    """Test opcode transform (request -> reply)."""

    def test_opcode_transform_4F12(self):
        """Test GET_FEATURES opcode transform."""
        # 0x4F12 -> expected reply opcode
        # Transform: (req & 0xFF00) | ((req & 0xFF) >> 2)
        expected = expected_reply_opcode(0x4F12)
        self.assertEqual(expected, 0x4F04)

    def test_opcode_transform_4F0C(self):
        """Test STATUS_IND opcode transform."""
        expected = expected_reply_opcode(0x4F0C)
        self.assertEqual(expected, 0x4F03)

    def test_opcode_transform_roundtrip(self):
        """Test that some opcodes transform correctly."""
        test_cases = [
            (0x4F00, 0x4F00),  # FWU_ENABLE
            (0x4F01, 0x4F00),  # FWU_ENABLE_CFM
            (0x4F10, 0x4F04),  # FWU_SET_FEATURES
            (0x4F11, 0x4F04),  # FWU_SET_FEATURES_CFM
        ]
        for req, expected in test_cases:
            with self.subTest(req=req):
                self.assertEqual(expected_reply_opcode(req), expected)


class TestMarkerTransform(unittest.TestCase):
    """Test marker transformation."""

    def test_marker_host_to_device(self):
        """Test host marker to device marker transformation."""
        # 04 00 -> 05 30 (ACK)
        self.assertEqual(marker_transform(MARKER_HOST), MARKER_ACK)

    def test_marker_device(self):
        """Test device marker transformation."""
        # 10 01 -> 11 31
        expected = bytes([MARKER_DEVICE[0] + 1, MARKER_DEVICE[1] + 0x30])
        self.assertEqual(marker_transform(MARKER_DEVICE), expected)

    def test_marker_invalid_length(self):
        """Test marker with invalid length raises ValueError."""
        with self.assertRaises(ValueError):
            marker_transform(b'\x00')
        with self.assertRaises(ValueError):
            marker_transform(b'\x00\x01\x02')


class TestValidateFrame(unittest.TestCase):
    """Test frame validation."""

    def test_validate_valid_ack_frame(self):
        """Test validation of a valid ACK frame."""
        payload = b'\x01\x02\x03'
        data = frame(0x4F12, payload)
        f = classify(data)

        # Manually set kind to ack for validation
        f.kind = 'ack'

        is_valid, msg = validate_frame(f)
        self.assertTrue(is_valid)
        self.assertEqual(msg, '')

    def test_validate_invalid_sync(self):
        """Test validation fails with invalid sync."""
        raw = bytes([0x01, 0x00, 0x01, 0x00, 0x00]) + MARKER_ACK + b'\x00\x00' + b'\x00\x00' + b'\xFF' + b'\x00'
        raw += b'\x00' * 94
        f = classify(raw)

        is_valid, msg = validate_frame(f)
        self.assertFalse(is_valid)
        self.assertIn('sync', msg.lower())


if __name__ == '__main__':
    unittest.main()
