#!/usr/bin/env bash
# Setup virtual 7.1 surround for the GSP 670 / GSA 70.
#
# 1. Downloads the HeSuVi HRIR installer (SourceForge), extracts the requested
#    14-channel preset WAV, verifies its SHA-256, and installs it as
#    ~/.local/share/pipewire/hrir_hesuvi/hrir.wav (the path PipeWire's
#    filter-chain convolver resolves relative IR names against).
# 2. Loads the surround sink live via pactl (optional, default on).
# 3. Optionally installs a PipeWire conf.d drop-in so the sink survives
#    PipeWire restarts (--persist).
#
# Usage: setup-virtual-surround.sh [--preset gsx|atmos] [--persist] [--no-load]
#
# IR provenance: HeSuVi 2.0.0.1 installer, https://sourceforge.net/projects/hesuvi/
# The gsx preset is the HRTF captured from the Sennheiser GSX virtualization —
# a natural fit for the Sennheiser/EPOS GSP 670. HeSuVi is open-source
# software; the IR captures ship with it under its distribution terms.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$REPO_ROOT/contrib/pipewire/gsp670-virtual-surround-7.1.conf"

# Where the IR is installed. The PipeWire convolver resolves a relative IR
# name against the pipewire process CWD on some versions, so the drop-in we
# write embeds the absolute path instead.
IR_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/pipewire/hrir_hesuvi"

HESUVI_URL="https://sourceforge.net/projects/hesuvi/files/HeSuVi_2.0.0.1.exe/download"
HESUVI_SHA256="a31774714d8f7a87ae4fd5bdbaa4bfa294a808296bdcc9e9935da4b427a601ba"

declare -A PRESET_SHA=(
    [gsx]="7285b3914f3e6e946b33660e782e5edf6a760d45fc89e03c6f72789b109e3ba4"
    [atmos]="44fc360fcd97157b3fd2a2d2701cf056f59db582ab2647cf365d97e31a9f4fcb"
)

PRESET="gsx"
PERSIST=0
LOAD=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --preset)  PRESET="$2"; shift 2 ;;
        --persist) PERSIST=1; shift ;;
        --no-load) LOAD=0; shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

[[ -n "${PRESET_SHA[$PRESET]:-}" ]] || { echo "Unknown preset '$PRESET' (known: ${!PRESET_SHA[*]})" >&2; exit 2; }

for dep in curl 7z sha256sum; do
    command -v "$dep" >/dev/null || { echo "Missing dependency: $dep" >&2; exit 1; }
done

IR_WAV="$IR_DIR/hrir.wav"
TMP="$(mktemp -d /tmp/opencode/hesuvi.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# --- 1. Fetch and verify the HeSuVi preset ---------------------------------
if [[ -f "$IR_WAV" ]] && [[ "$(sha256sum "$IR_WAV" | cut -d' ' -f1)" == "${PRESET_SHA[$PRESET]}" ]]; then
    echo "[ok] IR already installed at $IR_WAV"
else
    echo "[..] downloading HeSuVi 2.0.0.1 installer (~27 MB)..."
    curl -sSL --fail -o "$TMP/hesuvi.exe" "$HESUVI_URL"
    echo -n "$HESUVI_SHA256  $TMP/hesuvi.exe" | sha256sum -c --quiet \
        || { echo "Installer checksum mismatch; aborting." >&2; exit 1; }
    echo "[ok] installer checksum verified"
    7z e -y -o"$TMP/x" "$TMP/hesuvi.exe" "HeSuVi/hrir/$PRESET.wav" >/dev/null
    echo -n "${PRESET_SHA[$PRESET]}  $TMP/x/$PRESET.wav" | sha256sum -c --quiet \
        || { echo "Extracted $PRESET.wav checksum mismatch; aborting." >&2; exit 1; }
    echo "[ok] $PRESET.wav checksum verified (14-ch 48 kHz HRIR)"
    mkdir -p "$IR_DIR"
    install -m 644 "$TMP/x/$PRESET.wav" "$IR_WAV"
    echo "[ok] installed IR: $IR_WAV"
fi

# --- 2. Load the surround sink ---------------------------------------------
if [[ "$LOAD" -eq 1 ]]; then
    if pactl list short sinks 2>/dev/null | grep -q "GSP670_Surround"; then
        echo "[ok] GSP670_Surround sink already loaded"
    elif [[ ! -f "$CONF" ]]; then
        echo "[!] filter-chain config not found at $CONF; skipping live load" >&2
    else
        # relative IR paths resolve against the pipewire CWD — embed absolute
        sed "s|filename = \"hrir_hesuvi/hrir.wav\"|filename = \"$IR_WAV\"|g" \
            "$CONF" > "$TMP/conf-patched.conf"
        pactl load-module module-filter-chain file="$TMP/conf-patched.conf" >/dev/null \
            && echo "[ok] loaded GSP670_Surround sink (live, until PipeWire restarts)" \
            || echo "[!] pactl could not load module-filter-chain (not supported by " \
                    "this PipeWire build); use --persist + service restart instead" >&2
    fi
fi

# --- 3. Persistence ---------------------------------------------------------
if [[ "$PERSIST" -eq 1 ]]; then
    CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/pipewire/pipewire.conf.d"
    mkdir -p "$CONF_DIR"
    # The convolver resolves relative IR paths against the pipewire process
    # CWD (not the data dir) on some versions — write the absolute IR path.
    sed "s|filename = \"hrir_hesuvi/hrir.wav\"|filename = \"$IR_WAV\"|g" \
        "$CONF" > "$CONF_DIR/20-gsp670-surround.conf"
    echo "[ok] installed drop-in: $CONF_DIR/20-gsp670-surround.conf"
    echo "     (IR path embedded as: $IR_WAV)"
    echo "     restart pipewire to apply:  systemctl --user restart pipewire wireplumber"
fi

# --- Next steps --------------------------------------------------------------
cat <<'EOF'

Done. Try it:

  # make it the default output (or route a single app in the mixer instead)
  wpctl set-default "$(wpctl status | grep -oP '^\s+\K[0-9]+(?=\. GSP670_Surround)' | head -1)"

  # objective per-channel verification (all 8 tones must reach the headset)
  python3 scripts/surround_verify.py --test

  # subjective check: spoken channel names from distinct directions
  python3 scripts/surround_verify.py --listen

In games, set the audio device to "GSP 670 Virtual Surround 7.1" and select
7.1 speaker configuration in the game's audio settings.
EOF
