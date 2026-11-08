#!/usr/bin/env python3
"""
Unit tests for the CLI battery/link watch helpers (_run_watch_battery).

Regression coverage for the poll-fallback bug: the fallback previously lived
inside the async-for body, so it never ran when the dongle pushed zero events.
"""

import asyncio
import io
import unittest
from contextlib import redirect_stdout

from gsp670.cli import _run_watch_battery
from gsp670.protocol import MARKER_EVENT_BURST, SYNC, classify, crc8

BATTERY_PERCENTAGE = bytes.fromhex('12000f000400')  # u8 level
SUBDEVICES = bytes.fromhex('0100f0000100')          # u16 count


def _event_raw(payload: bytes) -> bytes:
    """Build a real-shaped unsolicited event report for `payload`."""
    raw = bytes([0x01]) + SYNC + MARKER_EVENT_BURST + b'\x04\x00'
    raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
    return raw + b'\x00' * (107 - len(raw))


class _FakeWatchDev:
    """Fake GSA70Device: queue of raw reports + scripted poll results."""

    def __init__(self, raws=(), poll_returns=()):
        self._raws = list(raws)
        self.poll_returns = list(poll_returns)
        self.poll_calls = 0

    def read(self, timeout_ms):
        return classify(self._raws.pop(0)) if self._raws else None

    def get_battery_percentage(self):
        self.poll_calls += 1
        return self.poll_returns.pop(0) if self.poll_returns else None


def _run_battery(dev, timeout=0.18, poll_interval=0.05):
    out = io.StringIO()
    with redirect_stdout(out):
        asyncio.run(_run_watch_battery(dev, timeout=timeout,
                                       poll_interval=poll_interval))
    return out.getvalue()


class TestRunWatchBattery(unittest.TestCase):
    def test_poll_fallback_fires_with_zero_events(self):
        """Regression: the (polled) fallback must run even with no traffic."""
        dev = _FakeWatchDev(poll_returns=[66])
        text = _run_battery(dev)
        self.assertIn('Battery (polled): 66%', text)
        self.assertGreaterEqual(dev.poll_calls, 1)

    def test_poll_reports_unlinked_with_no_value(self):
        """Fallback prints the 'not linked?' diagnostic when GET returns None."""
        dev = _FakeWatchDev(poll_returns=[None])
        text = _run_battery(dev)
        self.assertIn('no response (headset not linked?)', text)

    def test_battery_event_interleaves_with_poll(self):
        """Pushed BatteryEvent prints a timestamped line (no 'polled')."""
        dev = _FakeWatchDev(raws=[_event_raw(BATTERY_PERCENTAGE + b'\x57')],
                            poll_returns=[66])
        text = _run_battery(dev)
        self.assertIn('Battery: 87%', text)          # 0x57 = 87 %
        self.assertNotIn('(polled): 87%', text)

    def test_subdevices_event_prints_link_hint(self):
        """SubDevicesEvent in battery mode surfaces the link state."""
        dev = _FakeWatchDev(raws=[_event_raw(SUBDEVICES + b'\x01\x00')])
        text = _run_battery(dev)
        self.assertIn('LINKED (sub-devices: 1)', text)


if __name__ == '__main__':
    unittest.main()
