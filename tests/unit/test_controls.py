#!/usr/bin/env python3
"""
Unit tests for controls.py.

Covers: SecomControl enum, VolumeControl, MuteControl, SidetoneControl,
ControlsState, volume_delta_to_level().
(Integration tests in tests/integration/test_controls.py cover the rest.)
"""

import sys
import unittest

sys.path.insert(0, 'src')

from gsp670.controls import (
    SecomControl,
    VolumeControl,
    MuteControl,
    SidetoneControl,
    ControlsState,
    volume_delta_to_level,
)


class TestSecomControl(unittest.TestCase):
    """Test SecomControl opcode enum values."""

    def test_opcode_values_match_protocol(self):
        """Verify SecomControl values match SecomOpcode from protocol."""
        from gsp670.protocol import SecomOpcode
        # SecomControl is an alias/duplicate; values should match
        self.assertEqual(int(SecomControl.GET_FW_VERSION), int(SecomOpcode.GET_FW_VERSION))
        self.assertEqual(int(SecomControl.GET_SERIAL_NO), int(SecomOpcode.GET_SERIAL_NO))
        self.assertEqual(int(SecomControl.GET_DEVICE_NAME), int(SecomOpcode.GET_DEVICE_NAME))
        self.assertEqual(int(SecomControl.GET_BATTERY_PERCENTAGE), int(SecomOpcode.GET_BATTERY_PERCENTAGE))
        self.assertEqual(int(SecomControl.SET_SIDETONE), int(SecomOpcode.SET_SIDETONE))
        self.assertEqual(int(SecomControl.SET_NOISE_REDUCTION), int(SecomOpcode.SET_NOISE_REDUCTION))
        self.assertEqual(int(SecomControl.GET_NOISE_REDUCTION), int(SecomOpcode.GET_NOISE_REDUCTION))
        self.assertEqual(int(SecomControl.SET_AUTO_POWER_OFF), int(SecomOpcode.SET_AUTO_POWER_OFF))
        self.assertEqual(int(SecomControl.GET_AUTO_POWER_OFF), int(SecomOpcode.GET_AUTO_POWER_OFF))

    def test_control_opcodes_are_int(self):
        """All controls should be ints for use in struct.pack."""
        for member in SecomControl:
            self.assertIsInstance(int(member), int)

    def test_setter_opcodes_are_distinct(self):
        """Setter opcodes should be different from getter opcodes."""
        self.assertNotEqual(SecomControl.SET_SIDETONE, SecomControl.GET_SIDETONE)
        self.assertNotEqual(SecomControl.SET_NOISE_REDUCTION, SecomControl.GET_NOISE_REDUCTION)
        self.assertNotEqual(SecomControl.SET_AUTO_POWER_OFF, SecomControl.GET_AUTO_POWER_OFF)


class TestVolumeControl(unittest.TestCase):
    """Test VolumeControl class."""

    def test_default_value(self):
        vol = VolumeControl()
        self.assertEqual(vol.value, 50)
        self.assertEqual(vol.min_value, 0)
        self.assertEqual(vol.max_value, 100)

    def test_set_valid(self):
        vol = VolumeControl()
        vol.set(75)
        self.assertEqual(vol.value, 75)

    def test_set_out_of_range_raises(self):
        vol = VolumeControl()
        with self.assertRaises(ValueError):
            vol.set(-1)
        with self.assertRaises(ValueError):
            vol.set(101)

    def test_set_at_minimum(self):
        vol = VolumeControl()
        vol.set(0)
        self.assertEqual(vol.value, 0)

    def test_set_at_maximum(self):
        vol = VolumeControl()
        vol.set(100)
        self.assertEqual(vol.value, 100)

    def test_increment_positive(self):
        vol = VolumeControl(value=50)
        new = vol.increment(10)
        self.assertEqual(new, 60)
        self.assertEqual(vol.value, 60)

    def test_increment_negative(self):
        vol = VolumeControl(value=50)
        new = vol.increment(-10)
        self.assertEqual(new, 40)
        self.assertEqual(vol.value, 40)

    def test_increment_clamped_to_max(self):
        vol = VolumeControl(value=95)
        new = vol.increment(10)
        self.assertEqual(new, 100)
        self.assertEqual(vol.value, 100)

    def test_increment_clamped_to_min(self):
        vol = VolumeControl(value=5)
        new = vol.increment(-10)
        self.assertEqual(new, 0)
        self.assertEqual(vol.value, 0)

    def test_increment_default_is_one(self):
        vol = VolumeControl(value=50)
        vol.increment()  # default delta=1
        self.assertEqual(vol.value, 51)

    def test_is_muted_at_minimum(self):
        vol = VolumeControl(value=0)
        self.assertTrue(vol.is_muted())

    def test_is_not_muted_above_minimum(self):
        vol = VolumeControl(value=1)
        self.assertFalse(vol.is_muted())


