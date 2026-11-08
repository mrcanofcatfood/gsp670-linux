#!/usr/bin/env python3
"""
Unit tests for discovery.py - Device enumeration.

Tests HID device discovery and audio device enumeration.
"""

import unittest
from unittest.mock import MagicMock, patch

from gsp670.discovery import (
    PID_GSA70,
    PID_GSP670,
    _parse_alsa_output,
    _parse_device_info,
    find_audio_card,
    find_devices,
    find_dongle,
    find_headset,
)


class TestDeviceInfoParsing(unittest.TestCase):
    """Test device info parsing from hidapi enumeration."""

    def test_parse_device_info_full(self):
        """Test parsing a complete device info dict."""
        d = {
            'vendor_id': 0x1395,
            'product_id': 0x0300,
            'path': b'/dev/hidraw3',
            'serial': 'ABC123',
            'product': 'GSA 70 Dongle',
            'manufacturer': 'EPOS',
            'usage_page': 0xFFFF,
            'usage': 0x01,
            'interface_number': 5,
        }

        info = _parse_device_info(d)

        self.assertEqual(info.vid, 0x1395)
        self.assertEqual(info.pid, 0x0300)
        self.assertEqual(info.path, b'/dev/hidraw3')
        self.assertEqual(info.serial, 'ABC123')
        self.assertEqual(info.product_string, 'GSA 70 Dongle')
        self.assertEqual(info.manufacturer_string, 'EPOS')
        self.assertEqual(info.usage_page, 0xFFFF)
        self.assertEqual(info.usage, 0x01)
        self.assertEqual(info.interface, 5)

    def test_parse_device_info_minimal(self):
        """Test parsing with minimal device info dict."""
        d = {
            'vendor_id': 0x1395,
            'product_id': 0x008A,
        }

        info = _parse_device_info(d)

        self.assertEqual(info.vid, 0x1395)
        self.assertEqual(info.pid, 0x008A)
        self.assertIsNone(info.path)
        self.assertIsNone(info.serial)
        self.assertEqual(info.usage_page, 0)


class TestFindHIDDevice(unittest.TestCase):
    """Test finding specific HID devices."""

    @patch('gsp670.discovery.require_hid')
    def test_find_dongle(self, mock_require_hid):
        """Test finding GSA 70 dongle."""
        # hid.enumerate(VID, PID_GSA70) only returns dongle devices
        mock_require_hid.return_value = MagicMock(
            enumerate=MagicMock(return_value=[
                {
                    'vendor_id': 0x1395,
                    'product_id': 0x0300,
                    'path': b'/dev/hidraw3',
                    'usage_page': 0xFFFF,
                    'usage': 0x01,
                },
            ])
        )

        result = find_dongle()

        self.assertIsNotNone(result)
        self.assertEqual(result.pid, PID_GSA70)
        # Note: find_dongle/find_headset return DeviceInfo but don't set is_dongle/is_headset
        # Those flags are set by find_devices() based on PID classification

    @patch('gsp670.discovery.require_hid')
    def test_find_headset(self, mock_require_hid):
        """Test finding GSP 670 headset."""
        # hid.enumerate(VID, PID_GSP670) only returns headset devices
        mock_require_hid.return_value = MagicMock(
            enumerate=MagicMock(return_value=[
                {
                    'vendor_id': 0x1395,
                    'product_id': 0x008A,
                    'path': b'/dev/hidraw4',
                    'usage_page': 0xFFFF,
                    'usage': 0x01,
                },
            ])
        )

        result = find_headset()

        self.assertIsNotNone(result)
        self.assertEqual(result.pid, PID_GSP670)

    @patch('gsp670.discovery.require_hid')
    def test_find_device_not_found(self, mock_require_hid):
        """Test when device is not found."""
        mock_require_hid.return_value = MagicMock(
            enumerate=MagicMock(return_value=[])
        )

        result = find_dongle()
        self.assertIsNone(result)


