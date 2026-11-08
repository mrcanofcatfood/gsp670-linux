#!/usr/bin/env python3
"""
Integration tests for device discovery.

Tests device enumeration and find_devices() functionality with actual hardware.
Requires the GSP 670 headset or GSA 70 dongle to be connected.

Requires:
- A GSP 670 headset or dongle connected
- Root privileges (for HID access on hidraw devices)
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from gsp670 import (
    find_devices,
    enumerate_hid,
    enumerate_audio,
    find_dongle,
    find_headset,
    find_audio_card,
    print_devices,
    DeviceNotFoundError,
)
from gsp670.protocol import VID, PID_GSA70, PID_GSP670


class TestDeviceEnumeration(unittest.TestCase):
    """Test device enumeration with actual hardware."""

    def test_find_devices_returns_list(self):
        """Test that find_devices returns a list."""
        devices = find_devices()
        self.assertIsInstance(devices, list)
        print(f"\nFound {len(devices)} device(s)")

    def test_find_devices_structure(self):
        """Test that returned devices have expected structure."""
        devices = find_devices()
        
        for dev in devices:
            self.assertTrue(hasattr(dev, 'vid'))
            self.assertTrue(hasattr(dev, 'pid'))
            self.assertTrue(hasattr(dev, 'path'))
            self.assertEqual(dev.vid, VID)

    def test_find_devices_contains_expected_pids(self):
        """Test that found devices have expected product IDs."""
        devices = find_devices()
        
        if not devices:
            self.skipTest("No devices found - hardware not connected")
        
        for dev in devices:
            # Should be GSA70, GSP670, or upgrade mode PIDs
            valid_pids = [PID_GSA70, PID_GSP670, 0x8300, 0x8303, 0x8089, 0x808A]
            self.assertIn(dev.pid, valid_pids,
                        f"Unexpected PID 0x{dev.pid:04X}")

    @unittest.skip("May not find any devices depending on connection state")
    def test_enumerate_hid(self):
        """Test HID device enumeration."""
        devices = enumerate_hid()
        self.assertIsInstance(devices, list)
        print(f"\nHID interfaces found: {len(devices)}")


class TestDongleDiscovery(unittest.TestCase):
    """Test GSA 70 dongle discovery."""

    def test_find_dongle_returns_device_or_none(self):
        """Test that find_dongle returns DeviceInfo or None."""
        result = find_dongle()
        # Should return DeviceInfo if dongle is connected, None otherwise
        if result is not None:
            self.assertEqual(result.pid, PID_GSA70)
            print(f"\nDongle found: {result.product_string or 'Unknown'}")
        else:
            print("\nDongle not found - may be in headset-only mode")

    def test_find_dongle_returns_correct_pid(self):
        """Test that found dongle has correct PID."""
        dongle = find_dongle()
        if dongle is not None:
            self.assertEqual(dongle.pid, PID_GSA70)


class TestHeadsetDiscovery(unittest.TestCase):
    """Test GSP 670 headset discovery."""

    def test_find_headset_returns_device_or_none(self):
        """Test that find_headset returns DeviceInfo or None."""
        result = find_headset()
        # Returns DeviceInfo if headset is in wired mode (0x008A), None otherwise
        if result is not None:
            self.assertEqual(result.pid, PID_GSP670)
            print(f"\nHeadset found: {result.product_string or 'Unknown'}")
        else:
            print("\nHeadset not found - may be in wireless mode via dongle")

    def test_find_headset_returns_correct_pid(self):
        """Test that found headset has correct PID."""
        headset = find_headset()
        if headset is not None:
            self.assertEqual(headset.pid, PID_GSP670)


class TestAudioEnumeration(unittest.TestCase):
    """Test ALSA audio device enumeration."""

    def test_enumerate_audio_returns_list(self):
        """Test that enumerate_audio returns a list."""
        devices = enumerate_audio()
        self.assertIsInstance(devices, list)
        print(f"\nAudio devices found: {len(devices)}")

    def test_find_audio_card_g670(self):
        """Test finding G670 audio card."""
        card = find_audio_card('G670')
        if card is not None:
            print(f"\nG670 audio card: {card}")
            self.assertIsInstance(card, int)
        else:
            print("\nG670 audio card not found - headset may be in wireless mode")

    def test_find_audio_card_gsp670(self):
        """Test finding GSP 670 audio card."""
        card = find_audio_card('GSP 670')
        if card is not None:
            print(f"\nGSP 670 audio card: {card}")
            self.assertIsInstance(card, int)


class TestDeviceClassification(unittest.TestCase):
    """Test that devices are correctly classified by type."""

    def test_dongle_flag_set(self):
        """Test that GSA 70 dongles have is_dongle=True."""
        devices = find_devices()
        dongles = [d for d in devices if d.is_dongle]
        
        if not dongles:
            self.skipTest("No dongle found")
        
        for d in dongles:
            self.assertTrue(d.is_dongle)
            self.assertEqual(d.pid, PID_GSA70)

    def test_headset_flag_set(self):
        """Test that GSP 670 headsets have is_headset=True."""
        devices = find_devices()
        headsets = [d for d in devices if d.is_headset]
        
        if not headsets:
            self.skipTest("No headset found in wired mode")
        
        for d in headsets:
            self.assertTrue(d.is_headset)
            self.assertEqual(d.pid, PID_GSP670)


class TestPrintDevices(unittest.TestCase):
    """Test device printing functions."""

    def test_print_devices_runs(self):
        """Test that print_devices doesn't crash."""
        # This is a smoke test - just verify it runs without error
        try:
            print_devices()
        except Exception as e:
            self.fail(f"print_devices raised exception: {e}")

    def test_print_devices_with_devices(self):
        """Test print_devices with explicit device list."""
        devices = find_devices()
        try:
            print_devices(devices)
        except Exception as e:
            self.fail(f"print_devices with list raised exception: {e}")


if __name__ == '__main__':
    # Run with -v for verbose output
    unittest.main(verbosity=2)
