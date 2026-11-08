#!/usr/bin/env python3
"""
Unit tests for the async watch_* event generators on GSA70Device.

Uses a fake hid.device so no hardware is required. Battery/link events are
push-based: these tests replay queued raw reports and assert the generators
yield the correctly-parsed event dataclasses.
"""

import asyncio
import time
import unittest

from gsp670.device import GSA70Device, DeviceDisconnectedError
from gsp670.protocol import crc8, SYNC, MARKER_EVENT_BURST
from gsp670.events import (
    BatteryEvent,
    ChargingEvent,
    LinkEvent,
    SubDevicesEvent,
)

# Event payload keys (key = <word0 u16 LE> <word1 u16 LE> <variant u16 LE>):
BATTERY_PERCENTAGE = bytes.fromhex('12000f000400')   # Battery_Events_Percentage
BATTERY_CHARGING = bytes.fromhex('12000f000300')     # Battery_Events_ChargingChanged
LINK_STATUS = bytes.fromhex('0600f0000100')          # ConnectionStatus
SUBDEVICES = bytes.fromhex('0100f0000100')           # SubDevicesChanged


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


async def _collect(agen, timeout):
    """Drain an async generator into a list."""
    return [item async for item in agen]


class TestWatchEvents(unittest.TestCase):
    """Async watch_* generators yield parsed event dataclasses."""

    def test_not_connected_raises(self):
        """watch_events() raises DeviceDisconnectedError when device is closed."""
        dev = GSA70Device(path=b'/dev/null')
        with self.assertRaises(DeviceDisconnectedError):
            asyncio.run(_collect(dev.watch_events(timeout=0.1), 0))

    def test_watch_events_yields_battery_and_link(self):
        """All parsed push events arrive via watch_events()."""
        reports = [
            _event_raw(BATTERY_PERCENTAGE + b'\x57'),                    # 87 %
            _event_raw(BATTERY_CHARGING + b'\x02\x00'),                  # full
            _event_raw(SUBDEVICES + b'\x01\x00'),                        # 1 linked
            _event_raw(LINK_STATUS + b'\x01\x00'),                       # status 1
        ]
        dev = _connected_device(reports)
        evts = asyncio.run(_collect(dev.watch_events(timeout=0.6), 0))

        kinds = [type(e).__name__ for e in evts]
        self.assertEqual(kinds, ['BatteryEvent', 'ChargingEvent',
                                 'SubDevicesEvent', 'LinkEvent'])
        self.assertEqual(evts[0].level, 87)
        self.assertEqual(evts[1].state, 2)
        self.assertEqual(evts[2].count, 1)
        self.assertEqual(evts[3].status, 1)

    def test_watch_battery_filters_to_battery_only(self):
        """watch_battery() yields BatteryEvent, skipping link events."""
        reports = [
            _event_raw(BATTERY_PERCENTAGE + b'\x2d'),   # 45 %
            _event_raw(LINK_STATUS + b'\x01\x00'),
            _event_raw(BATTERY_PERCENTAGE + b'\x2c'),   # 44 %
        ]
        dev = _connected_device(reports)
        evts = asyncio.run(_collect(dev.watch_battery(timeout=0.6), 0))

        self.assertEqual(len(evts), 2)
        self.assertTrue(all(isinstance(e, BatteryEvent) for e in evts))
        self.assertEqual([e.level for e in evts], [45, 44])

    def test_watch_link_yields_link_and_subdevices(self):
        """watch_link() yields LinkEvent and SubDevicesEvent."""
        reports = [
            _event_raw(SUBDEVICES + b'\x01\x00'),
            _event_raw(BATTERY_PERCENTAGE + b'\x5a'),   # ignored
            _event_raw(LINK_STATUS + b'\x00\x00'),
        ]
        dev = _connected_device(reports)
        evts = asyncio.run(_collect(dev.watch_link(timeout=0.6), 0))

        self.assertEqual(len(evts), 2)
        self.assertIsInstance(evts[0], SubDevicesEvent)
        self.assertIsInstance(evts[1], LinkEvent)
        self.assertEqual(evts[0].count, 1)
        self.assertEqual(evts[1].status, 0)

    def test_watch_events_timeout_terminates(self):
        """watch_events() stops after `timeout` even with no traffic."""
        dev = _connected_device([])
        t0 = time.monotonic()
        evts = asyncio.run(_collect(dev.watch_events(timeout=0.25), 0))
        dt = time.monotonic() - t0
        self.assertEqual(evts, [])
        self.assertGreaterEqual(dt, 0.2)


if __name__ == '__main__':
    unittest.main()