#!/usr/bin/env python3
"""
Unit tests for unsolicited device->host event delivery in device.py.

Uses a fake hid.device so no hardware is required.
"""

import unittest

from gsp670.device import GSA70Device
from gsp670.protocol import crc8, SYNC, MARKER_ACK, MARKER_EVENT_BURST


def _event_raw(payload: bytes) -> bytes:
    """Build a real-shaped unsolicited event report for `payload`."""
    raw = bytes([0x01]) + SYNC + MARKER_EVENT_BURST + b'\x04\x00'
    raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
    return raw + b'\x00' * (107 - len(raw))


class _FakeHid:
    """Minimal stand-in for hid.device that replays queued raw reports."""

    def __init__(self, reports):
        self._reports = list(reports)

    def read(self, size, timeout_ms):
        return self._reports.pop(0) if self._reports else []


def _connected_device(reports):
    dev = GSA70Device(path=b'/dev/null')
    dev._dev = _FakeHid(reports)
    dev._connected = True
    return dev


class TestEventDelivery(unittest.TestCase):
    """Test that read() dispatches frames to registered callbacks."""

    PAYLOAD = bytes.fromhex('1d00f000010001007400')

    def test_event_callback_receives_event(self):
        """on_event() fires with the parsed event frame."""
        dev = _connected_device([_event_raw(self.PAYLOAD)])
        seen = []
        dev.on_event(seen.append)

        f = dev.read()

        self.assertEqual(f.kind, 'event')
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].payload, self.PAYLOAD)
        self.assertEqual(seen[0].opcode, 0x0004)

    def test_read_callback_receives_all_frames(self):
        """add_read_callback() fires for every frame."""
        dev = _connected_device([_event_raw(self.PAYLOAD)])
        seen = []
        dev.add_read_callback(seen.append)

        dev.read()

        self.assertEqual(len(seen), 1)

    def test_on_event_ignores_non_events(self):
        """on_event() must not fire for ACK frames."""
        ack = (bytes([0x01]) + SYNC + MARKER_ACK + b'\x00\x00'
               + b'\x00\x00' + b'\xff' + b'\x00')
        ack += b'\x00' * (107 - len(ack))
        dev = _connected_device([ack])
        seen = []
        dev.on_event(seen.append)

        f = dev.read()

        self.assertEqual(f.kind, 'ack')
        self.assertEqual(seen, [])

    def test_callback_exception_does_not_propagate(self):
        """A throwing listener must never break protocol I/O."""
        dev = _connected_device([_event_raw(self.PAYLOAD)])

        def boom(_f):
            raise RuntimeError('boom')

        dev.on_event(boom)

        f = dev.read()  # must not raise

        self.assertEqual(f.kind, 'event')

    def test_listen_zero_seconds_is_empty(self):
        """listen(0) yields nothing and returns immediately."""
        dev = _connected_device([])
        self.assertEqual(list(dev.listen(0)), [])


if __name__ == '__main__':
    unittest.main()
