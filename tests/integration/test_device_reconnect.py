#!/usr/bin/env python3
"""
Integration test for device disconnect/reconnect handling.

Tests that the library properly handles device disconnection and reconnection
events, and verifies clean error handling throughout the process.

Requires:
- A GSP 670 headset or dongle connected
- Root privileges (for HID access)
"""

import os
import sys
import unittest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from gsp670 import (
    CommunicationError,
    DeviceDisconnectedError,
    DeviceError,
    DeviceNotFoundError,
    GSA70Device,
    GSP670Device,
)


class TestDeviceReconnect(unittest.TestCase):
    """Test device reconnection handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.device = None

    def tearDown(self):
        """Clean up after test."""
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass

    def test_device_open_close(self):
        """Test basic device open/close cycle."""
        # This test requires actual hardware
        try:
            self.device = GSA70Device()
            self.device.open()
            self.assertTrue(self.device.is_connected)
        except DeviceNotFoundError:
            self.skipTest("No device found - hardware not connected")
        except Exception as e:
            # Some other error - still pass if device was found but couldn't open
            self.fail(f"Unexpected error: {e}")
        finally:
            if self.device:
                self.device.close()

    def test_device_context_manager(self):
        """Test device as context manager."""
        try:
            with GSA70Device() as dev:
                self.assertTrue(dev.is_connected)
            # After context, should be closed
            self.assertFalse(dev.is_connected)
        except DeviceNotFoundError:
            self.skipTest("No device found - hardware not connected")

    def test_exchange_requires_connection(self):
        """Test that exchange fails when device is not connected."""
        device = GSA70Device()

        with self.assertRaises(DeviceDisconnectedError):
            device.exchange(0x4F12)

    def test_write_requires_connection(self):
        """Test that write fails when device is not connected."""
        device = GSA70Device()

        with self.assertRaises(DeviceDisconnectedError):
            device.write(0x4F12)

    def test_read_returns_none_when_disconnected(self):
        """Test that read returns None when device is not connected."""
        device = GSA70Device()

        result = device.read()
        self.assertIsNone(result)

    def test_double_open(self):
        """Test that double open doesn't raise."""
        try:
            self.device = GSA70Device()
            self.device.open()
            # Opening again should be safe
            self.device.open()
            self.assertTrue(self.device.is_connected)
        except DeviceNotFoundError:
            self.skipTest("No device found - hardware not connected")
        finally:
            if self.device:
                self.device.close()

    def test_double_close(self):
        """Test that double close doesn't raise."""
        self.device = GSA70Device()

        try:
            self.device.open()
        except DeviceNotFoundError:
            self.skipTest("No device found - hardware not connected")

        # First close
        self.device.close()

        # Second close should be safe
        self.device.close()
        self.assertFalse(self.device.is_connected)

    def test_drain_when_closed(self):
        """Test that drain works when device is closed (returns empty list)."""
        self.device = GSA70Device()

        # Drain on closed device should return empty list
        result = self.device.drain()
        self.assertEqual(result, [])

    @unittest.skip("Requires physical device disconnect - manual test")
    def test_reconnect_after_disconnect(self):
        """Test that device can be reopened after physical disconnect/reconnect."""
        # This is a manual test - it requires physically disconnecting and
        # reconnecting the device during the test

        self.device = GSA70Device()

        # First connection
        self.device.open()
        self.assertTrue(self.device.is_connected)
        self.device.close()

        # NOTE: At this point, physically disconnect and reconnect the device

        # Try to reconnect
        self.device.open()
        self.assertTrue(self.device.is_connected)
        self.device.close()


class TestDeviceErrorHandling(unittest.TestCase):
    """Test error handling in various scenarios."""

    def test_communication_error_on_exchange(self):
        """Test CommunicationError is raised when device doesn't respond."""
        device = GSA70Device()

        try:
            device.open()
        except DeviceNotFoundError:
            self.skipTest("No device found - hardware not connected")

        # Mock the write to succeed but read to fail
        def failing_read(*args, **kwargs):
            return None  # No response

        device.read = failing_read

        with self.assertRaises(CommunicationError):
            device.exchange(0x4F12, timeout_ms=100)

        device.close()

    def test_device_not_found_error(self):
        """Test DeviceNotFoundError is raised when device doesn't exist."""
        device = GSA70Device()

        # Close any open device first
        try:
            device.close()
        except Exception:
            pass

        # Mock the device path to something that doesn't exist
        device._path = b'/dev/hidraw999'

        # Opening a non-existent device should raise DeviceError
        with self.assertRaises(DeviceError):
            device.open()

    def test_exception_propagation_from_write(self):
        """Test that OSError from write is wrapped."""
        device = GSA70Device()

        try:
            device.open()
        except DeviceNotFoundError:
            self.skipTest("No device found - hardware not connected")

        # Close device to force write error
        device.close()

        with self.assertRaises(DeviceDisconnectedError):
            device.write(0x4F12)


class TestGSP670Device(unittest.TestCase):
    """Test GSP670Device (headset in wired mode) handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.device = None

    def tearDown(self):
        """Clean up after test."""
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass

    def test_headset_device_open(self):
        """Test opening the headset device directly."""
        try:
            self.device = GSP670Device()
            self.device.open()
            self.assertTrue(self.device.is_connected)
        except DeviceNotFoundError:
            self.skipTest("No headset device found - may be in dongle mode")

    def test_headset_context_manager(self):
        """Test headset device as context manager."""
        try:
            with GSP670Device() as dev:
                self.assertTrue(dev.is_connected)
            self.assertFalse(dev.is_connected)
        except DeviceNotFoundError:
            self.skipTest("No headset device found - may be in dongle mode")


if __name__ == '__main__':
    unittest.main()
