#!/usr/bin/env python3
"""
Tests that exercise the protocol against recorded HID frames.

These run without any hardware: the frames in ``tests/fixtures/`` are used
as-is, and the encoder is checked for round-trip stability against them.
"""

import json
import unittest
from pathlib import Path

from gsp670.protocol import (
    MARKER_DEVICE,
    MARKER_HOST,
    classify,
    crc8,
    frame,
    validate_frame,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "hid_frames.json"

# Wire layout of a 107-byte output report:
#   [0]    report id (0x01)
#   [1..4] sync (EB FE 01 00)
#   [5..6] marker
#   [7..8] opcode LE
#   [9..10] payload length LE
#   [11]   CRC-8(payload)
#   [12]   filler
#   [13..] payload
OFFSET_MARKER = 5
OFFSET_OPCODE = 7
OFFSET_CRC = 11


def load_fixtures():
    with open(FIXTURES, "r", encoding="utf-8") as fh:
        return json.load(fh)


class TestRecordedFrames(unittest.TestCase):
    """Validate the protocol against recorded device frames."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_fixtures()
        cls.frames = cls.fixtures["frames"]

    def test_fixtures_file_exists(self):
        self.assertTrue(FIXTURES.is_file(), f"missing fixtures: {FIXTURES}")

    def test_secom_frames_are_valid(self):
        """Every recorded SECOM reply frame passes the protocol validator."""
        for name, hexdata in self.frames.items():
            if not name.startswith("secom_"):
                continue
            with self.subTest(frame=name):
                parsed = classify(bytes.fromhex(hexdata))
                ok, reason = validate_frame(parsed)
                self.assertTrue(ok, f"{name} failed validation: {reason}")

    def test_secom_replies_carry_the_device_marker(self):
        """A recorded reply uses the device marker (0x10 0x01)."""
        for name, hexdata in self.frames.items():
            if not name.startswith("secom_reply"):
                continue
            with self.subTest(frame=name):
                data = bytes.fromhex(hexdata)
                self.assertEqual(
                    data[OFFSET_MARKER:OFFSET_MARKER + 2], MARKER_DEVICE,
                    f"{name} does not carry the device marker",
                )

    def test_secom_request_carries_the_host_marker(self):
        """A recorded request uses the host marker (0x04 0x00)."""
        data = bytes.fromhex(self.frames["secom_request_device_name"])
        self.assertEqual(data[OFFSET_MARKER:OFFSET_MARKER + 2], MARKER_HOST)

    def test_secom_opcodes_round_trip(self):
        """The opcode field of a recorded frame matches its fixture name."""
        expected = {
            "secom_reply_firmware_version": 0x00,
            "secom_reply_serial": 0x01,
            "secom_reply_device_name": 0x02,
            "secom_reply_address": 0x03,
        }
        for name, opcode in expected.items():
            with self.subTest(frame=name):
                data = bytes.fromhex(self.frames[name])
                self.assertEqual(
                    int.from_bytes(data[OFFSET_OPCODE:OFFSET_OPCODE + 2], "little"),
                    opcode,
                )

    def test_event_frames_are_recognised(self):
        """The recorded event payloads classify as events, not as replies."""
        for name in ("event_burst_link_change", "event_poll"):
            with self.subTest(frame=name):
                parsed = classify(bytes.fromhex(self.frames[name]))
                self.assertIn(
                    parsed.kind, ("event", "event_burst", "event_poll"),
                    f"{name} classified as {parsed.kind}",
                )

    def test_subreply_frames_are_recognised(self):
        """The recorded sub-device replies classify as such."""
        for name in ("subreply_0x04", "subreply_0x05"):
            with self.subTest(frame=name):
                parsed = classify(bytes.fromhex(self.frames[name]))
                self.assertIsNotNone(parsed.kind, f"{name} was not classified")
                self.assertNotEqual(parsed.kind, "short")

    def test_encoder_round_trip_is_stable(self):
        """Encoding a SECOM request and decoding it back is lossless."""
        for opcode in (0x00, 0x01, 0x02, 0x03):
            with self.subTest(opcode=opcode):
                data = frame(opcode, b"")
                self.assertEqual(len(data), 107)
                # The CRC byte covers the payload we sent.
                self.assertEqual(data[OFFSET_CRC], crc8(b""))
                # The encoder must reproduce the recorded request byte for byte.
                if opcode == 0x02:
                    self.assertEqual(
                        data.hex(),
                        self.frames["secom_request_device_name"],
                    )

    def test_encoder_round_trips_through_the_decoder(self):
        """A frame built by frame() decodes back to the same opcode."""
        for opcode in (0x00, 0x01, 0x02, 0x03, 0x0E, 0x4F12):
            with self.subTest(opcode=opcode):
                parsed = classify(frame(opcode, b""))
                self.assertEqual(parsed.opcode, opcode)
                self.assertEqual(parsed.size, 0)
                self.assertEqual(parsed.crc, crc8(b""))

    def test_frame_length_is_constant(self):
        """All output reports are 107 bytes (report id + 106 data bytes)."""
        for name, hexdata in self.frames.items():
            if not name.startswith("secom_"):
                continue
            with self.subTest(frame=name):
                self.assertEqual(len(bytes.fromhex(hexdata)), 107)


if __name__ == "__main__":
    unittest.main()
