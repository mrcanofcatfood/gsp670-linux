#!/usr/bin/env python3
"""
Optional-dependency handling.

The base install needs only ``hidapi``. ``dbus-python`` and ``PyGObject`` are
needed solely by the optional D-Bus daemon (:mod:`gsp670.dbus_service`).

Importing :mod:`gsp670` must therefore succeed on a machine that has neither
the D-Bus stack nor, ideally, even ``hidapi`` — the audio path of this project
does not need Python at all. Modules that genuinely require a dependency call
the ``require_*`` helpers below, which raise a clear, actionable error instead
of an opaque ``ImportError``.
"""

from __future__ import annotations

import importlib
from typing import Any, Optional

__all__ = [
    "MissingDependency",
    "require_hid",
    "require_dbus",
    "have_dbus",
]


class MissingDependency(ImportError):
    """Raised when an optional dependency is required but not installed."""


def _install_hint(module: str, extra: Optional[str] = None) -> str:
    """Build an actionable error message for a missing dependency."""
    if extra:
        return (
            f"the {module!r} module is required for this feature but is not "
            f"installed.\n"
            f"Install it with:\n"
            f"    pip install 'gsp670[{extra}]'\n"
            f"or install the distribution package, e.g.:\n"
            f"    Debian/Ubuntu: sudo apt install python3-dbus python3-gi\n"
            f"    Fedora:         sudo dnf install python3-dbus python3-gobject\n"
            f"    Arch:           sudo pacman -S python-dbus python-gobject"
        )
    return (
        f"the {module!r} module is required but is not installed.\n"
        f"Install it with:\n"
        f"    pip install hidapi\n"
        f"or use your distribution's package manager, e.g.:\n"
        f"    Debian/Ubuntu: sudo apt install python3-hidapi\n"
        f"    Fedora:         sudo dnf install python3-hidapi\n"
        f"    Arch:           sudo pacman -S python-hidapi"
    )


def require_hid() -> Any:
    """Return the ``hid`` module, or raise :class:`MissingDependency`."""
    try:
        return importlib.import_module("hid")
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise MissingDependency(_install_hint("hidapi")) from exc


def require_dbus() -> tuple[Any, Any]:
    """Return ``(dbus, GLib)``, or raise :class:`MissingDependency`."""
    try:
        dbus = importlib.import_module("dbus")
        dbus_bus = importlib.import_module("dbus.bus")
        dbus_service = importlib.import_module("dbus.service")
        dbus_mainloop = importlib.import_module("dbus.mainloop")
        dbus_mainloop_glib = importlib.import_module("dbus.mainloop.glib")
        glib = importlib.import_module("gi.repository", "GLib")
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise MissingDependency(_install_hint("dbus-python", extra="dbus")) from exc

    # The dbus submodules are normally wired up by ``dbus/__init__.py`` as a
    # side effect of importing them. Importing them directly (as above) does
    # not always register them on the parent packages, so do it explicitly:
    #   dbus.bus / dbus.service
    #   dbus.mainloop.glib
    for name, mod in (
        ("bus", dbus_bus),
        ("service", dbus_service),
    ):
        if getattr(dbus, name, None) is not mod:
            setattr(dbus, name, mod)

    if getattr(dbus_mainloop, "glib", None) is not dbus_mainloop_glib:
        setattr(dbus_mainloop, "glib", dbus_mainloop_glib)
    if getattr(dbus, "mainloop", None) is not dbus_mainloop:
        setattr(dbus, "mainloop", dbus_mainloop)

    return dbus, glib


def have_dbus() -> bool:
    """Return ``True`` when the optional D-Bus stack is importable."""
    try:
        require_dbus()
    except MissingDependency:
        return False
    return True
