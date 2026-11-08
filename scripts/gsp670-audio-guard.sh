#!/usr/bin/env bash
# gsp670-audio-guard.sh -- ensure the EPOS GSA 70 (1395:0300) USB-audio card
# is registered.
#
# Why this exists
# ---------------
# On Linux the GSA 70 needs the ALSA interface-reorder quirk (upstream since
# 5.14.15) to expose its "Game"/"Chat" outputs and microphone. However
# snd-usb-audio can occasionally come back from a device (re-)enumeration
# having *bound* the dongle's audio interfaces without ever creating an ALSA
# card.  In that state /proc/asound/cards has no "EPOS GSA 70" entry, there is
# no PipeWire sink/source, and the headset is completely silent.  A clean
# module re-probe restores the card.  This was observed at boot and after the
# dongle re-enumerates when the headset powers on/off.
#
# The script is a no-op unless (a) the dongle is plugged in and (b) its card is
# missing, so it is safe to run at any time.
set -u

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

TAG=gsp670-audio-guard
log() { logger -t "$TAG" -- "$*" 2>/dev/null || true; }

# The dongle's USB vendor/product id. Match on BOTH: the vendor id 0x1395 is
# shared with other Sennheiser/EPOS devices (e.g. the wired GSP 670 in USB
# device mode, 1395:008a), and reacting to those would reload snd-usb-audio
# for unrelated hardware.
DONGLE_VID="1395"
DONGLE_PID="0300"

# dongle_present -> 0 if the GSA 70 dongle is plugged in.
dongle_present() {
    local d
    for d in /sys/bus/usb/devices/*/idVendor; do
        [ -r "$d" ] || continue
        [ "$(cat "$d" 2>/dev/null)" = "$DONGLE_VID" ] || continue
        # Same device directory -> check the product id.
        local pid_file="${d%/idVendor}/idProduct"
        [ -r "$pid_file" ] || continue
        [ "$(cat "$pid_file" 2>/dev/null)" = "$DONGLE_PID" ] && return 0
    done
    return 1
}

# card_present -> 0 if the ALSA card for the dongle is registered.
card_present() {
    grep -qiE 'EPOS GSA 70|\[E70' /proc/asound/cards 2>/dev/null
}

dongle_present || exit 0     # dongle not plugged in -> nothing to do
card_present  && exit 0      # card already healthy   -> nothing to do

log "audio card missing; re-probing snd-usb-audio"
if ! modprobe -r snd-usb-audio 2>/dev/null; then
    log "could not unload snd-usb-audio (in use?); leaving as-is"
    exit 0
fi
sleep 1
modprobe snd-usb-audio 2>/dev/null

for _ in 1 2 3 4 5; do
    card_present && break
    sleep 1
done

if card_present; then
    log "card restored"
else
    log "card still missing after re-probe"
fi
