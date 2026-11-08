#!/usr/bin/env python3
"""
Unit tests for the Rtx FWU channel helpers (Phase 3 recovery).

FWU travels on the Rtx datagram channel (64-byte ``0x58`` reports,
``0xEE``-padded), *not* SECOM ``04 00`` — see
``analysis/session-handshake.md`` section 6.3/6.5.
"""

import unittest

from gsp670.protocol import (
    RTX_FWU_IDS,
    RTX_PAD,
    RTX_REPORT_PREFIX,
    RTX_REPORT_SIZE,
    rtx_fwu_enable,
    rtx_fwu_packet,
)


class TestRtxFwuPacket(unittest.TestCase):
    """Wire shape of the Rtx datagram reports."""

    def test_enable_report_shape(self):
        report = rtx_fwu_enable(0x00, 0x00)
        self.assertEqual(len(report), RTX_REPORT_SIZE)
        self.assertEqual(report[0], RTX_REPORT_PREFIX)
        # request id 0x4f00 LE, then A B, then EE padding
        self.assertEqual(report[1:5], bytes.fromhex('004F0000'))
        self.assertTrue(all(b == RTX_PAD for b in report[5:]))

    def test_nonzero_bytes(self):
        report = rtx_fwu_enable(0x01, 0x03)
        self.assertEqual(report[1:5], bytes.fromhex('004F0103'))

    def test_custom_payload(self):
        report = rtx_fwu_packet(bytes.fromhex('00 4f 01 03'))
        self.assertEqual(report[:5], bytes.fromhex('58 00 4f 01 03'))

    def test_payload_too_large(self):
        with self.assertRaises(ValueError):
            rtx_fwu_packet(b'\x00' * RTX_REPORT_SIZE)

    def test_id_table(self):
        self.assertEqual(RTX_FWU_IDS['enable'], 0x4F00)
        self.assertEqual(RTX_FWU_IDS['update'], 0x4F03)
        self.assertEqual(RTX_FWU_IDS['keepalive'], 0xF066)


if __name__ == '__main__':
    unittest.main()