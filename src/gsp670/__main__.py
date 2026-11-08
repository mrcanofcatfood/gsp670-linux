#!/usr/bin/env python3
"""
Allow running gsp670 modules as: python -m gsp670.<module>

Usage:
    python -m gsp670.daemon [args]
    python -m gsp670.dbus_service [args]

Note: ``python -m gsp670`` runs the D-Bus daemon, which needs the optional
``dbus`` extra (``pip install 'gsp670[dbus]'``). For device information use the
``gsp670`` console script instead, e.g. ``gsp670 info``.
"""

import sys


def main() -> int:
    """Delegate to the daemon, falling back to the dbus_service CLI."""
    try:
        from gsp670.daemon import main as daemon_main
    except Exception as exc:
        # MissingDependency (and anything else) is reported here rather than
        # as a traceback, because the actionable install hint lives in the
        # exception message.
        print(f"Daemon unavailable: {exc}", file=sys.stderr)
        try:
            from gsp670.dbus_service import main as dbus_main
        except Exception as exc2:
            print(f"D-Bus service unavailable: {exc2}", file=sys.stderr)
            return 1
        dbus_main()
        return 0

    daemon_main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
