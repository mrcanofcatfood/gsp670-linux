#!/bin/bash
#
# GSP 670 Hardware Test Runner
#
# Runs hardware-specific tests for the GSP 670 headset.
# This script does NOT require sudo but tests actual hardware.
#
# Usage:
#   bash scripts/run-hw-tests.sh
#   bash scripts/run-hw-tests.sh --playback-device hw:3,0 --capture-device hw:3,0
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_FULL_DUPLEX="$PROJECT_DIR/tests/hardware/test_full_duplex.py"

# Parse arguments
PLAYBACK_DEVICE="hw:4,0"
CAPTURE_DEVICE="hw:4,0"
DURATION=3.0

while [[ $# -gt 0 ]]; do
    case $1 in
        --playback-device)
            PLAYBACK_DEVICE="$2"
            shift 2
            ;;
        --capture-device)
            CAPTURE_DEVICE="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --playback-device <dev>  ALSA playback device (default: hw:4,0)"
            echo "  --capture-device <dev>  ALSA capture device (default: hw:4,0)"
            echo "  --duration <seconds>     Test duration (default: 3.0)"
            echo "  --help                  Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if test file exists
if [[ ! -f "$TEST_FULL_DUPLEX" ]]; then
    echo -e "${RED}Error: Full-duplex test not found at $TEST_FULL_DUPLEX${NC}"
    exit 1
fi

# Check dependencies
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}GSP 670 Hardware Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${BLUE}[INFO]${NC} Checking dependencies..."

for cmd in python3 aplay arecord; do
    if command -v "$cmd" &> /dev/null; then
        echo -e "${GREEN}[OK]${NC} $cmd is installed"
    else
        echo -e "${RED}[FAIL]${NC} $cmd is not installed"
        exit 1
    fi
done

echo ""

# Run full-duplex test
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running Full-Duplex Audio Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

python3 "$TEST_FULL_DUPLEX" \
    --playback-device "$PLAYBACK_DEVICE" \
    --capture-device "$CAPTURE_DEVICE" \
    --playback-rate 48000 \
    --capture-rate 16000 \
    --duration "$DURATION"

exit_code=$?

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Complete${NC}"
echo -e "${BLUE}========================================${NC}"

if [[ $exit_code -eq 0 ]]; then
    echo -e "${GREEN}Full-duplex test PASSED${NC}"
else
    echo -e "${RED}Full-duplex test FAILED (exit code: $exit_code)${NC}"
fi

exit $exit_code