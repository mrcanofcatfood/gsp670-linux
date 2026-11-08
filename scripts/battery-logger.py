#!/usr/bin/env python3
"""
Battery Logger for GSP 670

Monitor battery level over time, log to file with timestamps,
detect charging state changes, and run in background or cron.

Requirements:
    - pyudev (for device monitoring)
    - dbus-python (for UPower integration)

Install: pip install pyudev dbus-python
"""

import argparse
import sys
import os
import time
import datetime
import json
import signal
import threading
from dataclasses import dataclass, asdict
from typing import Optional, List
from enum import Enum

# Optional imports
try:
    import pyudev
    HAS_PYUDEV = True
except ImportError:
    HAS_PYUDEV = False

try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    import GLib
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class ChargingState(Enum):
    """Battery charging state."""
    UNKNOWN = "unknown"
    CHARGING = "charging"
    DISCHARGING = "discharging"
    FULL = "full"
    NOT_CHARGING = "not_charging"


@dataclass
class BatteryReading:
    """A single battery reading."""
    timestamp: str
    percentage: int
    state: str
    is_charging: bool
    time_to_full_minutes: Optional[int]  # None if unknown
    voltage_mv: Optional[int]  # Millivolts, if available


class BatteryLogger:
    """Battery level logger for GSP 670."""
    
    def __init__(self, log_file: str, interval: int = 60, use_upower: bool = True):
        """
        Initialize battery logger.
        
        Args:
            log_file: Path to log file
            interval: Polling interval in seconds
            use_upower: Use UPower for battery info (if available)
        """
        self.log_file = log_file
        self.interval = interval
        self.use_upower = use_upower and HAS_DBUS
        
        self.running = False
        self.last_percentage = None
        self.last_state = None
        self.charging_start_time = None
        self.charging_start_percentage = None
        
        # History for detecting trends
        self.history: List[BatteryReading] = []
        
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\nReceived signal, shutting down...")
        self.running = False
    
    def _init_dbus(self):
        """Initialize dbus for UPower."""
        if not HAS_DBUS:
            return None
        
        try:
            DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            upower = bus.get_object('org.freedesktop.UPower', 
                                   '/org/freedesktop/UPower')
            return dbus.Interface(upower, 'org.freedesktop.UPower')
        except Exception as e:
            print(f"Warning: Could not connect to UPower: {e}")
            return None
    
    def _find_gsp670_device(self, context) -> Optional[pyudev.Device]:
        """Find the GSP 670 USB device."""
        if not HAS_PYUDEV:
            return None
        
        try:
            for device in context.list_devices(subsystem='usb', 
                                               ID_VENDOR_EPOS=True):
                if 'GSP' in device.get('ID_MODEL', '') or \
                   'G670' in device.get('ID_MODEL', ''):
                    return device
        except Exception:
            pass
        
        # Fallback: search by vendor ID
        try:
            for device in context.list_devices(subsystem='usb'):
                vendor = device.get('ID_VENDOR_ID', '')
                model = device.get('ID_MODEL_ID', '')
                # EPOS vendor ID is 1390 (0x056b)
                if vendor == '056b' or 'EPOS' in device.get('ID_VENDOR', ''):
                    if 'GSP' in device.get('ID_MODEL', ''):
                        return device
        except Exception:
            pass
        
        return None
    
    def _get_battery_from_sysfs(self) -> Optional[BatteryReading]:
        """Read battery info from sysfs (works without UPower)."""
        # Look for battery devices
        battery_base = '/sys/class/power_supply'
        
        if not os.path.exists(battery_base):
            return None
        
        try:
            for supply in os.listdir(battery_base):
                supply_path = os.path.join(battery_base, supply)
                present_file = os.path.join(supply_path, 'present')
                
                if os.path.exists(present_file):
                    with open(present_file) as f:
                        if f.read().strip() != '1':
                            continue
                
                # Read capacity/percentage
                capacity_file = os.path.join(supply_path, 'capacity')
                if not os.path.exists(capacity_file):
                    continue
                
                with open(capacity_file) as f:
                    percentage = int(f.read().strip())
                
                # Read status
                status_file = os.path.join(supply_path, 'status')
                status = 'unknown'
                is_charging = False
                
                if os.path.exists(status_file):
                    status_str = f.read().strip().lower()
                    if 'charging' in status_str:
                        status = 'charging'
                        is_charging = True
                    elif 'full' in status_str:
                        status = 'full'
                    elif 'discharging' in status_str:
                        status = 'discharging'
                    elif 'not charging' in status_str:
                        status = 'not_charging'
                
                # Read voltage if available
                voltage_mv = None
                voltage_file = os.path.join(supply_path, 'voltage_now')
                if os.path.exists(voltage_file):
                    try:
                        with open(voltage_file) as f:
                            voltage_mv = int(f.read().strip()) // 1000
                    except Exception:
                        pass
                
                # Time to full (not typically available via sysfs)
                time_to_full = None
                
                return BatteryReading(
                    timestamp=datetime.datetime.now().isoformat(),
                    percentage=percentage,
                    state=status,
                    is_charging=is_charging,
                    time_to_full_minutes=time_to_full,
                    voltage_mv=voltage_mv
                )
        except Exception as e:
            print(f"Error reading battery from sysfs: {e}")
        
        return None
    
    def _get_battery_from_upower(self, upower) -> Optional[BatteryReading]:
        """Read battery info from UPower."""
        if not upower:
            return None
        
        try:
            devices = upower.GetDevices()
            
            for device_path in devices:
                # Get device properties
                device_obj = dbus.SystemBus().get_object(
                    'org.freedesktop.UPower', device_path)
                props = dbus.Interface(device_obj, 'org.freedesktop.DBus.Properties')
                
                # Check if this is a battery
                type_ = props.Get('org.freedesktop.UPower.Device', 'Type')
                if type_ != 2:  # 2 = Battery
                    continue
                
                # Check if it's our device (GSP 670)
                model = props.Get('org.freedesktop.UPower.Device', 'Model')
                if 'GSP' not in model and 'G670' not in model:
                    # Also check parent device
                    serial = props.Get('org.freedesktop.UPower.Device', 'Serial')
                    if 'GSP' not in (model or '') and 'G670' not in (model or ''):
                        continue
                
                percentage = int(props.Get('org.freedesktop.UPower.Device', 'Percentage'))
                state = props.Get('org.freedesktop.UPower.Device', 'State')
                
                # Map state to our enum
                state_map = {
                    1: ChargingState.CHARGING,
                    2: ChargingState.DISCHARGING,
                    3: ChargingState.FULL,
                    4: ChargingState.NOT_CHARGING,
                    5: ChargingState.DISCHARGING,  # Empty
                }
                state_enum = state_map.get(state, ChargingState.UNKNOWN)
                is_charging = state_enum == ChargingState.CHARGING
                
                # Get time to full/empty
                time_to_full = None
                try:
                    time_to_empty = props.Get('org.freedesktop.UPower.Device', 'TimeToEmpty')
                    time_to_full_sec = props.Get('org.freedesktop.UPower.Device', 'TimeToFull')
                    
                    if time_to_full_sec > 0:
                        time_to_full = int(time_to_full_sec // 60)
                    elif time_to_empty > 0:
                        time_to_full = -int(time_to_empty // 60)  # Negative = time to empty
                except Exception:
                    pass
                
                # Get voltage
                voltage_mv = None
                try:
                    voltage = props.Get('org.freedesktop.UPower.Device', 'Voltage')
                    voltage_mv = int(voltage * 1000)  # Convert from V to mV
                except Exception:
                    pass
                
                return BatteryReading(
                    timestamp=datetime.datetime.now().isoformat(),
                    percentage=percentage,
                    state=state_enum.value,
                    is_charging=is_charging,
                    time_to_full_minutes=time_to_full,
                    voltage_mv=voltage_mv
                )
        except Exception as e:
            print(f"Error reading from UPower: {e}")
        
        return None
    
    def _detect_state_change(self, reading: BatteryReading) -> Optional[str]:
        """Detect and describe state changes."""
        changes = []
        
        if self.last_percentage is not None:
            delta = reading.percentage - self.last_percentage
            
            if delta != 0:
                direction = "increased" if delta > 0 else "decreased"
                changes.append(f"Battery {direction} from {self.last_percentage}% to {reading.percentage}%")
                
                # Track charging rate
                if reading.is_charging:
                    if self.charging_start_percentage is None:
                        self.charging_start_percentage = self.last_percentage
                        self.charging_start_time = datetime.datetime.now()
                    elif delta > 0:
                        elapsed_minutes = (datetime.datetime.now() - self.charging_start_time).total_seconds() / 60
                        if elapsed_minutes > 1:
                            rate = delta / elapsed_minutes
                            estimated_full_time = (100 - reading.percentage) / rate if rate > 0 else None
                            if estimated_full_time:
                                changes.append(f"Estimated time to full: ~{estimated_full_time:.0f} minutes")
                else:
                    # Reset charging tracking when discharging
                    self.charging_start_percentage = None
                    self.charging_start_time = None
        
        if self.last_state is not None and reading.state != self.last_state:
            changes.append(f"State changed from {self.last_state} to {reading.state}")
            
            if reading.state == 'charging':
                changes.append("Started charging")
            elif reading.state == 'discharging':
                changes.append("Started discharging")
            elif reading.state == 'full':
                changes.append("Battery fully charged!")
        
        self.last_percentage = reading.percentage
        self.last_state = reading.state
        
        return "; ".join(changes) if changes else None
    
    def _log_reading(self, reading: BatteryReading, change_description: Optional[str] = None):
        """Log a battery reading to file."""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # CSV format
        csv_line = (f"{timestamp},{reading.percentage},{reading.state},"
                   f"{'1' if reading.is_charging else '0'},"
                   f"{reading.time_to_full_minutes or ''},"
                   f"{reading.voltage_mv or ''}\n")
        
        # Append to log file
        with open(self.log_file, 'a') as f:
            f.write(csv_line)
        
        # Print to console if running in foreground
        print(f"[{timestamp}] Battery: {reading.percentage}% ({reading.state})", end="")
        
        if change_description:
            print(f" - {change_description}")
        else:
            print()
        
        # Print additional info
        if reading.time_to_full_minutes is not None:
            if reading.time_to_full_minutes > 0:
                print(f"  Time to full: ~{reading.time_to_full_minutes} minutes")
            else:
                print(f"  Time to empty: ~{-reading.time_to_full_minutes} minutes")
        
        if reading.voltage_mv:
            print(f"  Voltage: {reading.voltage_mv} mV")
    
    def _ensure_log_header(self):
        """Ensure log file has header row."""
        if not os.path.exists(self.log_file) or os.path.getsize(self.log_file) == 0:
            with open(self.log_file, 'w') as f:
                f.write("timestamp,percentage,state,is_charging,time_to_full_minutes,voltage_mv\n")
    
    def get_current_reading(self) -> Optional[BatteryReading]:
        """Get current battery reading using best available method."""
        if self.use_upower:
            upower = self._init_dbus()
            reading = self._get_battery_from_upower(upower)
            if reading:
                return reading
        
        return self._get_battery_from_sysfs()
    
    def run_once(self) -> Optional[BatteryReading]:
        """Take a single reading and log it."""
        reading = self.get_current_reading()
        
        if reading:
            self._ensure_log_header()
            change = self._detect_state_change(reading)
            self._log_reading(reading, change)
            self.history.append(reading)
        else:
            print("Could not read battery status")
        
        return reading
    
    def run_continuous(self):
        """Run continuous monitoring loop."""
        self.running = True
        self.setup_signal_handlers()
        
        print(f"Battery Logger Starting")
        print(f"Log file: {self.log_file}")
        print(f"Polling interval: {self.interval} seconds")
        print(f"Press Ctrl+C to stop")
        print()
        
        self._ensure_log_header()
        
        # Initial reading
        self.run_once()
        
        # Continuous monitoring
        while self.running:
            time.sleep(self.interval)
            if self.running:
                self.run_once()
        
        print("\nLogger stopped")
        print(f"Total readings: {len(self.history)}")
        
        # Print summary
        if self.history:
            percentages = [r.percentage for r in self.history]
            print(f"Battery range: {min(percentages)}% - {max(percentages)}%")
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate a report from collected history."""
        if not self.history:
            return "No data available"
        
        report_lines = [
            "GSP 670 Battery Log Report",
            "=" * 50,
            f"Generated: {datetime.datetime.now().isoformat()}",
            "",
            f"Total readings: {len(self.history)}",
            f"Duration: {self.history[0].timestamp} to {self.history[-1].timestamp}",
            "",
            "Summary:",
            "-" * 50,
        ]
        
        percentages = [r.percentage for r in self.history]
        report_lines.append(f"  Min battery: {min(percentages)}%")
        report_lines.append(f"  Max battery: {max(percentages)}%")
        
        # Calculate charge/discharge rate
        charging_readings = [r for r in self.history if r.is_charging]
        if charging_readings:
            avg_charge_rate = sum(
                r.percentage - self.history[i-1].percentage 
                for i, r in enumerate(charging_readings) if i > 0
            ) / max(1, len(charging_readings) - 1)
            report_lines.append(f"  Avg charge rate: {avg_charge_rate:.1f}% per reading")
        
        discharging_readings = [r for r in self.history if not r.is_charging]
        if discharging_readings:
            avg_discharge_rate = sum(
                r.percentage - self.history[i-1].percentage 
                for i, r in enumerate(discharging_readings) if i > 0 and self.history[i-1].is_charging
            ) / max(1, len(discharging_readings) - 1)
            report_lines.append(f"  Avg discharge rate: {avg_discharge_rate:.1f}% per reading")
        
        # State changes
        state_changes = sum(
            1 for i, r in enumerate(self.history) 
            if i > 0 and r.state != self.history[i-1].state
        )
        report_lines.append(f"  State changes: {state_changes}")
        
        report = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            print(f"Report saved to: {output_file}")
        
        return report


def main():
    parser = argparse.ArgumentParser(
        description="GSP 670 Battery Logger"
    )
    parser.add_argument('--log-file', '-l', default='~/.local/share/gsp670/battery.log',
                        help='Log file path (default: ~/.local/share/gsp670/battery.log)')
    parser.add_argument('--interval', '-i', type=int, default=60,
                        help='Polling interval in seconds (default: 60)')
    parser.add_argument('--once', '-1', action='store_true',
                        help='Take a single reading and exit')
    parser.add_argument('--report', '-r', type=str,
                        help='Generate report from log file')
    parser.add_argument('--no-upower', action='store_true',
                        help='Disable UPower, use sysfs only')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Output reading as JSON')
    
    args = parser.parse_args()
    
    # Expand path
    log_file = os.path.expanduser(args.log_file)
    
    # Ensure directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    # Create logger
    logger = BatteryLogger(
        log_file=log_file,
        interval=args.interval,
        use_upower=not args.no_upower
    )
    
    # Handle report generation
    if args.report:
        logger.history = []  # We don't need history for report
        
        # Read existing log file
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                next(f)  # Skip header
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 4:
                        reading = BatteryReading(
                            timestamp=parts[0],
                            percentage=int(parts[1]),
                            state=parts[2],
                            is_charging=parts[3] == '1',
                            time_to_full_minutes=int(parts[4]) if parts[4] else None,
                            voltage_mv=int(parts[5]) if len(parts) > 5 and parts[5] else None
                        )
                        logger.history.append(reading)
        
        report = logger.generate_report(args.report)
        print(report)
        return 0
    
    # Take single reading
    if args.once:
        reading = logger.run_once()
        if reading and args.json:
            print(json.dumps(asdict(reading), indent=2))
        return 0 if reading else 1
    
    # Run continuous
    logger.run_continuous()
    return 0


if __name__ == '__main__':
    sys.exit(main())
