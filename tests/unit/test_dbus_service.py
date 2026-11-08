#!/usr/bin/env python3
"""
Unit tests for the extended GSP 670 D-Bus service.

Covers the verified-control methods added for the device panel (auto power
off, latency, device identity, sub-devices) and the new change-detection
signals. Uses a real session bus when available and a fake device, so no
hardware is required.
"""

import unittest
from unittest import mock

import dbus
import dbus.mainloop.glib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

from gsp670.config import DeviceConfig
from gsp670.dbus_service import Gsp670DBusService


class _FakeDevice:
    """Duck-typed GSA70Device with canned values and selective failures."""

    def __init__(self, **values):
        self.is_connected = True
        self.values = {
            'sidetone': 40,
            'noise_reduction': 2,
            'auto_power_off': 30,
            'latency': 1,
            'subdevices': 1,
            'name': 'EPOS GSA 70',
            'serial': 'ABC123',
            'firmware': '3.14.2',
        }
        self.values.update(values)
        self.reports = []
        self.raise_on = set()

    def _get(self, key):
        if key in self.raise_on:
            raise RuntimeError(key)
        return self.values.get(key)

    def get_sidetone(self):
        return self._get('sidetone')

    def get_noise_reduction(self):
        return self._get('noise_reduction')

    def get_auto_power_off(self):
        return self._get('auto_power_off')

    def get_latency(self):
        return self._get('latency')

    def get_subdevices_connected(self):
        return self._get('subdevices')

    def get_device_name(self):
        return self._get('name')

    def get_serial_number(self):
        return self._get('serial')

    def get_firmware_version(self):
        return self._get('firmware')

    def set_sidetone(self, value):
        if 'set_sidetone' in self.raise_on:
            raise RuntimeError('set_sidetone')
        self.values['sidetone'] = value
        return True

    def set_noise_reduction(self, value):
        self.values['noise_reduction'] = value
        return True

    def set_auto_power_off(self, value):
        self.values['auto_power_off'] = value
        return True

    def read(self, timeout_ms=100):
        return self.reports.pop(0) if self.reports else None


class _RecordingService(Gsp670DBusService):
    """Record signal emissions instead of putting them on the bus."""

    def __init__(self, bus):
        super().__init__(bus)
        self.signals = []

    def BatteryChanged(self, level, charging):
        self.signals.append(('BatteryChanged', level, charging))

    def SidetoneChanged(self, level):
        self.signals.append(('SidetoneChanged', level))

    def NoiseReductionChanged(self, level):
        self.signals.append(('NoiseReductionChanged', level))

    def AutoPowerOffChanged(self, level):
        self.signals.append(('AutoPowerOffChanged', level))

    def SubDevicesChanged(self, count):
        self.signals.append(('SubDevicesChanged', count))

    def DeviceInfoChanged(self):
        self.signals.append(('DeviceInfoChanged',))

    def LinkChanged(self, connected):
        self.signals.append(('LinkChanged', connected))


def _session_bus():
    # Use a private connection so this module's object-path registration does
    # not collide with other D-Bus tests sharing the session bus.
    try:
        return dbus.bus.BusConnection(dbus.bus.BUS_SESSION)
    except Exception:
        return None


