#!/usr/bin/env python3
"""
Device configuration persistence for GSP 670.

Stores and retrieves device settings using XDG Base Directory specification.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List

# XDG Base Directory paths — expanduser() so ~ resolves correctly
XDG_CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME', '~/.config')).expanduser()
XDG_DATA_HOME = Path(os.environ.get('XDG_DATA_HOME', '~/.local/share')).expanduser()

# App-specific directories — computed lazily so tests can override env vars
def _get_config_dir() -> Path:
    return XDG_CONFIG_HOME / 'gsp670'

def _get_data_dir() -> Path:
    return XDG_DATA_HOME / 'gsp670'

CONFIG_DIR = None  # lazily initialized
DATA_DIR = None

def _init_dirs():
    global CONFIG_DIR, DATA_DIR
    CONFIG_DIR = _get_config_dir()
    DATA_DIR = _get_data_dir()

def get_config_dir() -> Path:
    """Return CONFIG_DIR, initializing it on first call."""
    if CONFIG_DIR is None:
        _init_dirs()
    return CONFIG_DIR

def get_data_dir() -> Path:
    """Return DATA_DIR, initializing it on first call."""
    if DATA_DIR is None:
        _init_dirs()
    return DATA_DIR


@dataclass
class EQPreset:
    """Equalizer preset configuration."""
    name: str = "Default"
    enabled: bool = False
    # 10-band EQ gains (dB), -12 to +12
    bands: List[int] = field(default_factory=lambda: [0] * 10)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EQPreset':
        return cls(**data)


@dataclass 
class DeviceConfig:
    """Device configuration persisted across sessions."""
    # Device identity (from device)
    serial: Optional[str] = None
    firmware_version: Optional[str] = None
    
    # Audio settings
    sidetone_level: int = 50  # 0-100
    noise_reduction_level: int = 0  # 0-3 (off, low, medium, high)
    auto_power_off_minutes: int = 30  # 0 = disabled
    
    # Volume limiter
    volume_limiter_enabled: bool = False
    volume_limiter_max: int = 100  # 1-100
    
    # EQ presets
    eq_presets: List[EQPreset] = field(default_factory=list)
    active_eq_preset: Optional[str] = None
    
    # Last known device path (for auto-reconnect)
    last_device_path: Optional[str] = None
    
    # Metadata
    config_version: int = 1
    
    def to_dict(self) -> dict:
        result = asdict(self)
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DeviceConfig':
        # Handle EQ presets
        if 'eq_presets' in data and data['eq_presets']:
            data['eq_presets'] = [EQPreset.from_dict(p) for p in data['eq_presets']]
        return cls(**data)
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to JSON file."""
        if path is None:
            path = get_config_dir() / 'config.json'
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> 'DeviceConfig':
        """Load configuration from JSON file."""
        if path is None:
            path = get_config_dir() / 'config.json'
        
        path = Path(path)
        
        if not path.exists():
            return cls()
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            # Corrupted config - start fresh
            return cls()
    
    @classmethod
    def for_device(cls, serial: str) -> 'DeviceConfig':
        """Load configuration for a specific device, or return default."""
        config = cls.load()
        if config.serial != serial:
            # Different device - reset device-specific settings but keep global
            config.serial = serial
        return config


def get_default_config() -> DeviceConfig:
    """Get default configuration."""
    return DeviceConfig()


def save_device_config(config: DeviceConfig, serial: Optional[str] = None) -> None:
    """
    Save device configuration.
    
    If serial is provided, saves to a device-specific file.
    Otherwise saves to the default config file.
    """
    if serial:
        path = get_data_dir() / f'device_{serial}.json'
    else:
        path = get_config_dir() / 'config.json'
    config.save(path)


def load_device_config(serial: Optional[str] = None) -> DeviceConfig:
    """
    Load device configuration.
    
    If serial is provided, loads from device-specific file.
    Otherwise loads from default config file.
    """
    if serial:
        path = get_data_dir() / f'device_{serial}.json'
        config = DeviceConfig.load(path)
        config.serial = serial
        return config
    return DeviceConfig.load()



