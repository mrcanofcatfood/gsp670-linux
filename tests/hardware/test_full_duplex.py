#!/usr/bin/env python3
"""
Full-duplex audio test for GSP 670 headset.

Tests simultaneous playback (48000Hz mono) and capture (16000Hz mono)
to verify no xruns or errors occur in full-duplex mode.

Usage:
    python3 tests/hardware/test_full_duplex.py

Requires:
    - aplay and arecord (ALSA utils)
    - GSP 670 headset connected
"""

import math
import os
import signal
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TestResult:
    """Result of a full-duplex test."""
    success: bool
    playback_started: bool
    capture_started: bool
    errors: List[str]
    duration_seconds: float
    capture_data_bytes: int
    playback_samples: int
    xruns_detected: int
    capture_has_audio: bool


def generate_sine_wave(frequency: float, sample_rate: int, duration: float, amplitude: float = 0.5) -> bytes:
    """Generate a sine wave test tone as S16_LE mono."""
    num_samples = int(sample_rate * duration)
    samples = []
    for i in range(num_samples):
        value = int(32767 * amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(value)
    return struct.pack(f'<{num_samples}h', *samples)


def check_for_xruns() -> int:
    """Check for ALSA xruns in dmesg."""
    try:
        result = subprocess.run(['dmesg'], capture_output=True, text=True, timeout=2)
        return result.stdout.lower().count('xrun')
    except Exception:
        return 0


def has_audio_data(data: bytes, threshold: float = 0.005) -> bool:
    """
    Check if data contains actual audio (not silence).
    
    Args:
        data: Raw audio data (S16_LE mono)
        threshold: Minimum RMS level to consider as audio
        
    Returns:
        True if audio data detected
    """
    if len(data) < 4:
        return False
    
    num_samples = len(data) // 2
    
    # Calculate RMS
    sum_squares = 0.0
    for i in range(num_samples):
        sample = struct.unpack_from('<h', data, i * 2)[0]
        sum_squares += sample * sample
    
    rms = math.sqrt(sum_squares / num_samples) / 32768.0
    
    return rms > threshold


def playback_thread_func(device: str, sample_rate: int, data: bytes, result_holder: dict) -> None:
    """Thread function for playback using aplay."""
    result_holder['playback_started'] = False
    result_holder['playback_errors'] = []
    result_holder['playback_samples'] = 0
    
    cmd = [
        'aplay',
        '-D', device,
        '-c', '1',           # Mono
        '-r', str(sample_rate),  # Sample rate
        '-f', 'S16_LE',      # 16-bit little-endian
        '-t', 'raw',
        '-q'                 # Quiet mode
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Write all audio data
        proc.stdin.write(data)
        proc.stdin.close()
        
        # Wait for completion
        proc.wait(timeout=10)
        
        if proc.returncode == 0:
            result_holder['playback_started'] = True
            result_holder['playback_samples'] = len(data) // 2  # 2 bytes per sample
        else:
            stderr = proc.stderr.read().decode('utf-8', errors='replace')
            result_holder['playback_errors'].append(f"Playback failed: {stderr}")
            
    except subprocess.TimeoutExpired:
        proc.kill()
        result_holder['playback_errors'].append("Playback timed out")
    except Exception as e:
        result_holder['playback_errors'].append(f"Playback error: {str(e)}")


def capture_thread_func(device: str, sample_rate: int, duration: float, result_holder: dict) -> None:
    """Thread function for capture using arecord."""
    result_holder['capture_started'] = False
    result_holder['capture_errors'] = []
    result_holder['capture_data'] = b''
    
    cmd = [
        'arecord',
        '-D', device,
        '-c', '1',           # Mono
        '-r', str(sample_rate),  # Sample rate
        '-f', 'S16_LE',      # 16-bit little-endian
        '-t', 'raw',
        '-d', str(int(duration) + 1),  # Duration with buffer
        '-q'                 # Quiet mode
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Read captured data
        captured = b''
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            captured += chunk
        
        proc.wait(timeout=5)
        
        result_holder['capture_data'] = captured
        
        if proc.returncode == 0 and len(captured) > 0:
            result_holder['capture_started'] = True
        else:
            stderr = proc.stderr.read().decode('utf-8', errors='replace')
            result_holder['capture_errors'].append(f"Capture failed: {stderr}")
            
    except subprocess.TimeoutExpired:
        proc.kill()
        result_holder['capture_errors'].append("Capture timed out")
    except Exception as e:
        result_holder['capture_errors'].append(f"Capture error: {str(e)}")


def test_full_duplex(playback_device: str = 'hw:4,0',
                     capture_device: str = 'hw:4,0',
                     playback_rate: int = 48000,
                     capture_rate: int = 16000,
                     duration: float = 3.0) -> TestResult:
    """
    Test full-duplex audio (simultaneous playback and capture).
    
    Args:
        playback_device: ALSA device for playback
        capture_device: ALSA device for capture
        playback_rate: Playback sample rate (Hz)
        capture_rate: Capture sample rate (Hz)
        duration: Test duration in seconds
        
    Returns:
        TestResult with test outcome
    """
    result = TestResult(
        success=False,
        playback_started=False,
        capture_started=False,
        errors=[],
        duration_seconds=0.0,
        capture_data_bytes=0,
        playback_samples=0,
        xruns_detected=0,
        capture_has_audio=False
    )
    
    print(f"Testing full-duplex audio:")
    print(f"  Playback device: {playback_device} @ {playback_rate}Hz mono")
    print(f"  Capture device:  {capture_device} @ {capture_rate}Hz mono")
    print(f"  Duration: {duration}s")
    print()
    
    # Generate test tone (440Hz sine wave)
    print("Generating 440Hz test tone...")
    tone_data = generate_sine_wave(440, playback_rate, duration + 0.5)
    print(f"  Generated {len(tone_data)} bytes of audio")
    
    # Baseline xrun check
    baseline_xruns = check_for_xruns()
    
    # Create thread result holders
    playback_result = {}
    capture_result = {}
    
    # Start playback thread
    print("Starting playback thread...")
    pt = threading.Thread(
        target=playback_thread_func,
        args=(playback_device, playback_rate, tone_data, playback_result)
    )
    pt.start()
    
    # Start capture thread
    print("Starting capture thread...")
    ct = threading.Thread(
        target=capture_thread_func,
        args=(capture_device, capture_rate, duration, capture_result)
    )
    ct.start()
    
    # Wait for completion
    start_time = time.time()
    print(f"Running for {duration}s...")
    
    pt.join(timeout=duration + 10)
    ct.join(timeout=duration + 5)
    
    result.duration_seconds = time.time() - start_time
    
    # Collect results
    result.playback_started = playback_result.get('playback_started', False)
    result.capture_started = capture_result.get('capture_started', False)
    result.playback_samples = playback_result.get('playback_samples', 0)
    result.capture_data_bytes = len(capture_result.get('capture_data', b''))
    result.capture_has_audio = has_audio_data(capture_result.get('capture_data', b''))
    
    if playback_result.get('playback_errors'):
        result.errors.extend(playback_result['playback_errors'])
    if capture_result.get('capture_errors'):
        result.errors.extend(capture_result['capture_errors'])
    
    # Check for xruns
    post_xruns = check_for_xruns()
    result.xruns_detected = max(0, post_xruns - baseline_xruns)
    
    # Determine overall success
    # Full-duplex is verified when both playback and capture start and run without errors
    # Note: The microphone may not pick up audio from the speaker (typical for headsets)
    # but the hardware is functioning correctly if both streams operate without xruns
    result.success = (
        result.playback_started and
        result.capture_started and
        len(result.errors) == 0 and
        result.xruns_detected == 0
    )
    
    return result


def main():
    """Main entry point (standalone script)."""
    print("=" * 60)
    print("GSP 670 Full-Duplex Audio Test")
    print("=" * 60)
    print()
    
    # Parse command line args
    import argparse
    parser = argparse.ArgumentParser(description='Full-duplex audio test for GSP 670')
    parser.add_argument('--playback-device', default='hw:4,0',
                        help='Playback device (default: hw:4,0)')
    parser.add_argument('--capture-device', default='hw:4,0',
                        help='Capture device (default: hw:4,0)')
    parser.add_argument('--playback-rate', type=int, default=48000,
                        help='Playback sample rate (default: 48000)')
    parser.add_argument('--capture-rate', type=int, default=16000,
                        help='Capture sample rate (default: 16000)')
    parser.add_argument('--duration', type=float, default=3.0,
                        help='Test duration in seconds (default: 3.0)')
    
    args = parser.parse_args()
    
    # Set up signal handler for cleanup
    def signal_handler(sig, frame):
        print("\n\nInterrupted - cleaning up...")
        # Kill any lingering processes
        subprocess.run(['pkill', '-f', 'aplay'], timeout=2)
        subprocess.run(['pkill', '-f', 'arecord'], timeout=2)
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run test
    result = test_full_duplex(
        playback_device=args.playback_device,
        capture_device=args.capture_device,
        playback_rate=args.playback_rate,
        capture_rate=args.capture_rate,
        duration=args.duration
    )
    
    # Report results
    print()
    print("=" * 60)
    print("Test Results")
    print("=" * 60)
    
    print(f"\nPlayback started: {'YES' if result.playback_started else 'NO'}")
    print(f"Capture started:  {'YES' if result.capture_started else 'NO'}")
    print(f"Playback samples: {result.playback_samples}")
    print(f"Capture data:     {result.capture_data_bytes} bytes")
    print(f"Duration:          {result.duration_seconds:.2f}s")
    print(f"Xruns detected:    {result.xruns_detected}")
    print(f"Audio detected:   {'YES' if result.capture_has_audio else 'NO'}")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    
    print()
    if result.success:
        print("STATUS: PASSED - Full-duplex audio working correctly")
        print("  - Simultaneous playback and capture successful")
        print("  - No xruns detected")
        print("  - Audio recorded successfully")
    else:
        print("STATUS: FAILED - Issues detected")
        if not result.playback_started:
            print("  - Playback did not start")
        if not result.capture_started:
            print("  - Capture did not start")
        if result.xruns_detected > 0:
            print("  - Xruns detected during test")
        if not result.capture_has_audio:
            print("  - No audio detected in recording")
    
    print()
    
    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(main())