@unittest.skipUnless(_session_bus(), "no D-Bus session bus available")
class TestDBusServiceControls(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.bus = _session_bus()
        cls.service = _RecordingService(cls.bus)

    def setUp(self):
        self.service = self.__class__.service
        self.service.signals.clear()
        self.service._device = None
        self.service._last_sidetone = -1
        self.service._last_noise_reduction = -1
        self.service._last_auto_power_off = -1
        self.service._last_subdevices = -1
        self.service._last_link = False
        self.service._device_name = ''
        self.service._serial = ''
        self.service._firmware = ''

    # ── getters ──────────────────────────────────────────────────────

    def test_getters_return_device_values(self):
        self.service._device = _FakeDevice()
        self.assertEqual(self.service.GetSidetone(), 40)
        self.assertEqual(self.service.GetNoiseReduction(), 2)
        self.assertEqual(self.service.GetAutoPowerOff(), 30)
        self.assertEqual(self.service.GetLatency(), 1)
        self.assertEqual(self.service.GetSubDevices(), 1)

    def test_getters_return_sentinels_without_device(self):
        self.assertEqual(self.service.GetSidetone(), -1)
        self.assertEqual(self.service.GetNoiseReduction(), -1)
        self.assertEqual(self.service.GetAutoPowerOff(), -1)
        self.assertEqual(self.service.GetLatency(), -1)
        self.assertEqual(self.service.GetSubDevices(), -1)

    def test_getter_tolerates_device_error(self):
        dev = _FakeDevice()
        dev.raise_on.add('latency')
        self.service._device = dev
        self.assertEqual(self.service.GetLatency(), -1)

    def test_get_device_identity(self):
        self.service._device = _FakeDevice()
        self.assertEqual(self.service.GetDeviceName(), 'EPOS GSA 70')
        self.assertEqual(self.service.GetSerial(), 'ABC123')
        self.assertEqual(self.service.GetFirmwareVersion(), '3.14.2')

    def test_identity_cached_after_refresh(self):
        dev = _FakeDevice()
        self.service._device = dev
        self.service.GetDeviceName()
        dev.values['name'] = 'CHANGED'
        # Cached: a plain get must not re-read the device.
        self.assertEqual(self.service.GetDeviceName(), 'EPOS GSA 70')
        self.assertEqual(self.service._device_name, 'EPOS GSA 70')

    # ── setters ──────────────────────────────────────────────────────

    def test_set_auto_power_off_persists_and_sets(self):
        dev = _FakeDevice()
        self.service._device = dev
        with mock.patch('gsp670.dbus_service.load_device_config',
                        return_value=DeviceConfig()), \
             mock.patch('gsp670.dbus_service.save_device_config') as save:
            ok = self.service.SetAutoPowerOff(45)
        self.assertTrue(ok)
        self.assertEqual(dev.values['auto_power_off'], 45)
        save.assert_called_once()

    def test_set_auto_power_off_rejects_out_of_range(self):
        self.service._device = _FakeDevice()
        self.assertFalse(self.service.SetAutoPowerOff(-1))
        self.assertFalse(self.service.SetAutoPowerOff(256))

    def test_set_auto_power_off_false_on_device_error(self):
        self.service._device = None
        self.assertFalse(self.service.SetAutoPowerOff(10))

    # ── device info signal ───────────────────────────────────────────

    def test_refresh_emits_device_info_changed_once(self):
        self.service._device = _FakeDevice()
        self.assertTrue(self.service.RefreshDeviceInfo())
        self.assertEqual(self.service.signals.count(('DeviceInfoChanged',)), 1)
        # Nothing changed the second time.
        self.service.RefreshDeviceInfo()
        self.assertEqual(self.service.signals.count(('DeviceInfoChanged',)), 1)

    def test_refresh_false_without_device(self):
        self.assertFalse(self.service.RefreshDeviceInfo())

    # ── poll-once change detection ───────────────────────────────────

    def test_poll_once_emits_new_state_signals_once(self):
        self.service._device = _FakeDevice()
        self.service._poll_once()
        names = [s[0] for s in self.service.signals]
        self.assertIn('SidetoneChanged', names)
        self.assertIn('NoiseReductionChanged', names)
        self.assertIn('AutoPowerOffChanged', names)
        self.assertIn('SubDevicesChanged', names)

        # A second, unchanged iteration must not re-emit.
        before = len(self.service.signals)
        self.service._poll_once()
        self.assertEqual(len(self.service.signals), before)

    def test_poll_once_emits_on_real_change(self):
        dev = _FakeDevice(noise_reduction=0)
        self.service._device = dev
        self.service._poll_once()
        self.service.signals.clear()

        dev.values['noise_reduction'] = 3
        self.service._poll_once()
        self.assertIn(('NoiseReductionChanged', 3), self.service.signals)


if __name__ == '__main__':
    unittest.main()
