#!/usr/bin/env bash
#
# gsp670 install — set up the EPOS|Sennheiser GSP 670 headset and GSA 70
#                   wireless dongle on Linux.
#
# What this installs
# ------------------
#   * udev rules       -> hidraw access for the device-control features
#   * systemd unit     -> audio guard that recovers the ALSA card
#   * WirePlumber cfg  -> keeps the USB-audio nodes alive (fixes the
#                          Discord "no-audio-input-detected" / EasyEffects
#                          teardown race on this USB Full-Speed device)
#   * Python library   -> optional: sidetone, noise reduction, auto-power-off
#
# What this does NOT install
# --------------------------
#   * The ALSA profile set. The GSP 670's "Game" (stereo) and "Chat" (mono)
#     outputs come from the stock `usb-gaming-headset.conf` profile set, which
#     ships with PulseAudio/ALSA and is used by PipeWire via the ALSA
#     configuration API. Nothing extra is needed for audio to work.
#   * A kernel module. Modern kernels (>= ~5.14.15) handle the device's
#     interface ordering natively.
#
# Usage:
#   sudo ./scripts/install.sh                # system-wide install
#   ./scripts/install.sh --user              # per-user install (no root
#                                            # needed except for udev)
#   ./scripts/install.sh --dry-run           # show what would happen
#   ./scripts/install.sh --no-python         # audio setup only
#   ./scripts/install.sh --uninstall         # remove everything
#
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/distros.sh
. "$REPO_ROOT/scripts/distros.sh"

# --- Options -----------------------------------------------------------------
DRY_RUN=0
USER_SCOPE=0
WITH_PYTHON=1
WITH_DBUS=0
UNINSTALL=0
PREFIX="/usr"
LIBDIR="/usr/lib/gsp670"

usage() {
    sed -n '2,/^set -u/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//; $d'
    exit 0
}

for arg in "$@"; do
    case "$arg" in
        --user)      USER_SCOPE=1 ;;
        --dry-run)   DRY_RUN=1 ;;
        --no-python) WITH_PYTHON=0 ;;
        --with-dbus) WITH_DBUS=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --prefix)    PREFIX="${2:-/usr}"; shift ;;
        -h|--help)   usage ;;
        *) echo "Unknown option: $arg" >&2; usage ;;
    esac
done

if [ "$USER_SCOPE" -eq 1 ]; then
    LIBDIR="$HOME/.local/lib/gsp670"
fi

# --- Output helpers ----------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'
    C_INFO=$'\033[36m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_ERR=""; C_INFO=""; C_DIM=""; C_OFF=""
fi

info() { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
err()  { printf '%serr %s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; }
dim()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }
die()  { err "$*"; exit 1; }

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_OFF" "$*"
        return 0
    fi
    "$@"
}

