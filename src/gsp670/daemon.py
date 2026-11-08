#!/usr/bin/env python3
"""
GSP 670 Daemon

Long-running daemon that:
1. Provides the D-Bus interface (via Gsp670DBusService)
2. Logs battery state changes to a CSV file

Intended to run as a systemd service via gsp670-daemon.service.

Usage:
    python -m gsp670.daemon [--log-file PATH] [-v]
"""

import os
import sys
import csv
import time
import argparse
import logging
import threading
from datetime import datetime
from pathlib import Path

# When run as 'python -m gsp670.daemon' from src/, the parent of src/ should
# be on the path so 'from gsp670 import ...' works.
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from gsp670._compat import MissingDependency

try:
    from gsp670.dbus_service import Gsp670DBusService, BUS_NAME
except MissingDependency as _exc:
    # The daemon is an optional extra; surface the actionable install hint
    # instead of a bare ImportError traceback.
    raise MissingDependency(
        f"{_exc}\n\n"
        "The GSP 670 D-Bus daemon requires the optional 'dbus' extra."
    ) from _exc

logger = logging.getLogger('gsp670.daemon')


class BatteryLogger:
    """
    Appends battery state to a CSV log file.
    
    Log format: timestamp,level,charging
    """
    
    def __init__(self, log_path: Path):
        self._path = log_path
        self._lock = threading.Lock()
        self._ensure_header()
    
    def _ensure_header(self):
        """Create file with header if it doesn't exist."""
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'level', 'charging'])
    
    def log(self, level: int, charging: bool):
        """Append a battery reading."""
        with self._lock:
            try:
                with open(self._path, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(timespec='seconds'),
                        level,
                        1 if charging else 0
                    ])
            except Exception as e:
                logger.warning(f"Battery log write failed: {e}")


class Daemon(Gsp670DBusService):
    """
    Extended D-Bus service that also logs battery state.
    
    Inherits all D-Bus methods and signals from Gsp670DBusService,
    and adds battery logging on BatteryChanged signals.
    """
    
    def __init__(self, bus, device_mode: str = 'dongle',
                 battery_log_path: Path = None):
        super().__init__(bus, device_mode)
        self._battery_logger = None
        if battery_log_path:
            self._battery_logger = BatteryLogger(battery_log_path)
    
    def BatteryChanged(self, level: int, charging: bool):
        """Override to also log battery state."""
        # Call the parent signal emitter
        super().BatteryChanged(level, charging)
        # Log to CSV
        if self._battery_logger is not None and level >= 0:
            self._battery_logger.log(level, charging)


def _run_daemon(bus_type: str = 'system',
                device_mode: str = 'dongle',
                battery_log_path: Path = None,
                verbose: bool = False):
    """Run the full daemon (D-Bus + battery logger)."""
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    
    from gsp670.dbus_service import _request_bus_name, Gsp670DBusService
    
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    if bus_type == 'session':
        bus = dbus.SessionBus()
    else:
        bus = dbus.SystemBus()
    
    if not _request_bus_name(bus):
        logger.error(f"Bus name {BUS_NAME} is already taken")
        sys.exit(1)
    
    service = Daemon(bus, device_mode=device_mode,
                     battery_log_path=battery_log_path)
    service.start()
    
    logger.info(f"GSP 670 daemon running on {bus_type} bus")
    logger.info(f"Battery log: {battery_log_path or 'disabled'}")
    
    try:
        mainloop = GLib.MainLoop()
        mainloop.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        service.stop()


def main():
    # Default log location: XDG_DATA_HOME/gsp670/battery-log.csv
    default_log = Path.home() / '.local' / 'share' / 'gsp670' / 'battery-log.csv'
    
    parser = argparse.ArgumentParser(description='GSP 670 Daemon')
    parser.add_argument('--bus', choices=['system', 'session'], default='system',
                        help='D-Bus bus to use (default: system)')
    parser.add_argument('--device', choices=['dongle', 'headset'], default='dongle',
                        help='Device mode (default: dongle)')
    parser.add_argument('--log-file', type=Path, default=default_log,
                        help=f'Battery log CSV path (default: {default_log})')
    parser.add_argument('--no-log', action='store_true',
                        help='Disable battery logging')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(name)s: %(levelname)s %(message)s'
    )
    
    log_path = None if args.no_log else args.log_file
    
    _run_daemon(
        bus_type=args.bus,
        device_mode=args.device,
        battery_log_path=log_path,
        verbose=args.verbose
    )


if __name__ == '__main__':
    main()
