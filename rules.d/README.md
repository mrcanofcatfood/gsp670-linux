# `rules.d/` vs `udev/`

This project has two rule directories, and they serve different audiences.

| Directory | Purpose | Installed by |
|---|---|---|
| `udev/` | The **runtime** udev rules that make the device work. | `scripts/install.sh`, `make install-udev`, or a distro package |
| `rules.d/` | The **packaging** rules tree: the files a distribution package needs to ship, install and own the files in `udev/`, `systemd/`, `contrib/` and `scripts/`. | Not installed directly — consumed by the packager |

In short: `udev/` is *what* the rules are, `rules.d/` is *how a distro packages
them*.

## Contents

```
rules.d/
├── README.md          this file
├── debian/            Debian/Ubuntu packaging
│   ├── control
│   ├── changelog
│   ├── copyright
│   ├── install
│   ├── rules
│   └── gsp670.install  dh_install file lists
├── arch/
│   └── PKGBUILD       Arch Linux (also usable as a template for other
│                      Arch-family distributions: CachyOS, Manjaro, Endeavour)
└── rpm/
    └── gsp670.spec    Fedora/RHEL/openSUSE
```

## Notes for packagers

- **udev rules belong in `/usr/lib/udev/rules.d/`** on modern distributions
  (the vendor location), not `/etc/udev/rules.d/`. The upstream `Makefile`
  defaults to `/usr/lib`; `scripts/install.sh` uses `/etc` because it installs
  into a live system rather than a package root.
- **Do not enable `gsp670-audio-guard.service` by default in the package.**
  It is enabled by `scripts/install.sh` because that is an explicit,
  interactive action. A package should ship the unit and let the user enable
  it, or use a preset.
- **The `hidapi` dependency is only needed for the device-control features**
  (`gsp670` CLI). The audio path — the stereo "Game" sink and the mono "Chat"
  sink — needs no package from this project at all; it comes from the stock
  `usb-gaming-headset.conf` ALSA profile set.
- **The Python package and the D-Bus daemon are separable.** `dbus-python` and
  `PyGObject` should be a weak/suggests dependency, since the base install
  must work without them.
- **The HeSuVi HRIR file is not shipped.** It is downloaded on demand by
  `scripts/setup-virtual-surround.sh` and is licensed separately by HeSuVi.
