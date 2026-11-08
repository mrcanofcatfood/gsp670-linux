#!/bin/bash
#
# GSP 670 Hardware Test Script
#
# Tests all major functionality of the GSP 670 headset and reports
# pass/fail for each test.
#
# Usage:
#   bash scripts/hardware-test.sh
#
# Requirements:
#   - Root privileges (for HID access)
#   - python3
#   - aplay, arecord (ALSA utils)
#   - GSP 670 headset connected
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
SKIPPED=0

# Print functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_test() {
    echo -e "\n${YELLOW}Test: $1${NC}"
    echo "-------------------------------------------"
}

pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((SKIPPED++))
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${YELLOW}Warning: Not running as root. Some tests may fail.${NC}"
        echo "Consider running with: sudo $0"
    fi
}

# Check dependencies
check_dependencies() {
    print_header "Checking Dependencies"
    
    local deps=("python3" "aplay" "arecord")
    
    for dep in "${deps[@]}"; do
        if command -v "$dep" &> /dev/null; then
            pass "$dep is installed"
        else
            fail "$dep is not installed"
        fi
    done
    
    # Check Python modules
    info "Checking Python modules..."
    if python3 -c "import hid" 2>/dev/null; then
        pass "Python hid module is available"
    else
        fail "Python hid module is not installed (try: pip3 install hidapi)"
    fi
    
    if python3 -c "import gsp670" 2>/dev/null; then
        pass "Python gsp670 module is installed"
    else
        info "Python gsp670 not installed as system module"
        info "Using src/ path instead"
    fi
}

