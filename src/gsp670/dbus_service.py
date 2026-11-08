#!/usr/bin/env python3
"""
D-Bus service for GSP 670 device control.

Provides a system D-Bus interface for battery, sidetone, and link state.

Requires: dbus-python, GLib (gi.repository.GLib)

This module is only needed for the optional D-Bus daemon. The ``gsp670`` CLI
and the audio path of this project do **not** require it. If the D-Bus stack
is missing, importing this module raises
:class:`gsp670._compat.MissingDependency` with installation instructions
rather than a bare ImportError.

Usage:
    # As a standalone service:
    python -m gsp670.dbus_service

    # Or import and use the Gsp670DBusService class directly.
"""

import argparse
import logging
import sys
import threading
import time
from typing import Optional

from ._compat import require_dbus

try:
    dbus, GLib = require_dbus()
except Exception as _exc:  # pragma: no cover - depends on environment
    # Re-raise with the actionable message from _compat.
    raise

from gsp670 import GSA70Device, GSP670Device
from gsp670.config import load_device_config, save_device_config
from gsp670.events import (
    BatteryEvent,
    ChargingEvent,
    SidetoneEvent,
    SubDevicesEvent,
    parse_frame_event,
)

# dbus.service / dbus.mainloop.glib are needed as attributes of `dbus`; the
# require_dbus() helper grafts them on.
dbus_service = dbus.service
dbus_mainloop_glib = dbus.mainloop.glib

BUS_NAME = 'com.epos.gsp670'
OBJECT_PATH = '/com/epos/gsp670'

logger = logging.getLogger('gsp670.dbus')