need_root() {
    if [ "$USER_SCOPE" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
        die "System-wide install needs root. Re-run with sudo, or use --user."
    fi
}

# --- Install / uninstall primitives ------------------------------------------
install_file() {
    # install_file <src> <dest> <mode>
    local src="$1" dest="$2" mode="${3:-0644}"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s[dry-run]%s install %s -> %s (%s)\n' \
            "$C_DIM" "$C_OFF" "$src" "$dest" "$mode"
        return 0
    fi
    mkdir -p "$(dirname "$dest")"
    install -D -m "$mode" "$src" "$dest"
}

remove_file() {
    local dest="$1"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s[dry-run]%s remove %s\n' "$C_DIM" "$C_OFF" "$dest"
        return 0
    fi
    rm -f "$dest"
}

udev_rules_dir() {
    if [ "$USER_SCOPE" -eq 1 ]; then
        echo "$HOME/.config/udev/rules.d"
    else
        echo "/etc/udev/rules.d"
    fi
}

wireplumber_dir() {
    if [ "$USER_SCOPE" -eq 1 ]; then
        echo "$HOME/.config/wireplumber/wireplumber.conf.d"
    else
        echo "/etc/wireplumber/wireplumber.conf.d"
    fi
}

# have_wireplumber -> 0 if WirePlumber appears to be installed.
#
# WirePlumber's config directory lives in different places depending on the
# distribution: /etc/wireplumber on Debian/Fedora, /usr/share/wireplumber on
# Arch, and ~/.config/wireplumber when installed per-user.
have_wireplumber() {
    local d
    for d in /etc/wireplumber /usr/share/wireplumber "$HOME/.config/wireplumber"; do
        [ -d "$d" ] && return 0
    done
    # Fall back to asking the session manager itself.
    command -v wpctl >/dev/null 2>&1 && return 0
    return 1
}

pipewire_dir() {
    if [ "$USER_SCOPE" -eq 1 ]; then
        echo "$HOME/.config/pipewire/pipewire.conf.d"
    else
        echo "/etc/pipewire/pipewire.conf.d"
    fi
}

# --- Uninstall ---------------------------------------------------------------
do_uninstall() {
    info "Uninstalling gsp670-linux"

    remove_file "$(udev_rules_dir)/99-gsp670.rules"
    remove_file "$(udev_rules_dir)/99-gsp670-audio.rules"
    remove_file "$(wireplumber_dir)/50-gsp670.conf"
    remove_file "$PREFIX/lib/systemd/system/gsp670-audio-guard.service"
    remove_file "$LIBDIR/gsp670-audio-guard.sh"

    if [ "$USER_SCOPE" -eq 0 ]; then
        if command -v systemctl >/dev/null 2>&1; then
            info "Disabling and stopping gsp670-audio-guard.service"
            if [ "$DRY_RUN" -eq 1 ]; then
                echo "[dry-run] systemctl disable --now gsp670-audio-guard.service"
            else
                systemctl disable --now gsp670-audio-guard.service 2>/dev/null || true
            fi
        fi
        # Clean up a unit left by an older install location.
        remove_file /etc/systemd/system/gsp670-audio-guard.service
        if command -v udevadm >/dev/null 2>&1; then
            run udevadm control --reload-rules
        fi
    else
        if command -v systemctl >/dev/null 2>&1; then
            info "Reloading the user WirePlumber instance"
            run systemctl --user restart wireplumber 2>/dev/null || true
        fi
    fi

    ok "Removed. The Python package, if installed, was left in place"
    dim "  (remove it with: pip uninstall gsp670)"
}

# --- Main install ------------------------------------------------------------
do_install() {
    need_root
    gsp670_detect_distro

    info "Detected: $DISTRO_ID (family: $DISTRO_FAMILY, package manager: ${PKG_MANAGER:-none})"

    # --- 1. udev rules -------------------------------------------------------
    info "Installing udev rules"
    install_file "$REPO_ROOT/udev/99-gsp670.rules" \
        "$(udev_rules_dir)/99-gsp670.rules" 0644

    if [ "$USER_SCOPE" -eq 0 ]; then
        # The audio-guard rule asks systemd to start the guard unit, which only
        # exists as a system unit, so only install it system-wide.
        install_file "$REPO_ROOT/udev/99-gsp670-audio.rules" \
            "$(udev_rules_dir)/99-gsp670-audio.rules" 0644
        if command -v udevadm >/dev/null 2>&1; then
            run udevadm control --reload-rules
            run udevadm trigger --subsystem-match=usb --action=add
        else
            warn "udevadm not found; reload the udev rules manually"
        fi
    else
        warn "Per-user udev rules are not honoured by systemd-udevd on most distros."
        warn "The audio guard therefore needs a system-wide install to work."
    fi

    # --- 2. audio guard (systemd) -------------------------------------------
    if [ "$USER_SCOPE" -eq 0 ]; then
        info "Installing the audio-guard service"
        install_file "$REPO_ROOT/scripts/gsp670-audio-guard.sh" \
            "$LIBDIR/gsp670-audio-guard.sh" 0755
        install_file "$REPO_ROOT/systemd/gsp670-audio-guard.service" \
            "$PREFIX/lib/systemd/system/gsp670-audio-guard.service" 0644

        # Remove a unit left behind by an older install location.
        if [ "$PREFIX" = "/usr" ] && [ -f /etc/systemd/system/gsp670-audio-guard.service ]; then
            dim "Removing the stale unit in /etc/systemd/system"
            rm -f /etc/systemd/system/gsp670-audio-guard.service
        fi

        if command -v systemctl >/dev/null 2>&1; then
            run systemctl daemon-reload
            run systemctl enable --now gsp670-audio-guard.service
            ok "gsp670-audio-guard.service enabled"
        else
            warn "systemctl not found; enable gsp670-audio-guard.service manually"
        fi
    else
        info "Skipping the audio-guard service (needs a system-wide install)"
    fi

    # --- 3. WirePlumber configuration ---------------------------------------
    # This is the important one: without it WirePlumber suspends the idle
    # USB-audio node and the resulting resume race breaks Discord and
    # EasyEffects.
    if have_wireplumber; then
        info "Installing the WirePlumber configuration"
        install_file "$REPO_ROOT/contrib/wireplumber/50-gsp670.conf" \
            "$(wireplumber_dir)/50-gsp670.conf" 0644

        # Restart WirePlumber so it picks the drop-in up. This has to happen
        # in the user's session: root has no user D-Bus session.
        if command -v systemctl >/dev/null 2>&1; then
            local wp_user=""
            if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
                wp_user="$SUDO_USER"
            fi
            if [ -n "$wp_user" ]; then
                if run sudo -u "$wp_user" -H \
                        XDG_RUNTIME_DIR="/run/user/$(id -u "$wp_user")" \
                        systemctl --user restart wireplumber 2>/dev/null; then
                    ok "restarted WirePlumber for $wp_user"
                else
                    warn "Could not restart WirePlumber; run this as $wp_user:"
                    warn "  systemctl --user restart wireplumber"
                fi
            elif [ "$USER_SCOPE" -eq 1 ]; then
                run systemctl --user restart wireplumber 2>/dev/null \
                    || warn "Could not restart the user WirePlumber instance"
            else
                warn "Restart WirePlumber to apply the configuration:"
                warn "  systemctl --user restart wireplumber"
            fi
        fi
    else
        warn "WirePlumber not detected; skipping 50-gsp670.conf"
        warn "  (install it to $(wireplumber_dir)/50-gsp670.conf if you use WirePlumber)"
    fi

    # --- 4. optional: virtual surround --------------------------------------
    if [ -f "$REPO_ROOT/contrib/pipewire/gsp670-virtual-surround-7.1.conf" ]; then
        info "Installing the optional virtual-surround configuration"
        install_file "$REPO_ROOT/contrib/pipewire/gsp670-virtual-surround-7.1.conf" \
            "$(pipewire_dir)/50-gsp670-surround.conf" 0644
        dim "  The HeSuVi HRIR file is not bundled. To enable 7.1 virtual surround, run:"
        dim "    $REPO_ROOT/scripts/setup-virtual-surround.sh"
    fi

    # --- 5. optional: Python library ----------------------------------------
    if [ "$WITH_PYTHON" -eq 1 ]; then
        info "Installing the Python library and CLI"
        install_hidapi
        install_python
    else
        dim "Skipping the Python library (--no-python)"
        dim "  Audio works without it; it only adds device controls."
    fi

    if [ "$WITH_DBUS" -eq 1 ]; then
        install_dbus_stack
    fi

    print_summary
}

install_hidapi() {
    local pkg
    pkg="$(gsp670_hidapi_package)"
    if [ -z "$pkg" ]; then
        warn "Unknown package manager; skipping hidapi install"
        dim "  Install it manually, or use: pip install hidapi"
        return 0
    fi
    if gsp670_pkg_installed "$pkg"; then
        ok "$pkg already installed"
        return 0
    fi
    info "Installing $pkg (needed for the device-control features)"
    if run gsp670_pkg_install "$pkg"; then
        ok "installed $pkg"
    else
        warn "Could not install $pkg"
        dim "  Install it manually, or use: pip install hidapi"
    fi
}

install_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        warn "python3 not found; skipping the Python library"
        return 0
    fi

    # When run via sudo, the Python package must be installed as the
    # *invoking* user, not as root — otherwise it lands in root's user site
    # and the user cannot run the `gsp670` command.
    local run_as_user=""
    local run_as_home=""
    if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        run_as_user="$SUDO_USER"
        run_as_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    fi

    # Find a usable pip. Prefer an explicitly requested interpreter's pip so
    # that `PIP=... make install` or a virtualenv's pip is used when active.
    local pip_cmd=""
    local candidate
    for candidate in "${PIP:-}" "pip3" "pip"; do
        [ -n "$candidate" ] || continue
        if [ "$candidate" = "pip3" ] || [ "$candidate" = "pip" ]; then
            command -v "$candidate" >/dev/null 2>&1 || continue
            pip_cmd="$candidate"
            break
        fi
        # An explicit PIP=... value: use it as-is if it looks runnable.
        if $candidate --version >/dev/null 2>&1; then
            pip_cmd="$candidate"
            break
        fi
    done
    if [ -z "$pip_cmd" ] && python3 -m pip --version >/dev/null 2>&1; then
        pip_cmd="python3 -m pip"
    fi

    if [ -z "$pip_cmd" ]; then
        # No pip at all. Offer to install it — it is a standard package on
        # every supported distribution.
        local pip_pkg
        case "$PKG_MANAGER" in
            pacman) pip_pkg="python-pip" ;;
            apt)    pip_pkg="python3-pip" ;;
            dnf)    pip_pkg="python3-pip" ;;
            zypper) pip_pkg="python3-pip" ;;
            apk)    pip_pkg="py3-pip" ;;
            xbps)   pip_pkg="python3-pip" ;;
            emerge) pip_pkg="dev-python/pip" ;;
            *)      pip_pkg="" ;;
        esac
        if [ -n "$pip_pkg" ] && [ "$DRY_RUN" -eq 0 ]; then
            info "pip not found; installing $pip_pkg"
            if gsp670_pkg_install "$pip_pkg" 2>/dev/null; then
                ok "installed $pip_pkg"
                pip_cmd="python3 -m pip"
            fi
        fi
    fi

    if [ -z "$pip_cmd" ]; then
        warn "pip not found; skipping the Python library"
        dim "  Install manually: python3 -m pip install --user $REPO_ROOT"
        return 0
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s[dry-run]%s %s install %s\n' "$C_DIM" "$C_OFF" \
            "$pip_cmd" "$REPO_ROOT"
        return 0
    fi

    # Run the pip install as the target user when we are root.
    local as_user=()
    if [ -n "$run_as_user" ]; then
        as_user=(sudo -u "$run_as_user" -H)
    fi

    # $pip_cmd may be a multi-word command ("python3 -m pip"), so split it
    # into an array and expand it unquoted.
    local pip=()
    read -r -a pip <<< "$pip_cmd"

    # Modern distributions mark the system Python as "externally managed"
    # (PEP 668), which makes a plain `pip install` fail. Try the usual
    # escape hatches in order of preference.
    if "${as_user[@]}" "${pip[@]}" install --user "$REPO_ROOT" 2>/dev/null; then
        ok "installed the gsp670 package (user site)"
        note_user_path "$run_as_home"
        return 0
    fi
    if "${as_user[@]}" "${pip[@]}" install --user --break-system-packages \
        "$REPO_ROOT" 2>/dev/null; then
        ok "installed the gsp670 package (user site, PEP 668 override)"
        note_user_path "$run_as_home"
        return 0
    fi
    if "${as_user[@]}" "${pip[@]}" install "$REPO_ROOT" 2>/dev/null; then
        ok "installed the gsp670 package (system)"
        return 0
    fi

    # Last resort: a self-contained virtualenv under ~/.local, so the install
    # works even where the system Python is locked down.
    if command -v python3 >/dev/null 2>&1 && python3 -m venv --help >/dev/null 2>&1; then
        local venv_dir
        if [ -n "$run_as_home" ]; then
            venv_dir="$run_as_home/.local/share/gsp670/venv"
        else
            venv_dir="$HOME/.local/share/gsp670/venv"
        fi
        info "falling back to a virtualenv at $venv_dir"
        if python3 -m venv "$venv_dir" 2>/dev/null \
           && "$venv_dir/bin/pip" install -q "$REPO_ROOT" 2>/dev/null; then
            ok "installed the gsp670 package into $venv_dir"
            dim "  Add it to your PATH:  export PATH=\"$venv_dir/bin:\$PATH\""
            return 0
        fi
    fi

    warn "pip install failed; install it manually with one of:"
    dim "  $pip_cmd install --user --break-system-packages $REPO_ROOT"
    dim "  pipx install $REPO_ROOT"
}

