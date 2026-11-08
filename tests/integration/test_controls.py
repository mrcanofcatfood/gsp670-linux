#!/usr/bin/env python3
"""
Integration test for device controls.

Tests volume control operations, mute control operations, and documents
which controls actually work on the GSP 670 headset.

Requires:
- A GSP 670 headset or dongle connected
- Root privileges (for HID access)
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from gsp670 import (
    GSA70Device,
    GSP670Device,
    ControlsState,
    VolumeControl,
    MuteControl,
    SidetoneControl,
    DeviceNotFoundError,
)


class TestControlsState(unittest.TestCase):
    """Test ControlsState class."""
    
    def test_default_state(self):
        """Test default controls state initialization."""
        state = ControlsState()
        
        self.assertIsNotNone(state.volume)
        self.assertIsNotNone(state.mute)
        self.assertIsNotNone(state.sidetone)
        
        self.assertEqual(state.volume.value, 50)
        self.assertEqual(state.mute.muted, False)
        self.assertEqual(state.sidetone.value, 50)
    
    def test_volume_range(self):
        """Test volume control range validation."""
        volume = VolumeControl()
        
        # Valid range
        volume.set(0)
        self.assertEqual(volume.value, 0)
        
        volume.set(100)
        self.assertEqual(volume.value, 100)
        
        # Out of range
        with self.assertRaises(ValueError):
            volume.set(-1)
        
        with self.assertRaises(ValueError):
            volume.set(101)
    
    def test_volume_increment(self):
        """Test volume increment/decrement."""
        volume = VolumeControl()
        volume.value = 50
        
        # Increment
        new_val = volume.increment(5)
        self.assertEqual(new_val, 55)
        
        # Decrement
        new_val = volume.increment(-10)
        self.assertEqual(new_val, 45)
        
        # Clamp to minimum
        volume.value = 5
        new_val = volume.increment(-10)
        self.assertEqual(new_val, 0)
        
        # Clamp to maximum
        volume.value = 95
        new_val = volume.increment(10)
        self.assertEqual(new_val, 100)
    
    def test_mute_toggle(self):
        """Test mute toggle."""
        mute = MuteControl()
        
        self.assertFalse(mute.muted)
        
        mute.toggle()
        self.assertTrue(mute.muted)
        
        mute.toggle()
        self.assertFalse(mute.muted)
    
    def test_mute_set(self):
        """Test mute set."""
        mute = MuteControl()
        
        mute.set(True)
        self.assertTrue(mute.muted)
        
        mute.set(False)
        self.assertFalse(mute.muted)
    
    def test_sidetone_range(self):
        """Test sidetone control range validation."""
        sidetone = SidetoneControl()
        
        sidetone.set(0)
        self.assertEqual(sidetone.value, 0)
        
        sidetone.set(100)
        self.assertEqual(sidetone.value, 100)
        
        with self.assertRaises(ValueError):
            sidetone.set(-1)
        
        with self.assertRaises(ValueError):
            sidetone.set(101)
    
    def test_sidetone_unsupported(self):
        """Test sidetone not supported flag."""
        sidetone = SidetoneControl()
        sidetone.supported = False
        
        # set() should raise NotImplementedError when not supported
        with self.assertRaises(NotImplementedError):
            sidetone.set(50)
        
        # Note: increment() does NOT check supported flag,
        # it just clamps the value. This is a design choice.


class TestControlDocumentation(unittest.TestCase):
    """
    Document which controls actually work on the GSP 670.
    
    This test documents the expected behavior based on analysis and testing.
    """
    
    def test_volume_control_documentation(self):
        """Document volume control behavior."""
        # Based on analysis:
        # - Volume wheel generates HID reports (Report ID 0x02)
        # - Volume range is 0-100
        # - Software volume control may not actually affect hardware volume
        
        volume = VolumeControl()
        
        # Test range
        volume.set(0)
        self.assertEqual(volume.value, 0)
        
        volume.set(100)
        self.assertEqual(volume.value, 100)
        
        # The volume wheel on the headset generates HID events
        # but the actual volume may be controlled by the headset firmware
        print("\nVolume Control Documentation:")
        print("  - Physical control: Volume wheel on headset")
        print("  - HID Report ID: 0x02")
        print("  - Software volume: 0-100 range tracking only")
        print("  - Actual volume may be controlled by headset firmware")
    
    def test_mute_control_documentation(self):
        """Document mute control behavior."""
        # Based on analysis:
        # - Mute button generates HID reports (Report ID 0x06)
        # - Mute toggles audio playback/capture
        
        mute = MuteControl()
        
        print("\nMute Control Documentation:")
        print("  - Physical control: Mute button on headset")
        print("  - HID Report ID: 0x06")
        print("  - Behavior: Toggle mute state")
        print("  - Effect: Silences microphone and/or speakers")
    
    def test_sidetone_control_documentation(self):
        """Document sidetone control behavior."""
        # Sidetone lets you hear your own voice in the headset
        # This feature may or may not be supported depending on firmware
        
        sidetone = SidetoneControl()
        sidetone.supported = False  # Many firmwares don't support this
        
        print("\nSidetone Control Documentation:")
        print("  - Physical control: None (software only if supported)")
        print("  - Purpose: Hear your own voice in headset")
        print("  - Support: Varies by firmware version")
        print("  - If not supported, software calls will raise NotImplementedError")
    
    def test_media_controls_documentation(self):
        """Document media control behavior."""
        # The headset has media controls (play/pause, next, prev)
        # HID Report ID 0x08 with 4 1-bit fields
        
        print("\nMedia Controls Documentation:")
        print("  - Play/Pause button")
        print("  - Next track button")
        print("  - Previous track button")
        print("  - HID Report ID: 0x08")
        print("  - Format: 4 1-bit fields in byte 1")


class TestSecomDeviceAccess(unittest.TestCase):
    """
    Test the verified SECOM device methods.

    These tests require actual hardware to run.
    """

    @unittest.skip("Requires hardware - run manually")
    def test_get_device_name(self):
        """The dongle reports its name (opcode 0x02)."""
        try:
            with GSA70Device() as dev:
                name = dev.get_device_name()
                print(f"\nDevice name: {name!r}")
                self.assertIsInstance(name, str)
                self.assertIn('GSA', name.upper())
        except DeviceNotFoundError:
            self.skipTest("No device found")

    @unittest.skip("Requires hardware - run manually")
    def test_get_firmware_version(self):
        """The dongle reports a dotted firmware version (opcode 0x00)."""
        try:
            with GSA70Device() as dev:
                fw = dev.get_firmware_version()
                print(f"\nFirmware: {fw}")
                self.assertRegex(fw or '', r'^\d+\.\d+\.\d+$')
        except DeviceNotFoundError:
            self.skipTest("No device found")

    @unittest.skip("Requires hardware - run manually")
    def test_set_sidetone_acked(self):
        """Sidetone set (opcode 0x11) is link-ACKed by the dongle."""
        try:
            with GSA70Device() as dev:
                self.assertTrue(dev.set_sidetone(5))
        except DeviceNotFoundError:
            self.skipTest("No device found")

    @unittest.skip("Requires hardware - run manually")
    def test_settings_need_linked_headset(self):
        """Read-backs need the headset; expect None when unlinked."""
        try:
            with GSA70Device() as dev:
                # All of these query the nested headset.
                for name in ('get_battery_percentage', 'get_sidetone',
                             'get_noise_reduction', 'get_latency'):
                    value = getattr(dev, name)()
                    print(f"\n{name}: {value}")
                    self.assertTrue(value is None or isinstance(value, int))
        except DeviceNotFoundError:
            self.skipTest("No device found")

    @unittest.skip("Requires hardware - run manually")
    def test_volume_is_not_a_device_command(self):
        """Volume is an OS/USB-Audio-Class control, not SECOM."""
        try:
            with GSA70Device() as dev:
                self.assertEqual(dev.get_volume(), -1)
                self.assertFalse(dev.set_volume(50))
        except DeviceNotFoundError:
            self.skipTest("No device found")


class TestSecomOpcodes(unittest.TestCase):
    """Verify the verified SECOM opcode constants and request payloads."""

    def test_opcode_values(self):
        from gsp670.protocol import SecomOpcode
        self.assertEqual(SecomOpcode.GET_FW_VERSION, 0x00)
        self.assertEqual(SecomOpcode.GET_SERIAL_NO, 0x01)
        self.assertEqual(SecomOpcode.GET_DEVICE_NAME, 0x02)
        self.assertEqual(SecomOpcode.GET_DEVICE_ADDRESS, 0x03)
        self.assertEqual(SecomOpcode.GET_BATTERY_PERCENTAGE, 0x0E)
        self.assertEqual(SecomOpcode.GET_SIDETONE, 0x10)
        self.assertEqual(SecomOpcode.SET_SIDETONE, 0x11)
        self.assertEqual(SecomOpcode.SET_NOISE_REDUCTION, 0x12)
        self.assertEqual(SecomOpcode.GET_NOISE_REDUCTION, 0x13)
        self.assertEqual(SecomOpcode.GET_LATENCY, 0x17)

    def test_request_payloads(self):
        from gsp670.protocol import secom_request, SecomOpcode
        self.assertEqual(secom_request(SecomOpcode.GET_FW_VERSION),
                         bytes.fromhex('01000300'))
        self.assertEqual(secom_request(SecomOpcode.GET_DEVICE_NAME),
                         bytes.fromhex('09000100'))
        # Setters append the value as a u16 LE.
        self.assertEqual(secom_request(SecomOpcode.SET_SIDETONE, 5),
                         bytes.fromhex('0a000b000500'))
        self.assertEqual(secom_request(SecomOpcode.SET_NOISE_REDUCTION, 7),
                         bytes.fromhex('0a0011000700'))

    def test_setter_requires_value(self):
        from gsp670.protocol import secom_request, SecomOpcode
        with self.assertRaises(ValueError):
            secom_request(SecomOpcode.SET_SIDETONE)

    def test_secom_opcode_get_fw_version_exists(self):
        """Verify SecomOpcode.GET_FW_VERSION is the correct replacement for deprecated FeatureIndex."""
        from gsp670.protocol import SecomOpcode
        self.assertEqual(SecomOpcode.GET_FW_VERSION, 0x00)
        # FeatureIndex was the old guessed model, now replaced by SecomOpcode
        # which was recovered via static analysis of the actual EPOS Gaming Suite binary


if __name__ == '__main__':
    # Run with -v for verbose output
    unittest.main(verbosity=2)
