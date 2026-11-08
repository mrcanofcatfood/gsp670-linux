#!/bin/bash
# gsp670-audio-doctor.sh -- read-only diagnostic for GSP 670 / GSA 70 audio on
# PipeWire + WirePlumber.
#
# It answers the questions that come up when the headset "breaks" in an app
# (typically Discord: "no audio input detected", or one app's audio stopping
# another's):
#
#   1. Is the device present and did ALSA create its card?
#   2. What are the real PipeWire node names (so WirePlumber rules match)?
#   3. Are the GSA 70 nodes stuck suspended?
#   4. Is a host DSP stack (EasyEffects / filter-chain) sitting between the app
#      and the device, and are app streams attached to it instead of hardware?
#   5. Are the default sink/source pointing at nodes that still exist?
#   6. What have WirePlumber / EasyEffects / Discord said recently?
#
# It makes no changes. Run it from the repo root or anywhere.
set -u

CARD_RE='EPOS GSA 70|\[E70|GSP ?670'
tag() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

tag "USB device"
if have lsusb; then
    lsusb | grep -iE '1395' || echo "  no 1395:* device found (dongle 1395:0300, wired headset 1395:008a)"
fi

tag "ALSA card"
if grep -qiE "$CARD_RE" /proc/asound/cards 2>/dev/null; then
    grep -iE -B1 "$CARD_RE" /proc/asound/cards
else
    echo "  no GSA 70 / GSP 670 ALSA card."
    echo "  If the dongle is plugged in but the card is missing, run:"
    echo "    scripts/gsp670-audio-guard.sh   (re-probes snd-usb-audio)"
fi

tag "PipeWire node names (use these in WirePlumber rules)"
if have pw-cli; then
    pw-cli list-objects Node 2>/dev/null \
        | grep -oE 'node\.name = "[^"]*"' \
        | grep -iE 'GSA_70|GSP_?670|easyeffects|GSP670_Surround' \
        | sort -u || echo "  (none found)"
fi

tag "Sink / source state"
if have pw-dump; then
    pw-dump 2>/dev/null | python3 -c '
import json, sys, re
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
found = False
for o in data:
    if o.get("type") != "PipeWire:Interface:Node":
        continue
    info = o.get("info") or {}
    name = (info.get("props") or {}).get("node.name", "")
    if re.search(r"alsa_(output|input).*(GSA_70|GSP_?670)", name):
        found = True
        print("  %-62s %s" % (name, info.get("state", "?")))
if not found:
    print("  (no GSA 70 / GSP 670 nodes found)")
'
    echo "  ('suspended' on an idle node is normal, but should resume cleanly."
    echo "   persisting 'suspended' while audio plays => see contrib/wireplumber/.)"
else
    echo "  pw-dump not available (install pipewire-utils)"
fi

tag "Host DSP stack (EasyEffects / filter-chain)"
if have pactl; then
    pactl list short sinks 2>/dev/null | grep -iE 'easyeffects|GSP670_Surround' || echo "  no virtual sinks"
    pactl list short sources 2>/dev/null | grep -iE 'easyeffects|GSP670_Surround' || true
    echo "  app streams currently attached to a virtual node:"
    pactl list sink-inputs 2>/dev/null | awk '
        /Sink Input/ { si=$0 }
        /application.name/ { app=$0 }
        /media.name/ { med=$0 }
        /Sink:/ { sink=$0; print "    " si " -> " sink "  " app "  " med }' \
        | grep -iE 'easyeffects|GSP670_Surround' || echo "    (none)"
    echo "  NOTE: voice chat (Discord) should sit on the hardware nodes, not on"
    echo "        easyeffects_sink/easyeffects_source or the surround sink."
fi

tag "Default sink / source (stale defaults break apps silently)"
if have pactl; then
    ds=$(pactl get-default-sink 2>/dev/null); dsrc=$(pactl get-default-source 2>/dev/null)
    echo "  default sink   : ${ds:-?}"
    echo "  default source : ${dsrc:-?}"
    if have pactl && [ -n "${dsrc:-}" ] && ! pactl list short sources 2>/dev/null | grep -qF "$dsrc"; then
        echo "  !! default source does not exist as a node (stale)."
    fi
    if [ -n "${ds:-}" ] && ! pactl list short sinks 2>/dev/null | grep -qF "$ds"; then
        echo "  !! default sink does not exist as a node (stale)."
    fi
fi
if have pw-metadata; then
    pw-metadata -n default 2>/dev/null | grep -E 'default\.(configured\.)?audio\.(sink|source)' | sed 's/^/  /'
fi

tag "WirePlumber drop-in installed?"
for f in "$HOME/.config/wireplumber/wireplumber.conf.d"/*.conf; do
    [ -e "$f" ] && echo "  found: $f"
done
if ! ls "$HOME/.config/wireplumber/wireplumber.conf.d"/*.conf >/dev/null 2>&1; then
    echo "  none installed. To disable idle suspend for the headset:"
    echo "    mkdir -p ~/.config/wireplumber/wireplumber.conf.d"
    echo "    cp contrib/wireplumber/50-gsp670.conf ~/.config/wireplumber/wireplumber.conf.d/"
    echo "    systemctl --user restart wireplumber"
fi

tag "Idle-suspend override active?"
# The 50-gsp670.conf drop-in sets session.suspend-timeout-seconds = 0 for the
# GSA 70 nodes. Without it WirePlumber suspends the idle node and the resume
# races any host DSP stage, which is what breaks Discord and EasyEffects.
if have pw-dump; then
    pw-dump 2>/dev/null | python3 -c '
import json, sys, re
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
found = False
for o in data:
    if o.get("type") != "PipeWire:Interface:Node":
        continue
    props = (o.get("info") or {}).get("props") or {}
    name = props.get("node.name", "")
    if not re.search(r"alsa_(output|input).*(GSA_70|GSP_?670)", name):
        continue
    found = True
    timeout = props.get("session.suspend-timeout-seconds", "(unset -> default 5)")
    print("  %-58s suspend-timeout=%s" % (name[:58], timeout))
if not found:
    print("  (no GSA 70 / GSP 670 nodes found)")
' 
    echo "  A value of 0 means the override is applied (good)."
    echo "  '(unset)' means the drop-in is missing or did not match."
fi

tag "Game / Chat profile (stereo game + mono chat)"
if have wpctl; then
    wpctl status 2>/dev/null | grep -iE 'GSA 70|GSP 670' | sed 's/^/  /' \
        || echo "  no GSA 70 device in wpctl status"
    echo
    echo "  Expected: a stereo 'Game' sink and a mono 'Chat' sink."
    echo "  The Chat sink is what Discord/voice chat should use for output,"
    echo "  and the mic source lives on the Chat device."
fi

tag "Recent EasyEffects errors (resource churn)"
if have journalctl; then
    journalctl --user -b --no-pager 2>/dev/null | grep -i 'pw_manager.cpp' | tail -6 \
        || echo "  none"
fi

tag "Recent Discord audio warnings"
if have journalctl; then
    journalctl --user -b --no-pager 2>/dev/null \
        | grep -iE 'AVError|InputWatcher|no-audio-input' | tail -8 || echo "  none"
fi

tag "Summary"
echo "  If Discord reports no-audio-input-detected while the raw mic works:"
echo "    scripts/gsp670-audio-doctor.sh shows the capture chain; the usual"
echo "    culprits are the EasyEffects mic gate and idle-suspend churn."
echo "  See docs/troubleshooting.md: 'Discord / voice chat'."