class TestMuteControl(unittest.TestCase):
    """Test MuteControl class."""

    def test_default_not_muted(self):
        mute = MuteControl()
        self.assertFalse(mute.muted)

    def test_toggle(self):
        mute = MuteControl()
        self.assertFalse(mute.muted)
        mute.toggle()
        self.assertTrue(mute.muted)
        mute.toggle()
        self.assertFalse(mute.muted)

    def test_toggle_returns_new_state(self):
        mute = MuteControl()
        self.assertEqual(mute.toggle(), True)
        self.assertEqual(mute.toggle(), False)

    def test_set_true(self):
        mute = MuteControl()
        mute.set(True)
        self.assertTrue(mute.muted)

    def test_set_false(self):
        mute = MuteControl(muted=True)
        mute.set(False)
        self.assertFalse(mute.muted)


class TestSidetoneControl(unittest.TestCase):
    """Test SidetoneControl class."""

    def test_default_values(self):
        st = SidetoneControl()
        self.assertEqual(st.value, 50)
        self.assertEqual(st.min_value, 0)
        self.assertEqual(st.max_value, 100)
        self.assertTrue(st.supported)

    def test_set_valid(self):
        st = SidetoneControl()
        st.set(75)
        self.assertEqual(st.value, 75)

    def test_set_out_of_range_raises(self):
        st = SidetoneControl()
        with self.assertRaises(ValueError):
            st.set(-1)
        with self.assertRaises(ValueError):
            st.set(101)

    def test_set_unsupported_raises(self):
        st = SidetoneControl(supported=False)
        with self.assertRaises(NotImplementedError):
            st.set(50)

    def test_increment_positive(self):
        st = SidetoneControl(value=50)
        new = st.increment(10)
        self.assertEqual(new, 60)

    def test_increment_negative(self):
        st = SidetoneControl(value=50)
        new = st.increment(-10)
        self.assertEqual(new, 40)

    def test_increment_clamped(self):
        st = SidetoneControl(value=95)
        new = st.increment(10)
        self.assertEqual(new, 100)


class TestControlsState(unittest.TestCase):
    """Test ControlsState aggregation class."""

    def test_defaults_created(self):
        state = ControlsState()
        self.assertIsInstance(state.volume, VolumeControl)
        self.assertIsInstance(state.mute, MuteControl)
        self.assertIsInstance(state.sidetone, SidetoneControl)

    def test_custom_controls(self):
        vol = VolumeControl(value=80)
        state = ControlsState(volume=vol)
        self.assertEqual(state.volume.value, 80)
        self.assertIsInstance(state.mute, MuteControl)  # default still created
        self.assertIsInstance(state.sidetone, SidetoneControl)

    def test_all_defaults_can_be_overridden(self):
        vol = VolumeControl(value=30)
        mute = MuteControl(muted=True)
        st = SidetoneControl(value=20)
        state = ControlsState(volume=vol, mute=mute, sidetone=st)
        self.assertEqual(state.volume.value, 30)
        self.assertTrue(state.mute.muted)
        self.assertEqual(state.sidetone.value, 20)


class TestVolumeDeltaToLevel(unittest.TestCase):
    """Test volume_delta_to_level helper."""

    def test_positive_delta(self):
        result = volume_delta_to_level(4, current=50)
        self.assertEqual(result, 51)  # 50 + 4//4 = 51

    def test_negative_delta(self):
        result = volume_delta_to_level(-4, current=50)
        self.assertEqual(result, 49)  # 50 + (-4)//4 = 49

    def test_large_delta_positive(self):
        result = volume_delta_to_level(20, current=80)
        self.assertEqual(result, 85)  # 80 + 20//4 = 80 + 5 = 85
        # Actually: 20//4 = 5, 80 + 5 = 85

    def test_large_delta_negative(self):
        result = volume_delta_to_level(-20, current=10)
        self.assertEqual(result, 5)  # 10 + (-20)//4 = 10 + (-5) = 5

    def test_delta_zero(self):
        result = volume_delta_to_level(0, current=50)
        self.assertEqual(result, 50)

    def test_result_clamped_to_max(self):
        result = volume_delta_to_level(400, current=90, max_val=100)
        # 90 + 400//4 = 90 + 100 = 190, clamped to 100
        self.assertEqual(result, 100)

    def test_result_clamped_to_min(self):
        result = volume_delta_to_level(-400, current=10, min_val=0)
        # 10 + (-400)//4 = 10 + (-100) = -90, clamped to 0
        self.assertEqual(result, 0)

    def test_default_min_max(self):
        # Using default min=0, max=100
        result = volume_delta_to_level(500, current=99)
        self.assertEqual(result, 100)

    def test_integer_division(self):
        # delta=3, delta//4=0
        result = volume_delta_to_level(3, current=50)
        self.assertEqual(result, 50)

    def test_delta_one_is_zero_effect(self):
        # delta=1 or 2 or 3, delta//4=0 → no change
        for delta in [1, 2, 3]:
            result = volume_delta_to_level(delta, current=50)
            self.assertEqual(result, 50, f"delta={delta} should not change level")


if __name__ == '__main__':
    unittest.main(verbosity=2)