# Test HID device discovery
test_hid_discovery() {
    print_test "HID Device Discovery"
    
    # Try to find dongle
    local dongle_path
    dongle_path=$(python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from gsp670 import find_dongle
    d = find_dongle()
    if d:
        print(d.path.decode('utf-8') if isinstance(d.path, bytes) else d.path)
    else:
        print('NOT_FOUND')
except Exception as e:
    print('ERROR:' + str(e))
" 2>&1)
    
    if [[ "$dongle_path" == "NOT_FOUND" ]]; then
        fail "GSA 70 dongle not found"
    elif [[ "$dongle_path" == ERROR* ]]; then
        fail "Error finding dongle: ${dongle_path#ERROR:}"
    else
        pass "GSA 70 dongle found at $dongle_path"
    fi
    
    # Try to find headset (wired mode)
    local headset_path
    headset_path=$(python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from gsp670 import find_headset
    d = find_headset()
    if d:
        print(d.path.decode('utf-8') if isinstance(d.path, bytes) else d.path)
    else:
        print('NOT_FOUND')
except Exception as e:
    print('ERROR:' + str(e))
" 2>&1)
    
    if [[ "$headset_path" == "NOT_FOUND" ]]; then
        skip "GSP 670 headset not found (wired USB mode)"
    elif [[ "$headset_path" == ERROR* ]]; then
        fail "Error finding headset: ${headset_path#ERROR:}"
    else
        pass "GSP 670 headset found at $headset_path"
    fi
}

# Test device communication
test_device_communication() {
    print_test "Device Communication"
    
    local result
    
    result=$(python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from gsp670 import GSA70Device, CommunicationError
    
    with GSA70Device() as dev:
        # Try GET_FEATURES
        resp = dev.exchange(0x4F12, timeout_ms=1000)
        print('SUCCESS')
except DeviceNotFoundError:
    print('NOT_FOUND')
except CommunicationError as e:
    print('COMM_ERROR:' + str(e))
except Exception as e:
    print('ERROR:' + str(e))
" 2>&1)
    
    if [[ "$result" == "SUCCESS" ]]; then
        pass "Device communication successful"
    elif [[ "$result" == "NOT_FOUND" ]]; then
        fail "Device not found"
    elif [[ "$result" == COMM_ERROR:* ]]; then
        fail "Communication error: ${result#COMM_ERROR:}"
    else
        fail "Error: ${result#ERROR:}"
    fi
}

# Test protocol opcodes
test_protocol_opcodes() {
    print_test "Protocol Opcodes"
    
    local result
    
    result=$(python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from gsp670 import GSA70Device, CommunicationError
    
    results = []
    with GSA70Device() as dev:
        # Test FWU_GET_FEATURES
        try:
            resp = dev.exchange(0x4F12, timeout_ms=500)
            results.append('GET_FEATURES=ACK')
        except CommunicationError:
            results.append('GET_FEATURES=NAK')
        
        # Test FWU_SET_FEATURES  
        try:
            resp = dev.exchange(0x4F10, b'\\x01', timeout_ms=500)
            results.append('SET_FEATURES=ACK')
        except CommunicationError:
            results.append('SET_FEATURES=NAK')
        
        # Test STATUS_IND
        dev.drain(0.2)
        dev.write(0x4F0C)
        dev.drain(0.5)
        results.append('STATUS=OK')
    
    print('|'.join(results))
except DeviceNotFoundError:
    print('NOT_FOUND')
except Exception as e:
    print('ERROR:' + str(e))
" 2>&1)
    
    if [[ "$result" == "NOT_FOUND" ]]; then
        fail "Device not found"
    elif [[ "$result" == ERROR* ]]; then
        fail "Error: ${result#ERROR:}"
    else
        IFS='|' read -ra OPCODES <<< "$result"
        for opcode in "${OPCODES[@]}"; do
            if [[ "$opcode" == *=ACK ]]; then
                pass "Opcode ${opcode%=*}"
            elif [[ "$opcode" == *=NAK ]]; then
                skip "Opcode ${opcode%=*} returned NAK"
            else
                info "$opcode"
            fi
        done
    fi
}

# Test audio device detection
test_audio_devices() {
    print_test "Audio Device Detection"
    
    # Check aplay
    local aplay_output
    aplay_output=$(aplay -l 2>&1)
    if echo "$aplay_output" | grep -qi "G670\|USB Audio"; then
        pass "GSP 670 playback device found"
        
        # Get card number
        local card
        card=$(echo "$aplay_output" | grep -i "G670\|USB Audio" | head -1 | sed -n 's/.*card \([0-9]*\).*/\1/p')
        info "Playback card number: $card"
    else
        fail "GSP 670 playback device not found"
    fi
    
    # Check arecord
    local arecord_output
    arecord_output=$(arecord -l 2>&1)
    if echo "$arecord_output" | grep -qi "G670\|USB Audio"; then
        pass "GSP 670 capture device found"
    else
        skip "GSP 670 capture device not found"
    fi
}

# Test audio playback
test_audio_playback() {
    print_test "Audio Playback"
    
    # Get card number
    local card
    card=$(aplay -l 2>&1 | grep -i "G670\|USB Audio" | head -1 | sed -n 's/.*card \([0-9]*\).*/\1/p')
    
    if [[ -z "$card" ]]; then
        skip "No audio device to test"
        return
    fi
    
    # Generate a short sine wave
    local tmpfile
    tmpfile=$(mktemp /tmp/gsp670_test_XXXXXX.wav)
    
    # Create a small WAV file with a sine wave
    python3 -c "
import struct
import math

sample_rate = 48000
duration = 0.1
frequency = 440

# Generate samples
samples = []
for i in range(int(sample_rate * duration)):
    value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
    samples.append(value)

# Write WAV file
with open('$tmpfile', 'wb') as f:
    # WAV header
    f.write(b'RIFF')
    f.write(struct.pack('<I', 36 + len(samples) * 2))  # file size - 8
    f.write(b'WAVE')
    f.write(b'fmt ')
    f.write(struct.pack('<I', 16))  # chunk size
    f.write(struct.pack('<H', 1))   # PCM format
    f.write(struct.pack('<H', 1))   # mono
    f.write(struct.pack('<I', sample_rate))  # sample rate
    f.write(struct.pack('<I', sample_rate * 2))  # byte rate
    f.write(struct.pack('<H', 2))   # block align
    f.write(struct.pack('<H', 16))  # bits per sample
    f.write(b'data')
    f.write(struct.pack('<I', len(samples) * 2))
    for s in samples:
        f.write(struct.pack('<h', s))
" 2>&1
    
    # Play the file
    if aplay -D "hw:$card,0" "$tmpfile" 2>&1; then
        pass "Audio playback successful"
    else
        fail "Audio playback failed"
    fi
    
    rm -f "$tmpfile"
}

# Test audio capture
test_audio_capture() {
    print_test "Audio Capture"
    
    # Get card number
    local card
    card=$(arecord -l 2>&1 | grep -i "G670\|USB Audio" | head -1 | sed -n 's/.*card \([0-9]*\).*/\1/p')
    
    if [[ -z "$card" ]]; then
        skip "No capture device to test"
        return
    fi
    
    local tmpfile
    
    tmpfile=$(mktemp /tmp/gsp670_capture_XXXXXX.raw)
    
    # Record a short sample
    if timeout 2 arecord -D "hw:$card,0" -c 1 -r 48000 -f S16_LE -t raw "$tmpfile" 2>&1; then
        local size
        size=$(stat -c%s "$tmpfile" 2>/dev/null || stat -f%z "$tmpfile" 2>/dev/null || echo "0")
        if [[ "$size" -gt 1000 ]]; then
            pass "Audio capture successful ($size bytes)"
        else
            fail "Audio capture produced too little data"
        fi
    else
        fail "Audio capture failed"
    fi
    
    rm -f "$tmpfile"
}

# Test HID event monitoring
test_hid_events() {
    print_test "HID Event Monitoring"
    
    info "Starting 3-second HID event monitoring..."
    info "Please interact with the headset (press buttons, adjust volume)"
    
    local events
    
    events=$(python3 -c "
import sys
import time
sys.path.insert(0, 'src')
try:
    from gsp670 import GSA70Device
    
    events = 0
    with GSA70Device() as dev:
        dev.drain(0.2)
        start = time.time()
        while time.time() - start < 3:
            frame = dev.read(timeout_ms=100)
            if frame:
                events += 1
    print(events)
except Exception as e:
    print('ERROR:' + str(e))
" 2>&1)
    
    if [[ "$events" == ERROR* ]]; then
        fail "Error monitoring events: ${events#ERROR:}"
    elif [[ "$events" -gt 0 ]]; then
        pass "Received $events HID events"
    else
        skip "No HID events received (try interacting with headset)"
    fi
}

# Print summary
print_summary() {
    print_header "Test Summary"
    
    local total
    
    total=$((PASSED + FAILED + SKIPPED))
    
    echo -e "Total tests: $total"
    echo -e "${GREEN}Passed:  $PASSED${NC}"
    echo -e "${RED}Failed:  $FAILED${NC}"
    echo -e "${YELLOW}Skipped: $SKIPPED${NC}"
    echo
    
    if [[ $FAILED -eq 0 ]]; then
        echo -e "${GREEN}All tests passed!${NC}"
        return 0
    else
        echo -e "${RED}Some tests failed.${NC}"
        return 1
    fi
}

# Main
main() {
    print_header "GSP 670 Hardware Test Suite"
    
    echo "This script tests all major functionality of the GSP 670 headset"
    echo
    
    check_root
    check_dependencies
    test_hid_discovery
    test_device_communication
    test_protocol_opcodes
    test_audio_devices
    test_audio_playback
    test_audio_capture
    test_hid_events
    
    print_summary
}

main "$@"