class Gsp670DBusService(dbus.service.Object):
    """
    D-Bus service providing GSP 670 device control.

    Well-known name: com.epos.gsp670
    Object path: /com/epos/gsp670

    Only the *verified* SECOM controls are exposed. Volume, speaker/mic EQ,
    reverb, surround and voice enhancement are OS/APO software DSP on Windows,
    not device commands, and are deliberately absent here.

    Methods:
    - GetBattery() -> (level: int, charging: bool) or (-1, False) if unavailable
    - GetSidetone() -> int  (0-255, or -1 if unavailable)
    - SetSidetone(level: int) -> bool
    - GetNoiseReduction() -> int  (0-255, or -1 if unavailable)
    - SetNoiseReduction(level: int) -> bool
    - GetAutoPowerOff() -> int  (raw device value, or -1 if unavailable)
    - SetAutoPowerOff(level: int) -> bool
    - GetLatency() -> int  (read-only, or -1 if unavailable)
    - GetDeviceName() -> s
    - GetSerial() -> s
    - GetFirmwareVersion() -> s
    - GetSubDevices() -> int  (linked sub-devices; 0 = unlinked)
    - RefreshDeviceInfo() -> bool
    - GetLinkState() -> bool
    - IsAvailable() -> bool

    Signals:
    - BatteryChanged(level: int, charging: bool)
    - SidetoneChanged(level: int)
    - NoiseReductionChanged(level: int)
    - AutoPowerOffChanged(level: int)
    - SubDevicesChanged(count: int)
    - DeviceInfoChanged()
    - LinkChanged(connected: bool)

    Signals are emitted from both polled snapshots (5 s fallback) and pushed
    device->host events (drained every poll cycle — no subscription needed).
    """

    def __init__(self, bus: dbus.Bus, device_mode: str = 'dongle'):
        """
        Initialize the D-Bus service.

        Args:
            bus: D-Bus connection (session or system bus)
            device_mode: 'dongle' for GSA70Device, 'headset' for GSP670Device
        """
        dbus.service.Object.__init__(self, bus, OBJECT_PATH)
        self._bus = bus
        self._device_mode = device_mode
        self._device: Optional[GSA70Device | GSP670Device] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False

        # Cached state for change detection
        self._last_battery: int = -1
        self._last_charging: bool = False
        self._last_sidetone: int = -1
        self._last_noise_reduction: int = -1
        self._last_auto_power_off: int = -1
        self._last_subdevices: int = -1
        self._last_link: bool = False

        # Device identity (read once when the device is opened)
        self._device_name: str = ''
        self._serial: str = ''
        self._firmware: str = ''

    def _open_device(self) -> bool:
        """Try to open the device. Returns True on success."""
        try:
            if self._device_mode == 'dongle':
                self._device = GSA70Device()
            else:
                self._device = GSP670Device()
            self._device.open()
            logger.info(f"Device opened in {self._device_mode} mode")
            self._refresh_device_info()
            return True
        except Exception as e:
            logger.debug(f"Device not available: {e}")
            return False

    def _close_device(self):
        """Close the device if open."""
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        # Identity is re-read asynchronously when the value is next requested,
        # so clear it here to avoid reporting a stale device's identity.
        self._device_name = ''
        self._serial = ''
        self._firmware = ''

    def _refresh_device_info(self) -> bool:
        """
        Read the device identity (name, serial, firmware) and cache it.

        Emits ``DeviceInfoChanged`` if any value changed. Returns True on
        success (at least one value read).
        """
        if self._device is None:
            return False
        changed = False
        try:
            name = self._device.get_device_name()
            if name and name != self._device_name:
                self._device_name = name
                changed = True
        except Exception:
            pass
        try:
            serial = self._device.get_serial_number()
            if serial and serial != self._serial:
                self._serial = serial
                changed = True
        except Exception:
            pass
        try:
            fw = self._device.get_firmware_version()
            if fw and fw != self._firmware:
                self._firmware = fw
                changed = True
        except Exception:
            pass
        if changed:
            logger.debug(
                f"Device info: name={self._device_name!r} "
                f"serial={self._serial!r} fw={self._firmware!r}")
            self.DeviceInfoChanged()
        return bool(self._device_name or self._serial or self._firmware)

    def _poll_state(self):
        """Poll device state and emit signals on changes."""
        while self._running:
            if self._device is None or not self._device.is_connected:
                if not self._open_device():
                    time.sleep(5)
                    continue

            try:
                self._poll_once()
            except Exception as e:
                logger.debug(f"Poll error: {e}")
                self._close_device()
                time.sleep(2)
                continue

            time.sleep(5)  # Poll every 5 seconds

    def _poll_once(self):
        """
        Run a single poll iteration and emit signals on change.

        Split out from :meth:`_poll_state` so it can be unit-tested without a
        running loop. Drains push events first (those are lower-latency and
        need no subscription), then snapshots the state that has no push
        equivalent.
        """
        # 1. Drain push events (the dongle emits events unconditionally once
        #    the headset is linked, so no subscription handshake is needed).
        self._drain_events()

        # 2. Poll battery (fallback to -1 when unavailable)
        battery = self._get_battery_internal()
        if battery is not None:
            level, charging = battery
            if level != self._last_battery or charging != self._last_charging:
                self.BatteryChanged(level, charging)
                self._last_battery = level
                self._last_charging = charging

        # 3. Poll sidetone
        sidetone = self._get_sidetone_internal()
        if sidetone is not None and sidetone != self._last_sidetone:
            self.SidetoneChanged(sidetone)
            self._last_sidetone = sidetone

        # 4. Poll noise reduction
        nr = self._get_noise_reduction_internal()
        if nr is not None and nr != self._last_noise_reduction:
            self.NoiseReductionChanged(nr)
            self._last_noise_reduction = nr

        # 5. Poll auto power off
        apo = self._get_auto_power_off_internal()
        if apo is not None and apo != self._last_auto_power_off:
            self.AutoPowerOffChanged(apo)
            self._last_auto_power_off = apo

        # 6. Poll linked sub-devices (0 = headset not linked)
        sub = self._get_subdevices_internal()
        if sub is not None and sub != self._last_subdevices:
            self.SubDevicesChanged(sub)
            self._last_subdevices = sub

        # 7. Poll link state
        link = self._device.is_connected
        if link != self._last_link:
            self.LinkChanged(link)
            self._last_link = link

    def _drain_events(self):
        """
        Read pending device->host push events and emit D-Bus signals.

        The GSA 70 dongle pushes events without a subscription handshake
        (GAP-RE-1 resolved 2026-10-13). This drains up to 16 queued reports and
        maps parsed events to the public signals:

        - BatteryEvent / ChargingEvent      -> BatteryChanged(level, charging)
        - SidetoneEvent                     -> SidetoneChanged(level)
        - SubDevicesEvent (count > 0)       -> LinkChanged(connected)

        LinkEvent (raw ConnectionStatus) semantics are not yet documented, so
        it is intentionally ignored here.
        """
        for _ in range(16):
            try:
                f = self._device.read(timeout_ms=50)
            except Exception:
                break
            if f is None:
                break
            evt = parse_frame_event(f)
            if evt is None:
                continue

            if isinstance(evt, BatteryEvent):
                charging = bool(evt.charging_changed) if evt.charging_changed is not None \
                    else self._last_charging
                if evt.level != self._last_battery or charging != self._last_charging:
                    logger.debug(f"Event battery: {evt.level}% charging={charging}")
                    self.BatteryChanged(evt.level, charging)
                    self._last_battery = evt.level
                    self._last_charging = charging

            elif isinstance(evt, ChargingEvent):
                if self._last_battery < 0:
                    continue  # no level yet; wait for a BatteryEvent or poll
                charging = evt.state > 0
                if charging != self._last_charging:
                    logger.debug(f"Event charging: state={evt.state}")
                    self.BatteryChanged(self._last_battery, charging)
                    self._last_charging = charging

            elif isinstance(evt, SidetoneEvent):
                level = evt.level & 0xFF
                if level != self._last_sidetone:
                    logger.debug(f"Event sidetone: {level}")
                    self.SidetoneChanged(level)
                    self._last_sidetone = level

            elif isinstance(evt, SubDevicesEvent):
                link = evt.count > 0
                if link != self._last_link:
                    logger.debug(f"Event link: sub_devices={evt.count}")
                    self.LinkChanged(link)
                    self._last_link = link

    def _get_battery_internal(self):
        """Get battery level and charging state. Returns (level, charging) or None."""
        try:
            level = self._device.get_battery_percentage()
            if level is None:
                return None
            # Charging state comes from push events (BatteryEvent /
            # ChargingEvent) drained in _drain_events(); the poll falls back
            # to the last known state.
            return (level, self._last_charging)
        except Exception:
            return None

    def _get_sidetone_internal(self):
        """Get current sidetone level, or None if unavailable."""
        try:
            return self._device.get_sidetone()
        except Exception:
            return None

    def _get_noise_reduction_internal(self):
        """Get current noise reduction level, or None if unavailable."""
        try:
            return self._device.get_noise_reduction()
        except Exception:
            return None

    def _get_auto_power_off_internal(self):
        """Get current auto-power-off value, or None if unavailable."""
        try:
            return self._device.get_auto_power_off()
        except Exception:
            return None

    def _get_subdevices_internal(self):
        """Get the number of linked sub-devices, or None if unavailable."""
        try:
            return self._device.get_subdevices_connected()
        except Exception:
            return None

    # ─── D-Bus Methods ────────────────────────────────────────────────

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='(ib)')
    def GetBattery(self) -> dbus.Struct:
        """
        Get battery level (0-100) and charging state.

        Returns (level, charging) or (-1, False) if unavailable.
        """
        result = self._get_battery_internal()
        if result is None:
            return dbus.Struct([dbus.Int32(-1), dbus.Boolean(False)])
        return dbus.Struct([dbus.Int32(result[0]), dbus.Boolean(result[1])])

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='i')
    def GetSidetone(self) -> int:
        """Get sidetone level (0-100), or -1 if unavailable."""
        result = self._get_sidetone_internal()
        return result if result is not None else -1

    @dbus.service.method(BUS_NAME, in_signature='i', out_signature='b')
    def SetSidetone(self, level: int) -> bool:
        """
        Set sidetone level (0-100).

        Returns True on success, False on failure.
        """
        if not 0 <= level <= 100:
            return False
        try:
            ok = self._device.set_sidetone(level)
            if ok:
                try:
                    cfg = load_device_config()
                    cfg.sidetone_level = level
                    save_device_config(cfg)
                except Exception:
                    pass  # Config failure shouldn't fail the command
            return ok
        except Exception as e:
            logger.debug(f"SetSidetone failed: {e}")
            return False

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='i')
    def GetNoiseReduction(self) -> int:
        """Get noise reduction level (0=off, 1=low, 2=medium, 3=high), or -1 if unavailable."""
        result = self._get_noise_reduction_internal()
        return result if result is not None else -1

    @dbus.service.method(BUS_NAME, in_signature='i', out_signature='b')
    def SetNoiseReduction(self, level: int) -> bool:
        """
        Set noise reduction level (0=off, 1=low, 2=medium, 3=high).

        Returns True on success, False on failure.
        """
        if not 0 <= level <= 3:
            return False
        try:
            ok = self._device.set_noise_reduction(level)
            if ok:
                try:
                    cfg = load_device_config()
                    cfg.noise_reduction_level = level
                    save_device_config(cfg)
                except Exception:
                    pass
            return ok
        except Exception as e:
            logger.debug(f"SetNoiseReduction failed: {e}")
            return False

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='i')
    def GetAutoPowerOff(self) -> int:
        """Get the auto-power-off value (raw device value), or -1 if unavailable."""
        result = self._get_auto_power_off_internal()
        return result if result is not None else -1

    @dbus.service.method(BUS_NAME, in_signature='i', out_signature='b')
    def SetAutoPowerOff(self, level: int) -> bool:
        """
        Set the auto-power-off value (0-255; device-dependent mapping).

        Returns True on success, False on failure.
        """
        if not 0 <= level <= 255:
            return False
        try:
            ok = self._device.set_auto_power_off(level)
            if ok:
                try:
                    cfg = load_device_config()
                    cfg.auto_power_off_minutes = level
                    save_device_config(cfg)
                except Exception:
                    pass
            return ok
        except Exception as e:
            logger.debug(f"SetAutoPowerOff failed: {e}")
            return False

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='i')
    def GetLatency(self) -> int:
        """Get the audio latency level (read-only), or -1 if unavailable."""
        if self._device is None:
            return -1
        try:
            result = self._device.get_latency()
        except Exception:
            return -1
        return result if result is not None else -1

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='s')
    def GetDeviceName(self) -> str:
        """Get the device name (e.g. 'EPOS GSA 70'), or '' if unknown."""
        if not self._device_name and self._device is not None:
            self._refresh_device_info()
        return self._device_name

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='s')
    def GetSerial(self) -> str:
        """Get the device serial number, or '' if unknown."""
        if not self._serial and self._device is not None:
            self._refresh_device_info()
        return self._serial

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='s')
    def GetFirmwareVersion(self) -> str:
        """Get the device firmware version (e.g. '3.14.2'), or '' if unknown."""
        if not self._firmware and self._device is not None:
            self._refresh_device_info()
        return self._firmware

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='i')
    def GetSubDevices(self) -> int:
        """Get the number of linked sub-devices (0 = headset not linked), or -1."""
        result = self._get_subdevices_internal()
        return result if result is not None else -1

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='b')
    def RefreshDeviceInfo(self) -> bool:
        """Re-read the cached device identity. Returns True on success."""
        return self._refresh_device_info()

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='b')
    def GetLinkState(self) -> bool:
        """Return True if device is connected and responsive."""
        return self._device is not None and self._device.is_connected

    @dbus.service.method(BUS_NAME, in_signature='', out_signature='b')
    def IsAvailable(self) -> bool:
        """Return True if a GSP 670 device is available."""
        return self._device is not None and self._device.is_connected

    # ─── D-Bus Signals ───────────────────────────────────────────────

    @dbus.service.signal(BUS_NAME, signature='ib')
    def BatteryChanged(self, level: int, charging: bool):
        """Emitted when battery level or charging state changes."""
        pass

    @dbus.service.signal(BUS_NAME, signature='i')
    def SidetoneChanged(self, level: int):
        """Emitted when sidetone level changes."""
        pass

    @dbus.service.signal(BUS_NAME, signature='i')
    def NoiseReductionChanged(self, level: int):
        """Emitted when noise-reduction level changes."""
        pass

    @dbus.service.signal(BUS_NAME, signature='i')
    def AutoPowerOffChanged(self, level: int):
        """Emitted when the auto-power-off value changes."""
        pass

    @dbus.service.signal(BUS_NAME, signature='i')
    def SubDevicesChanged(self, count: int):
        """Emitted when the number of linked sub-devices changes."""
        pass

    @dbus.service.signal(BUS_NAME)
    def DeviceInfoChanged(self):
        """Emitted when the cached device identity (name/serial/firmware) changes."""
        pass

    @dbus.service.signal(BUS_NAME, signature='b')
    def LinkChanged(self, connected: bool):
        """Emitted when device connection state changes."""
        pass

    # ─── Lifecycle ────────────────────────────────────────────────────

    def start(self):
        """Start the service and polling thread."""
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_state, daemon=True)
        self._poll_thread.start()
        logger.info("D-Bus service started")

    def stop(self):
        """Stop the service and polling thread."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=3)
        self._close_device()
        logger.info("D-Bus service stopped")


def _request_bus_name(bus: dbus.Bus) -> bool:
    """Request the well-known bus name. Returns True if we own it."""
    # These constants normally live in dbus.bus. Some dbus-python builds also
    # re-export them as dbus.nameflag / dbus.request_name_reply, but not all
    # (e.g. the 1.5.0 build here), so resolve them from dbus.bus.
    name_flag = getattr(
        getattr(dbus, "nameflag", None),
        "do_not_queue",
        dbus.bus.NAME_FLAG_DO_NOT_QUEUE,
    )
    primary_owner = getattr(
        getattr(dbus, "request_name_reply", None),
        "primary_owner",
        dbus.bus.REQUEST_NAME_REPLY_PRIMARY_mrcanofcatfood,
    )

    try:
        result = bus.request_name(BUS_NAME, name_flag)
        return result == primary_owner
    except Exception as e:
        logger.error(f"Failed to request bus name: {e}")
        return False


def _run_service(bus_type: str = 'system', device_mode: str = 'dongle'):
    """Run the D-Bus service on the specified bus."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    if bus_type == 'session':
        bus = dbus.SessionBus()
    else:
        bus = dbus.SystemBus()

    if not _request_bus_name(bus):
        logger.error(f"Bus name {BUS_NAME} is already taken")
        sys.exit(1)

    service = Gsp670DBusService(bus, device_mode=device_mode)
    service.start()

    logger.info(f"GSP 670 D-Bus service running on {bus_type} bus")
    logger.info(f"Object: {OBJECT_PATH}")
    logger.info(f"Bus name: {BUS_NAME}")
    logger.info("Methods: GetBattery, GetSidetone, SetSidetone, GetNoiseReduction, "
                "SetNoiseReduction, GetAutoPowerOff, SetAutoPowerOff, GetLatency, "
                "GetDeviceName, GetSerial, GetFirmwareVersion, GetSubDevices, "
                "RefreshDeviceInfo, GetLinkState, IsAvailable")
    logger.info("Signals: BatteryChanged, SidetoneChanged, NoiseReductionChanged, "
                "AutoPowerOffChanged, SubDevicesChanged, DeviceInfoChanged, LinkChanged")

    try:
        mainloop = GLib.MainLoop()
        mainloop.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        service.stop()


def main():
    parser = argparse.ArgumentParser(description='GSP 670 D-Bus Service')
    parser.add_argument('--bus', choices=['system', 'session'], default='system',
                        help='D-Bus bus to use (default: system)')
    parser.add_argument('--device', choices=['dongle', 'headset'], default='dongle',
                        help='Device mode (default: dongle)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(name)s: %(levelname)s %(message)s'
    )

    _run_service(bus_type=args.bus, device_mode=args.device)


if __name__ == '__main__':
    main()
