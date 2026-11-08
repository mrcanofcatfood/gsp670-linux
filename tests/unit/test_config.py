#!/usr/bin/env python3
"""
Unit tests for the config module.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, 'src')

from gsp670.config import (
    DeviceConfig,
    EQPreset,
    get_default_config,
    load_device_config,
    save_device_config,
)


class TestEQPreset(unittest.TestCase):
    """Test EQPreset dataclass."""

    def test_default_preset(self):
        """Test default EQ preset values."""
        eq = EQPreset()
        assert eq.name == "Default"
        assert eq.enabled is False
        assert len(eq.bands) == 10
        assert all(b == 0 for b in eq.bands)

    def test_custom_preset(self):
        """Test custom EQ preset."""
        eq = EQPreset(name="Rock", enabled=True, bands=[5]*10)
        assert eq.name == "Rock"
        assert eq.enabled is True
        assert eq.bands == [5]*10

    def test_serialization(self):
        """Test EQ preset to/from dict."""
        eq = EQPreset(name="Test", bands=[1,2,3,4,5,6,7,8,9,10])
        data = eq.to_dict()
        restored = EQPreset.from_dict(data)
        assert restored.name == eq.name
        assert restored.bands == eq.bands


class TestDeviceConfig(unittest.TestCase):
    """Test DeviceConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DeviceConfig()
        assert config.serial is None
        assert config.sidetone_level == 50
        assert config.noise_reduction_level == 0
        assert config.auto_power_off_minutes == 30
        assert config.volume_limiter_enabled is False
        assert config.config_version == 1

    def test_serialization(self):
        """Test config to/from dict."""
        config = DeviceConfig()
        config.serial = "TEST123"
        config.sidetone_level = 75
        eq = EQPreset(name="Bass Boost", bands=[10]*10)
        config.eq_presets.append(eq)

        data = config.to_dict()
        restored = DeviceConfig.from_dict(data)

        assert restored.serial == "TEST123"
        assert restored.sidetone_level == 75
        assert len(restored.eq_presets) == 1
        assert restored.eq_presets[0].name == "Bass Boost"

    def test_save_load(self):
        """Test save and load to temporary file."""
        config = DeviceConfig()
        config.serial = "TEST456"
        config.sidetone_level = 80

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test_config.json')
            config.save(path)

            assert os.path.exists(path)

            loaded = DeviceConfig.load(path)
            assert loaded.serial == "TEST456"
            assert loaded.sidetone_level == 80

    def test_load_nonexistent(self):
        """Test loading nonexistent config returns default."""
        loaded = DeviceConfig.load('/nonexistent/path/config.json')
        assert loaded.serial is None
        assert loaded.sidetone_level == 50

    def test_device_specific_config(self):
        """Test loading device-specific config."""
        with tempfile.TemporaryDirectory():
            # Create a device-specific config
            config = DeviceConfig()
            config.serial = "DEVICE789"
            config.sidetone_level = 60

            save_device_config(config, serial="DEVICE789")

            # Load it back
            loaded = load_device_config(serial="DEVICE789")
            assert loaded.serial == "DEVICE789"
            assert loaded.sidetone_level == 60


class TestGetDefaultConfig(unittest.TestCase):
    """Test default config factory."""

    def test_returns_device_config(self):
        """Test that get_default_config returns a DeviceConfig."""
        config = get_default_config()
        assert isinstance(config, DeviceConfig)
        assert config.sidetone_level == 50


if __name__ == '__main__':
    import unittest
    unittest.main(verbosity=2)