# Tell the user where the console script landed, if it is not on their PATH.
note_user_path() {
    local home="${1:-$HOME}"
    [ -n "$home" ] || return 0
    local bindir="$home/.local/bin"
    if [ -x "$bindir/gsp670" ] && ! echo ":$PATH:" | grep -q ":$bindir:"; then
        dim "  The 'gsp670' command is at $bindir — add it to your PATH:"
        dim "    export PATH=\"$bindir:\$PATH\""
    fi
}

install_dbus_stack() {
    local pkgs
    pkgs="$(gsp670_dbus_packages)"
    if [ -z "$pkgs" ]; then
        warn "Unknown package manager; skipping the D-Bus stack"
        return 0
    fi
    info "Installing the optional D-Bus stack ($pkgs)"
    # shellcheck disable=SC2086
    run gsp670_pkg_install $pkgs || warn "Could not install the D-Bus stack"
}

print_summary() {
    echo
    ok "Installation finished."
    echo
    info "Next steps:"
    echo "  1. Unplug and replug the dongle (or the headset's Micro-USB cable)."
    echo "  2. Verify audio:  wpctl status | grep -i 'GSA 70'"
    echo "     You should see a stereo 'Game' sink and a mono 'Chat' sink."
    echo "  3. Run the doctor for a full check:"
    echo "       $REPO_ROOT/scripts/gsp670-audio-doctor.sh"
    if [ "$WITH_PYTHON" -eq 1 ]; then
        echo "  4. Device controls:  gsp670 info    (sidetone, battery, identity)"
    fi
    echo
    warn "Known limitation: the wireless dongle has a firmware bug that adds"
    warn "about 1.4 s of audio latency. Wired Micro-USB mode has ~44 ms latency."
    echo
}

# --- Entry point -------------------------------------------------------------
if [ "$UNINSTALL" -eq 1 ]; then
    do_uninstall
    exit 0
fi

do_install
