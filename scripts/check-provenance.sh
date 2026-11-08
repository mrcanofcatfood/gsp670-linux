#!/usr/bin/env bash
#
# check-provenance.sh -- enforce the publication boundary for this repository.
#
# This project publishes the hardware *interface* (the wire format, opcode
# numbers, payloads, event names). It must never publish the vendor's
# *implementation* (binaries, decompiled output, captures, disassembly,
# internal symbol names, code addresses) or anything else that is
# proprietary.
#
# The rules below are checked against TRACKED files only, so a local
# artefact cannot affect the result.
#
# Usage:
#   scripts/check-provenance.sh
#
# Exit status:
#   0  clean
#   1  a forbidden pattern was found
#   2  the repository could not be inspected
#
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 2

# --- Configuration ----------------------------------------------------------

# Maximum size for a tracked file. Anything larger is assumed to be an
# accidental capture, firmware image or VM disk.
MAX_FILE_BYTES="${GSP670_MAX_FILE_BYTES:-262144}"   # 256 KiB

# Allow-list. Each entry is "<path-glob>|<extended-regex>", and the regex is
# matched against the file's contents. These exist so that the legal and
# provenance documentation can *discuss* the patterns below without tripping
# them.
ALLOWLIST_FILE="scripts/provenance-allowlist.txt"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_ERR=$'\033[31m'; C_WARN=$'\033[33m'; C_OK=$'\033[32m'
    C_INFO=$'\033[36m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_ERR=""; C_WARN=""; C_OK=""; C_INFO=""; C_DIM=""; C_OFF=""
fi

info() { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
err()  { printf '%serr %s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; }
dim()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }

failures=0

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    err "Not a git repository; cannot determine the tracked file list."
    exit 2
fi

# Tracked files only. -z avoids quoting problems with unusual names.
mapfile -d '' TRACKED < <(git ls-files -z)

if [ "${#TRACKED[@]}" -eq 0 ]; then
    err "No tracked files found."
    exit 2
fi

info "Checking ${#TRACKED[@]} tracked files against the publication boundary"

# --- Load the allow-list ----------------------------------------------------
# Format: <path-glob>|<regex>. Blank lines and '#' comments are ignored.
declare -A ALLOWED_PATH_ALLOW=()   # path glob -> newline-separated regexes
if [ -f "$ALLOWLIST_FILE" ]; then
    while IFS='|' read -r glob regex; do
        # strip surrounding whitespace
        glob="${glob#"${glob%%[![:space:]]*}"}"
        glob="${glob%"${glob##*[![:space:]]}"}"
        regex="${regex#"${regex%%[![:space:]]*}"}"
        regex="${regex%"${regex##*[![:space:]]}"}"
        [ -z "$glob" ] && continue
        case "$glob" in \#*) continue ;; esac
        ALLOWED_PATH_ALLOW["$glob"]="${ALLOWED_PATH_ALLOW[$glob]:-}${regex}"$'\n'
    done < "$ALLOWLIST_FILE"
else
    warn "No allow-list at $ALLOWLIST_FILE; every tracked file is checked strictly."
fi

# Return 0 if the file is allowed to contain the given regex.
is_allowed() {
    local path="$1" regex="$2" glob list
    for glob in "${!ALLOWED_PATH_ALLOW[@]}"; do
        # shellcheck disable=SC2053
        [[ "$path" == $glob ]] || continue
        list="${ALLOWED_PATH_ALLOW[$glob]}"
        while IFS= read -r allowed; do
            [ -z "$allowed" ] && continue
            if printf '%s' "$regex" | grep -qE "$allowed" 2>/dev/null; then
                return 0
            fi
        done <<< "$list"
    done
    return 1
}

report() {
    # report <file> <rule> <detail>
    err "$1"
    dim "     rule: $2"
    dim "     $3"
    failures=$((failures + 1))
}

# --- Rule 1: forbidden file extensions --------------------------------------
FORBIDDEN_EXT='\.(msi|exe|dll|so|dylib|bin|qcow2|qcow|pcap|pcapng|img|iso|deb|rpm|appimage)$'
for f in "${TRACKED[@]}"; do
    if printf '%s' "$f" | grep -qE "$FORBIDDEN_EXT"; then
        report "$f" "forbidden binary extension" \
            "Remove it from the repository; proprietary or capture artefacts must not be published."
    fi
done

# --- Rule 2: oversized tracked files -----------------------------------------
for f in "${TRACKED[@]}"; do
    [ -f "$f" ] || continue
    size=$(wc -c < "$f" 2>/dev/null || echo 0)
    if [ "$size" -gt "$MAX_FILE_BYTES" ]; then
        report "$f" "file too large ($size bytes > $MAX_FILE_BYTES)" \
            "Large tracked files are almost always accidental captures or images."
    fi
done

# --- Rules 3-6: content patterns in text files ------------------------------
# Only inspect files that are plausibly text.
check_content() {
    local path="$1" regex="$2" rule="$3" detail="$4"

    [ -f "$path" ] || return 0
    case "$path" in
        *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.wav|*.ico|*.otf) return 0 ;;
    esac
    # Skip files with NUL bytes; they are binary.
    if grep -qI . "$path" 2>/dev/null; then :; else return 0; fi

    local hits
    hits=$(grep -nEI "$regex" "$path" 2>/dev/null | head -5)
    [ -z "$hits" ] && return 0

    if is_allowed "$path" "$regex"; then
        dim "  allowed: $path ($rule)"
        return 0
    fi

    report "$path" "$rule" "$detail"
    printf '%s\n' "$hits" | while IFS= read -r line; do
        dim "     $line"
    done
}

# Rule 3: vendor code addresses from the vendor's binaries.
#   0x00xxxxxx is the shape of an address inside a 32-bit PE image.
for f in "${TRACKED[@]}"; do
    check_content "$f" '0x00[0-9a-f]{6}\b' "vendor code address" \
        "Remove the address, or describe the behaviour in high-level terms instead."
done

# Rule 4: internal symbol names from the vendor's analysis output.
#   Note: no \b word boundary — GNU grep treats "_" as a word character, so
#   \bFUN_ does not match. A plain substring match is used instead.
for f in "${TRACKED[@]}"; do
    check_content "$f" 'FUN_[0-9a-f]{6}' "internal symbol name" \
        "Remove the symbol name; it describes the vendor's implementation, not the interface."
done

# Rule 5: disassembly listings.
#   A vendor address is 0x followed by 8 hex digits, so the mnemonic follows
#   after "0x" + 8 hex digits + whitespace.
for f in "${TRACKED[@]}"; do
    case "$f" in
        docs/*|*.md) ;;
        *) continue ;;
    esac
    check_content "$f" '^[[:space:]]*0x[0-9a-f]{6,8}[[:space:]]+[a-z]{2,7}' "disassembly listing" \
        "Remove the disassembly; it reproduces the vendor's implementation."
done

# Rule 6: names of the vendor's proprietary executables.
for f in "${TRACKED[@]}"; do
    check_content "$f" 'EPOSGamingSuite' "vendor executable name" \
        "Refer to it by product name only, or remove the reference."
done

# Rule 7: internal method and class names from the vendor's implementation.
#
# These are the names of functions and types inside the vendor's closed-source
# software. They describe the implementation, not the interface, so they must
# not be published. The pattern is an explicit list rather than a general
# heuristic, because the project has its own similarly-shaped API names
# (parse_event_payload, parse_frame_event, ...) that must remain allowed.
VENDOR_METHODS='parseSwVersion|parseGetSerialNumber|parseDeviceName|parseBDAddr|parseDfuType|parseEnterDfu|parsesubDevicesConnected|parseDeviceBtName|parsePIDNumber|GetBatPercentage|GetAutoPowerOffTimerStatus|SetAutoPowerOffTimerStatus|GetSideToneGain|GetNoiseReductionLevel|GetLatencyLevel|GetNbrLinkKeys|GetRemoteDeviceInfo|setNoiseReduction|setSideToneValue|SendLatencyCommand'
VENDOR_CLASSES='CCapricornDatagram|CSecomParserAdapter|QtilSecomParser|ModiBaseStationDevice|ModiHeadsetDevice|hModiHeadsetDevice|ModiFirmwareUpdater|ModiUpdater'
VENDOR_LIBS='CxAudioHid[A-Za-z]*|HidDfu[A-Za-z]*'

for f in "${TRACKED[@]}"; do
    check_content "$f" "($VENDOR_METHODS)" "vendor method name" \
        "Remove the vendor's internal method name; describe the behaviour instead."
    check_content "$f" "($VENDOR_CLASSES)" "vendor class name" \
        "Remove the vendor's internal class name; it describes their implementation."
    check_content "$f" "($VENDOR_LIBS)" "vendor library name" \
        "Remove the vendor's internal library name."
done

# --- Rule 8: licence-key and private-key artefacts --------------------------
KEY_RE='-----BEGIN [A-Z ]*PRIVATE KEY-----|(licen[cs]e|activation|serial)[_-]?key'
for f in "${TRACKED[@]}"; do
    check_content "$f" "$KEY_RE" "key artefact" \
        "Licence or activation key material must never be committed."
done

# --- Result ------------------------------------------------------------------
echo
if [ "$failures" -eq 0 ]; then
    ok "Provenance check passed: no proprietary material found."
    exit 0
fi

err "Provenance check FAILED: $failures problem(s) found."
echo
echo "This repository publishes the hardware interface only. The vendor's"
echo "implementation detail — binaries, decompiled output, captures,"
echo "disassembly, internal symbol names and code addresses — belongs in the"
echo "maintainer's private workbench and must not be committed here."
echo
echo "See docs/legal.md for the policy and scripts/provenance-allowlist.txt"
echo "if a specific file needs an exemption."
exit 1