class TestFindDevices(unittest.TestCase):
    """Test find_devices function."""

    @patch('gsp670.discovery.require_hid')
    def test_find_devices_deduplicates(self, mock_require_hid):
        """Test that find_devices deduplicates by path."""
        # Same path, multiple interfaces
        mock_require_hid.return_value = MagicMock(
            enumerate=MagicMock(return_value=[
                {
                    'vendor_id': 0x1395,
                    'product_id': 0x0300,
                    'path': b'/dev/hidraw3',
                    'usage_page': 0xFFFF,
                    'usage': 0x01,
                    'interface_number': 0,
                },
                {
                    'vendor_id': 0x1395,
                    'product_id': 0x0300,
                    'path': b'/dev/hidraw3',  # Same path
                    'usage_page': 0xFFFF,
                    'usage': 0x01,
                    'interface_number': 1,
                },
            ])
        )

        result = find_devices()

        # Should only have one device
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].path, b'/dev/hidraw3')

    @patch('gsp670.discovery.require_hid')
    def test_find_devices_classifies_types(self, mock_require_hid):
        """Test that devices are classified correctly."""
        mock_require_hid.return_value = MagicMock(
            enumerate=MagicMock(return_value=[
                {
                    'vendor_id': 0x1395,
                    'product_id': 0x0300,
                    'path': b'/dev/hidraw3',
                    'usage_page': 0xFFFF,
                    'usage': 0x01,
                },
                {
                    'vendor_id': 0x1395,
                    'product_id': 0x008A,
                    'path': b'/dev/hidraw4',
                    'usage_page': 0xFFFF,
                    'usage': 0x01,
                },
            ])
        )

        result = find_devices()

        dongles = [d for d in result if d.is_dongle]
        headsets = [d for d in result if d.is_headset]

        self.assertEqual(len(dongles), 1)
        self.assertEqual(len(headsets), 1)


class TestALSAParsing(unittest.TestCase):
    """Test ALSA device output parsing."""

    def test_parse_alsa_playback(self):
        """Test parsing aplay output."""
        output = """card 4: G670 [GSP 670], device 0: USB Audio [USB Audio]
  Subdevice: 0/1
  Subdevice #1: subdevice #1
"""
        devices = _parse_alsa_output(output, 'playback')

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['card'], 4)
        self.assertEqual(devices[0]['name'], 'G670')
        self.assertEqual(devices[0]['id'], 'GSP 670')
        self.assertEqual(devices[0]['device'], 0)
        self.assertEqual(devices[0]['type'], 'playback')

    def test_parse_alsa_capture(self):
        """Test parsing arecord output."""
        output = """card 3: Generic_1 [HD-Audio Generic], device 0: ALC1220 Analog [ALC1220 Analog]
  Subdevice: 1/1
  Subdevice #1: subdevice #1
"""
        devices = _parse_alsa_output(output, 'capture')

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['card'], 3)
        self.assertEqual(devices[0]['type'], 'capture')

    def test_parse_alsa_empty(self):
        """Test parsing empty output."""
        devices = _parse_alsa_output('', 'playback')
        self.assertEqual(len(devices), 0)


class TestFindAudioCard(unittest.TestCase):
    """Test find_audio_card function."""

    @patch('gsp670.discovery.enumerate_audio')
    def test_find_audio_card_success(self, mock_enum_audio):
        """Test finding audio card by name."""
        mock_enum_audio.return_value = [
            {'card': 0, 'name': 'Generic', 'type': 'playback'},
            {'card': 4, 'name': 'G670', 'type': 'playback'},
        ]

        result = find_audio_card('G670')
        self.assertEqual(result, 4)

    @patch('gsp670.discovery.enumerate_audio')
    def test_find_audio_card_not_found(self, mock_enum_audio):
        """Test when audio card is not found."""
        mock_enum_audio.return_value = [
            {'card': 0, 'name': 'Generic', 'type': 'playback'},
        ]

        result = find_audio_card('G670')
        self.assertIsNone(result)

    @patch('gsp670.discovery.enumerate_audio')
    def test_find_audio_card_case_insensitive(self, mock_enum_audio):
        """Test that search is case insensitive."""
        mock_enum_audio.return_value = [
            {'card': 4, 'name': 'G670', 'type': 'playback'},
        ]

        result = find_audio_card('g670')
        self.assertEqual(result, 4)


if __name__ == '__main__':
    unittest.main()
