#!/usr/bin/env python3
"""
Unit tests for the GSP 670 D-Bus service event draining (_drain_events).

Uses a real session bus if available (skips otherwise) and a fake hid.device,
so the event->signal mapping can be verified without hardware. Public signal
methods are overridden to record emissions.
"""

import unittest

import dbus
import dbus.mainloop.glib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

from gsp670.dbus_service import Gsp670DBusService
from gsp670.device import GSA70Device
from gsp670.protocol import crc8, SYNC, MARKER_EVENT_BURST

# Event payload keys:
BATTERY_PERCENTAGE = bytes.fromhex('12000f000400')   # u8 level
BATTERY_CHARGING = bytes.fromhex('12000f000300')     # u16 state
SIDETONE = bytes.fromhex('0a00f0000200')             # u16 level
SUBDEVICES = bytes.fromhex('0100f0000100')           # u16 count


def _event_raw(payload: bytes) -> bytes:
    """Build a real-shaped unsolicited event report for `payload`."""
    raw = bytes([0x01]) + SYNC + MARKER_EVENT_BURST + b'\x04\x00'
    raw += bytes([len(payload), 0x00, crc8(payload), 0x00]) + payload
    return raw + b'\x00' * (107 - len(raw))


class _FakeHid:
    def __init__(self, reports):
        self._reports = list(reports)

    def read(self, size, timeout_ms):
        return self._reports.pop(0) if self._reports else []


class _RecordingService(Gsp670DBusService):
    """Record signal calls instead of emitting on the bus."""

    def __init__(self, bus):
        super().__init__(bus)
        self.signals = []

    def BatteryChanged(self, level, charging):
        self.signals.append(('BatteryChanged', level, charging))

    def SidetoneChanged(self, level):
        self.signals.append(('SidetoneChanged', level))

    def LinkChanged(self, connected):
        self.signals.append(('LinkChanged', connected))


def _mock_device(reports):
    dev = GSA70Device(path=b'/dev/null')
    dev._dev = _FakeHid(reports)
    dev._connected = True
    return dev


def _session_bus():
    try:
        return dbus.SessionBus()
    except Exception:
        return None


@unittest.skipUnless(_session_bus(), "no D-Bus session bus available")
class TestDBusEventDrain(unittest.TestCase):
    """_drain_events maps pushed events to D-Bus signals."""

    @classmethod
    def setUpClass(cls):
        cls.bus = _session_bus()
        cls.service = _RecordingService(cls.bus)

    def setUp(self):
        self.service.signals.clear()
        self.service._device = None
        self.service._last_battery = -1
        self.service._last_charging = False
        self.service._last_sidetone = -1
        self.service._last_link = False

    def test_battery_percentage_event_emits_signal(self):
        """BatteryEvent -> BatteryChanged(level, charging)."""
        self.service._device = _mock_device([_event_raw(BATTERY_PERCENTAGE + b'\x4b')])

        self.service._drain_events()

        self.assertIn(('BatteryChanged', 75, False), self.service.signals)
        self.assertEqual(self.service._last_battery, 75)

    def test_charging_event_uses_last_level(self):
        """ChargingEvent -> BatteryChanged with cached level, charging=True."""
        service = self.service
        service._device = _mock_device([
            _event_raw(BATTERY_PERCENTAGE + b'\x32'),   # 50%
            _event_raw(BATTERY_CHARGING + b'\x01\x00'),  # charging
        ])

        service._drain_events()

        self.assertEqual(service._last_battery, 50)
        self.assertTrue(service._last_charging)
        self.assertIn(('BatteryChanged', 50, True), service.signals)

    def test_sidetone_event(self):
        """SidetoneEvent -> SidetoneChanged(level & 0xFF)."""
        self.service._device = _mock_device([_event_raw(SIDETONE + b'\x80\x00')])

        self.service._drain_events()

        self.assertIn(('SidetoneChanged', 0x80), self.service.signals)
        self.assertEqual(self.service._last_sidetone, 0x80)

    def test_subdevices_event_emits_link(self):
        """SubDevicesEvent count>0 -> LinkChanged(True)."""
        self.service._device = _mock_device([_event_raw(SUBDEVICES + b'\x01\x00')])

        self.service._drain_events()

        self.assertIn(('LinkChanged', True), self.service.signals)
        self.assertTrue(self.service._last_link)

    def test_no_duplicate_signals_on_unchanged(self):
        """Second identical event does not re-emit (change detection)."""
        service = self.service
        service._device = _mock_device([
            _event_raw(BATTERY_PERCENTAGE + b'\x4b'),
            _event_raw(BATTERY_PERCENTAGE + b'\x4b'),  # same level
        ])

        service._drain_events()
        service._drain_events()

        battery_sigs = [s for s in service.signals if s[0] == 'BatteryChanged']
        self.assertEqual(len(battery_sigs), 1)

    def test_charging_event_without_level_skipped(self):
        """ChargingEvent alone does not emit (no known level)."""
        self.service._device = _mock_device([_event_raw(BATTERY_CHARGING + b'\x01\x00')])

        self.service._drain_events()

        self.assertEqual(self.service.signals, [])

    def test_empty_reports_no_signals(self):
        """No queued reports -> no signals, no errors."""
        self.service._device = _mock_device([])

        self.service._drain_events()

        self.assertEqual(self.service.signals, [])


if __name__ == '__main__':
    unittest.main()