#!/usr/bin/env bash
# gsp670-distros.sh — distro detection and package-name mapping.
#
# Sourced by scripts/install.sh. Defines:
#
#   gsp670_detect_distro   -> sets DISTRO_ID, DISTRO_FAMILY, PKG_MANAGER
#   gsp670_pkg_install <pkg...>  -> installs distro packages
#   gsp670_hidapi_package   -> prints the distro package name for hidapi
#
# The only *required* package for the base install is hidapi (needed for the
# optional device-control features). The audio path of this project needs no
# packages at all beyond what a normal desktop already has.

set -u

# --- Package-manager mapping -------------------------------------------------
# Order matters: the first match wins.
gsp670_detect_distro() {
    DISTRO_ID="unknown"
    DISTRO_FAMILY="unknown"
    PKG_MANAGER=""

    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_FAMILY="${ID_LIKE:-${ID:-unknown}}"
    fi

    case "$DISTRO_ID" in
        arch|manjaro|endeavouros|garuda|cachyos|artix)
            PKG_MANAGER="pacman" ;;
        debian|ubuntu|linuxmint|pop|elementary|zorin|kali)
            PKG_MANAGER="apt" ;;
        fedora|rhel|centos|rocky|almalinux|nobara)
            PKG_MANAGER="dnf" ;;
        opensuse|opensuse-leap|opensuse-tumbleweed|suse)
            PKG_MANAGER="zypper" ;;
        alpine)
            PKG_MANAGER="apk" ;;
        void)
            PKG_MANAGER="xbps" ;;
        gentoo)
            PKG_MANAGER="emerge" ;;
        *)
            # Fall back to family matching.
            case "$DISTRO_FAMILY" in
                *arch*|*manjaro*)   PKG_MANAGER="pacman" ;;
                *debian*|*ubuntu*)  PKG_MANAGER="apt" ;;
                *fedora*|*rhel*)    PKG_MANAGER="dnf" ;;
                *suse*)             PKG_MANAGER="zypper" ;;
                *alpine*)           PKG_MANAGER="apk" ;;
                *)                  PKG_MANAGER="" ;;
            esac
            ;;
    esac
}

# Print the distro package name that provides the hidapi Python module.
gsp670_hidapi_package() {
    case "$PKG_MANAGER" in
        pacman) echo "python-hidapi" ;;
        apt)    echo "python3-hidapi" ;;
        dnf)    echo "python3-hidapi" ;;
        zypper) echo "python3-hidapi" ;;
        apk)    echo "py3-hidapi" ;;
        xbps)   echo "python3-hidapi" ;;
        emerge) echo "dev-python/hidapi" ;;
        *)      echo "" ;;
    esac
}

# Print the distro package names for the optional D-Bus stack.
gsp670_dbus_packages() {
    case "$PKG_MANAGER" in
        pacman) echo "python-dbus python-gobject" ;;
        apt)    echo "python3-dbus python3-gi" ;;
        dnf)    echo "python3-dbus python3-gobject" ;;
        zypper) echo "python3-dbus python3-gi" ;;
        apk)    echo "py3-dbus py3-gobject" ;;
        xbps)   echo "python3-dbus python3-gobject" ;;
        emerge) echo "dev-python/dbus dev-python/pygobject" ;;
        *)      echo "" ;;
    esac
}

# gsp670_pkg_install <pkg>...
#
# Installs packages with the detected package manager. Returns non-zero if the
# package manager is unknown or the install failed.
gsp670_pkg_install() {
    [ $# -eq 0 ] && return 0

    case "$PKG_MANAGER" in
        pacman)
            pacman -S --needed --noconfirm "$@" ;;
        apt)
            apt-get update -qq
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" ;;
        dnf)
            dnf install -y -q "$@" ;;
        zypper)
            zypper --non-interactive install "$@" ;;
        apk)
            apk add --no-cache "$@" ;;
        xbps)
            xbps-install -Sy "$@" ;;
        emerge)
            emerge "$@" ;;
        *)
            echo "No supported package manager detected (PKG_MANAGER='${PKG_MANAGER}')." >&2
            echo "Install manually: $*" >&2
            return 1 ;;
    esac
}

# gsp670_pkg_installed <pkg> -> 0 if installed, 1 otherwise.
gsp670_pkg_installed() {
    case "$PKG_MANAGER" in
        pacman) pacman -Qi "$1" >/dev/null 2>&1 ;;
        apt)    dpkg -s "$1" >/dev/null 2>&1 ;;
        dnf)    rpm -q "$1" >/dev/null 2>&1 ;;
        zypper) rpm -q "$1" >/dev/null 2>&1 ;;
        apk)    apk info -e "$1" >/dev/null 2>&1 ;;
        xbps)   xbps-query -R "$1" >/dev/null 2>&1 ;;
        emerge) emerge --search --quiet "$1" >/dev/null 2>&1 ;;
        *)      return 1 ;;
    esac
}
