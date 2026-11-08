#!/usr/bin/env python3
"""
Integration tests for GSP 670 device interactions.

Tests device reconnection and control persistence using mocks.
"""

import sys
import os
import tempfile
import unittest

sys.path.insert(0, 'src')
sys.path.insert(0, 'tests')

from mocks.mock_hid import MockHIDDevice, MockHIDContext
from gsp670.config import DeviceConfig, save_device_config, load_device_config
from gsp670.protocol import frame, SecomOpcode


class TestDeviceReconnection(unittest.TestCase):
    """Tests for device reconnection scenarios."""
    
    def test_mock_device_basic_flow(self):
        """Test basic mock device flow."""
        mock = MockHIDDevice()
        
        # Mock should be connected by default
        self.assertTrue(mock.is_connected())
        
        # Send a firmware version query
        # Frame format: 01 | EB FE 01 00 | 04 00 | 00 00 | 04 | crc | 00 | 01 00 03 00
        frame_bytes = frame(SecomOpcode.GET_FW_VERSION, b'\x01\x00\x03\x00')
        
        # Write frame to mock (this triggers response generation)
        mock.write(frame_bytes)
        
        # Read response
        response = mock.read()
        self.assertIsNotNone(response)
        
        # Disconnect
        mock.disconnect()
        self.assertFalse(mock.is_connected())
    
    def test_mock_device_responses(self):
        """Test that mock device returns correct responses."""
        mock = MockHIDDevice()
        
        # Test serial number query
        frame_bytes = frame(SecomOpcode.GET_SERIAL_NO, b'\x01\x00\x0b\x00')
        mock.write(frame_bytes)
        
        response = mock.read()
        self.assertIsNotNone(response)
        
        # Response should have correct marker
        self.assertEqual(response[5:7], b'\x04\x00')
    
    def test_reconnection_sequence(self):
        """Test connect -> disconnect -> reconnect sequence."""
        mock = MockHIDDevice()
        
        # Initial connection
        mock.connect()
        self.assertTrue(mock.is_connected())
        
        # Send command
        frame_bytes = frame(SecomOpcode.GET_FW_VERSION, b'\x01\x00\x03\x00')
        mock.write(frame_bytes)
        
        # Disconnect
        mock.disconnect()
        self.assertFalse(mock.is_connected())
        
        # Reconnect
        mock.connect()
        self.assertTrue(mock.is_connected())
        
        # Should be able to send again
        mock.write(frame_bytes)
        response = mock.read()
        self.assertIsNotNone(response)


class TestControlPersistence(unittest.TestCase):
    """Tests for control setting persistence."""
    
    def setUp(self):
        """Set up temporary config directory."""
        self._tmpdir = tempfile.mkdtemp()
        self._orig_xdg = os.environ.get('XDG_CONFIG_HOME')
        os.environ['XDG_CONFIG_HOME'] = self._tmpdir
    
    def tearDown(self):
        """Restore original config directory."""
        if self._orig_xdg:
            os.environ['XDG_CONFIG_HOME'] = self._orig_xdg
        else:
            os.environ.pop('XDG_CONFIG_HOME', None)
    
    def test_save_and_load_config(self):
        """Test basic config save/load."""
        config = DeviceConfig()
        config.serial = "TEST123"
        config.sidetone_level = 75
        config.noise_reduction_level = 2
        
        # Save
        save_device_config(config, serial="TEST123")
        
        # Load
        loaded = load_device_config(serial="TEST123")
        
        self.assertEqual(loaded.serial, "TEST123")
        self.assertEqual(loaded.sidetone_level, 75)
        self.assertEqual(loaded.noise_reduction_level, 2)
    
    def test_config_persistence_across_sessions(self):
        """Test config persists across separate 'sessions'."""
        # Session 1: Set some values
        config1 = DeviceConfig()
        config1.serial = "DEVICE456"
        config1.sidetone_level = 60
        save_device_config(config1, serial="DEVICE456")
        
        # Session 2: Load and verify
        config2 = load_device_config(serial="DEVICE456")
        self.assertEqual(config2.sidetone_level, 60)
        self.assertEqual(config2.serial, "DEVICE456")
        
        # Session 2: Update a value
        config2.sidetone_level = 80
        save_device_config(config2, serial="DEVICE456")
        
        # Session 3: Verify update
        config3 = load_device_config(serial="DEVICE456")
        self.assertEqual(config3.sidetone_level, 80)
    
    def test_different_devices_separate_config(self):
        """Test that different devices have separate configs."""
        # Device A
        config_a = DeviceConfig()
        config_a.serial = "DEVICE_A"
        config_a.sidetone_level = 50
        save_device_config(config_a, serial="DEVICE_A")
        
        # Device B
        config_b = DeviceConfig()
        config_b.serial = "DEVICE_B"
        config_b.sidetone_level = 100
        save_device_config(config_b, serial="DEVICE_B")
        
        # Verify each device has its own config
        loaded_a = load_device_config(serial="DEVICE_A")
        loaded_b = load_device_config(serial="DEVICE_B")
        
        self.assertEqual(loaded_a.sidetone_level, 50)
        self.assertEqual(loaded_b.sidetone_level, 100)
    
    def test_default_config_for_unknown_device(self):
        """Test loading config for unknown device returns defaults."""
        loaded = load_device_config(serial="UNKNOWN_DEVICE")
        
        # Should return default values (but serial is set to the requested device)
        self.assertEqual(loaded.serial, "UNKNOWN_DEVICE")
        self.assertEqual(loaded.sidetone_level, 50)  # default
        self.assertEqual(loaded.noise_reduction_level, 0)  # default


class TestSetAndPersistFlow(unittest.TestCase):
    """Test the set -> persist flow (simulated)."""
    
    def setUp(self):
        """Set up temporary config directory."""
        self._tmpdir = tempfile.mkdtemp()
        self._orig_xdg = os.environ.get('XDG_CONFIG_HOME')
        os.environ['XDG_CONFIG_HOME'] = self._tmpdir
    
    def tearDown(self):
        """Restore original config directory."""
        if self._orig_xdg:
            os.environ['XDG_CONFIG_HOME'] = self._orig_xdg
        else:
            os.environ.pop('XDG_CONFIG_HOME', None)
    
    def test_sidetone_set_and_save(self):
        """Simulate setting sidetone and saving."""
        # Start with clean config
        config = DeviceConfig()
        config.serial = "TEST789"
        save_device_config(config, serial="TEST789")
        
        # Simulate user setting sidetone to 70
        loaded = load_device_config(serial="TEST789")
        loaded.sidetone_level = 70
        save_device_config(loaded, serial="TEST789")
        
        # Verify it persisted
        final = load_device_config(serial="TEST789")
        self.assertEqual(final.sidetone_level, 70)
    
    def test_multiple_settings_persist(self):
        """Test multiple settings persist together."""
        config = DeviceConfig()
        config.serial = "MULTI_TEST"
        config.sidetone_level = 65
        config.noise_reduction_level = 3
        config.auto_power_off_minutes = 60
        save_device_config(config, serial="MULTI_TEST")
        
        # Load and verify all
        loaded = load_device_config(serial="MULTI_TEST")
        self.assertEqual(loaded.sidetone_level, 65)
        self.assertEqual(loaded.noise_reduction_level, 3)
        self.assertEqual(loaded.auto_power_off_minutes, 60)


if __name__ == '__main__':
    unittest.main(verbosity=2)
