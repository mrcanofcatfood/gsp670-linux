#!/usr/bin/env python3
"""
Audio Quality Test for GSP 670

This script generates test tones at different frequencies, records them,
and analyzes for distortion, clipping, or artifacts.

Requirements:
    - numpy (for signal generation and analysis)
    - soundfile (for audio file I/O)
    - scipy (for FFT analysis)
    - pyyaml (for configuration)

Install: pip install numpy soundfile scipy pyyaml
"""

import argparse
import subprocess
import sys
import os
import time
import json
import tempfile
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

# Optional imports with graceful fallback
try:
    import numpy as np
    from numpy.fft import rfft, rfftfreq
    import soundfile as sf
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class TestResult:
    """Result of an audio quality test."""
    frequency: float
    expected_amplitude: float
    measured_amplitude: float
    thd_percent: float  # Total Harmonic Distortion
    noise_floor_db: float
    clipping_detected: bool
    pass: bool
    notes: str = ""


def check_dependencies():
    """Check if required dependencies are installed."""
    missing = []
    if not HAS_NUMPY:
        missing.extend(['numpy', 'soundfile', 'scipy'])
    if not HAS_YAML:
        missing.append('pyyaml')
    
    if missing:
        print("ERROR: Missing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall with: pip install " + " ".join(missing))
        return False
    return True


def generate_sine_wave(frequency: float, duration: float, sample_rate: int, 
                       amplitude: float = 0.8) -> np.ndarray:
    """Generate a sine wave at the given frequency."""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    wave = amplitude * np.sin(2 * np.pi * frequency * t)
    return wave.astype(np.float32)


def generate_sweep(duration: float, start_freq: float, end_freq: float,
                    sample_rate: int, amplitude: float = 0.8) -> np.ndarray:
    """Generate a frequency sweep."""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Logarithmic sweep
    sweep = amplitude * np.sin(2 * np.pi * start_freq * duration * 
                               (np.exp(t / duration * np.log(end_freq / start_freq)) - 1) /
                               (np.log(end_freq / start_freq)))
    return sweep.astype(np.float32)


def play_audio(data: np.ndarray, device: str, sample_rate: int) -> bool:
    """Play audio through the specified device."""
    try:
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_file = f.name
            sf.write(temp_file, data, sample_rate)
        
        # Play using aplay or paplay
        try:
            subprocess.run(['paplay', '--device=' + device, temp_file],
                         check=True, capture_output=True, timeout=30)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to aplay
            subprocess.run(['aplay', '-D', device, '-r', str(sample_rate), 
                           '-f', 'S16_LE', '-t', 'wav', temp_file],
                         check=True, capture_output=True, timeout=30)
        
        os.unlink(temp_file)
        return True
    except Exception as e:
        print(f"Error playing audio: {e}")
        return False


def record_audio(duration: float, device: str, sample_rate: int, 
                 channels: int = 1) -> Optional[np.ndarray]:
    """Record audio from the specified device."""
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_file = f.name
        
        # Record using arecord or parecord
        try:
            subprocess.run(['parecord', '--device=' + device, '-d', str(duration),
                           temp_file], check=True, capture_output=True, timeout=duration + 5)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to arecord
            subprocess.run(['arecord', '-D', device, '-d', str(duration),
                           '-r', str(sample_rate), '-c', str(channels),
                           '-f', 'S16_LE', '-t', 'wav', temp_file],
                         check=True, capture_output=True, timeout=duration + 5)
        
        data, sr = sf.read(temp_file)
        os.unlink(temp_file)
        
        if sr != sample_rate:
            print(f"Warning: Sample rate mismatch (expected {sample_rate}, got {sr})")
        
        return data
    except Exception as e:
        print(f"Error recording audio: {e}")
        return None


def analyze_tone(data: np.ndarray, frequency: float, sample_rate: int,
                 duration: float) -> TestResult:
    """Analyze a recorded tone for quality."""
    # Use only the middle portion to avoid startup transients
    start_idx = int(sample_rate * 0.1)
    end_idx = int(sample_rate * (duration - 0.1))
    analysis_data = data[start_idx:end_idx]
    
    # Calculate RMS amplitude
    rms = np.sqrt(np.mean(analysis_data ** 2))
    
    # Expected amplitude for 0dBFS sine at 0.8 amplitude
    expected_amplitude = 0.8 / np.sqrt(2)  # RMS for 0.8 peak
    
    # FFT analysis
    n = len(analysis_data)
    fft = np.abs(rfft(analysis_data))
    freqs = rfftfreq(n, 1 / sample_rate)
    
    # Find fundamental frequency bin
    freq_bin = int(frequency * n / sample_rate)
    bin_width = sample_rate / n
    
    # Get fundamental amplitude
    fundamental_idx = np.argmax(fft[1:]) + 1  # Skip DC
    fundamental_amp = fft[freq_bin] / n * 2  # Normalize
    
    # Calculate THD (Total Harmonic Distortion)
    harmonics = []
    for h in range(2, 10):  # Check up to 9th harmonic
        harmonic_freq = frequency * h
        if harmonic_freq < sample_rate / 2:
            harmonic_bin = int(harmonic_freq * n / sample_rate)
            if harmonic_bin < len(fft):
                harmonics.append(fft[harmonic_bin])
    
    if harmonics:
        harmonic_power = np.sqrt(np.sum(np.array(harmonics) ** 2))
        if fundamental_amp > 0:
            thd = (harmonic_power / fundamental_amp) * 100
        else:
            thd = 100
    else:
        thd = 0
    
    # Noise floor (energy in non-signal bins)
    noise_bins = np.concatenate([
        np.arange(0, max(0, freq_bin - 50)),
        np.arange(min(len(fft), freq_bin + 50), len(fft))
    ])
    if len(noise_bins) > 0:
        noise_floor = np.mean(fft[noise_bins]) / n * 2
        noise_floor_db = 20 * np.log10(max(noise_floor, 1e-10))
    else:
        noise_floor_db = -100
    
    # Clip detection
    clipping_detected = np.any(np.abs(data) >= 0.99)
    
    # Pass/fail criteria
    amplitude_error_percent = abs(rms - expected_amplitude) / expected_amplitude * 100
    amplitude_pass = amplitude_error_percent < 20  # Within 20%
    thd_pass = thd < 5  # Less than 5% THD
    noise_pass = noise_floor_db < -40  # Better than -40dB
    clip_pass = not clipping_detected
    
    test_pass = amplitude_pass and thd_pass and noise_pass and clip_pass
    
    notes = []
    if not amplitude_pass:
        notes.append(f"Amplitude error: {amplitude_error_percent:.1f}%")
    if not thd_pass:
        notes.append(f"THD: {thd:.2f}%")
    if not noise_pass:
        notes.append(f"Noise floor: {noise_floor_db:.1f}dB")
    if clipping_detected:
        notes.append("CLIPPING DETECTED")
    
    return TestResult(
        frequency=frequency,
        expected_amplitude=expected_amplitude,
        measured_amplitude=rms,
        thd_percent=thd,
        noise_floor_db=noise_floor_db,
        clipping_detected=clipping_detected,
        pass=test_pass,
        notes="; ".join(notes) if notes else "OK"
    )


def find_gsp670_device() -> Tuple[Optional[str], Optional[str]]:
    """Find GSP 670 playback and capture devices."""
    playback_device = None
    capture_device = None
    
    try:
        # Try to find using pwctl
        result = subprocess.run(['wpctl', 'status'], capture_output=True, text=True, timeout=10)
        lines = result.stdout.split('\n')
        
        in_playback = False
        in_capture = False
        
        for line in lines:
            if 'GSP' in line or 'G670' in line:
                # Extract node ID from line like "42. <name>"
                parts = line.split()
                if parts and parts[0].isdigit():
                    node_id = parts[0]
                    # Determine if playback or capture based on context
                    if in_playback:
                        playback_device = node_id
                    elif in_capture:
                        capture_device = node_id
            elif 'Playback' in line:
                in_playback = True
                in_capture = False
            elif 'Capture' in line:
                in_capture = True
                in_playback = False
    except Exception:
        pass
    
    # Fallback to ALSA device names
    if not playback_device or not capture_device:
        try:
            result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'G670' in line or 'EPOS' in line:
                    if 'card' in line.lower():
                        card_num = line.split('card')[1].split(':')[0].strip()
                        playback_device = f'hw:{card_num},0'
                        capture_device = f'hw:{card_num},0'
        except Exception:
            pass
    
    return playback_device, capture_device


def run_latency_test(playback_device: str, capture_device: str,
                      sample_rate: int = 48000) -> Optional[float]:
    """Measure audio latency by playing and recording a click."""
    # Generate a short click/impulse
    click = np.zeros(int(sample_rate * 0.01))
    click[0] = 0.8  # Impulse at start
    
    try:
        # Record a quick test to measure loopback latency
        # This is a simplified test - real latency measurement needs specialized tools
        
        # Play the click
        if not play_audio(click, playback_device, sample_rate):
            return None
        
        time.sleep(0.05)
        
        # Record response
        recorded = record_audio(0.5, capture_device, sample_rate)
        
        if recorded is None:
            return None
        
        # Find the impulse response
        abs_recorded = np.abs(recorded)
        peak_idx = np.argmax(abs_recorded)
        
        # Calculate latency in milliseconds
        latency_samples = peak_idx
        latency_ms = (latency_samples / sample_rate) * 1000
        
        return latency_ms
    except Exception as e:
        print(f"Latency test error: {e}")
        return None


def run_quality_tests(playback_device: str, capture_device: str,
                      frequencies: List[float] = None,
                      sample_rate: int = 48000) -> List[TestResult]:
    """Run quality tests at specified frequencies."""
    if frequencies is None:
        frequencies = [100, 250, 500, 1000, 2000, 4000, 8000]
    
    results = []
    
    print("Audio Quality Test")
    print("=" * 60)
    print(f"Playback device: {playback_device}")
    print(f"Capture device: {capture_device}")
    print(f"Sample rate: {sample_rate} Hz")
    print()
    
    for freq in frequencies:
        print(f"Testing {freq} Hz...", end=" ", flush=True)
        
        # Generate test tone (1 second duration)
        tone = generate_sine_wave(freq, 1.0, sample_rate)
        
        # Play
        if not play_audio(tone, playback_device, sample_rate):
            print("FAILED (play error)")
            continue
        
        # Small delay between play and record
        time.sleep(0.2)
        
        # Record (need to record a bit longer to capture the tone)
        recorded = record_audio(1.5, capture_device, sample_rate)
        
        if recorded is None:
            print("FAILED (record error)")
            continue
        
        # Analyze
        result = analyze_tone(recorded, freq, sample_rate, 1.5)
        
        if result.pass:
            print(f"PASS (THD: {result.thd_percent:.2f}%, Noise: {result.noise_floor_db:.1f}dB)")
        else:
            print(f"FAIL - {result.notes}")
        
        results.append(result)
    
    return results


def print_summary(results: List[TestResult]) -> bool:
    """Print test summary and return overall pass/fail."""
    print()
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for r in results if r.pass)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    print()
    
    # Print detailed results table
    print(f"{'Freq (Hz)':<12} {'THD %':<10} {'Noise (dB)':<12} {'Clip':<6} {'Status':<8}")
    print("-" * 60)
    
    for r in results:
        clip_str = "YES" if r.clipping_detected else "No"
        status_str = "PASS" if r.pass else "FAIL"
        print(f"{r.frequency:<12.0f} {r.thd_percent:<10.2f} {r.noise_floor_db:<12.1f} {clip_str:<6} {status_str:<8}")
    
    print()
    
    all_passed = all(r.pass for r in results)
    if all_passed:
        print("Overall: ALL TESTS PASSED")
    else:
        print("Overall: SOME TESTS FAILED")
    
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Audio Quality Test for GSP 670"
    )
    parser.add_argument('--playback-device', '-p',
                        help='Playback device (ALSA hw:X or PipeWire node ID)')
    parser.add_argument('--capture-device', '-c',
                        help='Capture device (ALSA hw:X or PipeWire node ID)')
    parser.add_argument('--sample-rate', '-r', type=int, default=48000,
                        help='Sample rate (default: 48000)')
    parser.add_argument('--frequencies', '-f', type=str,
                        help='Comma-separated list of test frequencies (default: 100,250,500,1000,2000,4000,8000)')
    parser.add_argument('--latency-test', '-l', action='store_true',
                        help='Run latency measurement test')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Output results as JSON')
    parser.add_argument('--output', '-o', type=str,
                        help='Save results to file')
    
    args = parser.parse_args()
    
    if not check_dependencies():
        return 1
    
    # Parse frequencies
    if args.frequencies:
        try:
            frequencies = [float(f) for f in args.frequencies.split(',')]
        except ValueError:
            print("Error: Invalid frequency list")
            return 1
    else:
        frequencies = [100, 250, 500, 1000, 2000, 4000, 8000]
    
    # Find devices if not specified
    playback_device = args.playback_device
    capture_device = args.capture_device
    
    if not playback_device or not capture_device:
        p, c = find_gsp670_device()
        playback_device = playback_device or p
        capture_device = capture_device or c
    
    if not playback_device or not capture_device:
        print("Error: Could not find GSP 670 devices")
        print("Specify devices manually with --playback-device and --capture-device")
        return 1
    
    # Run quality tests
    results = run_quality_tests(playback_device, capture_device, frequencies, args.sample_rate)
    
    # Run latency test if requested
    latency_ms = None
    if args.latency_test:
        print()
        print("Running latency test...")
        latency_ms = run_latency_test(playback_device, capture_device, args.sample_rate)
        if latency_ms is not None:
            print(f"Measured latency: {latency_ms:.1f} ms")
        else:
            print("Could not measure latency")
    
    # Print summary
    all_passed = print_summary(results)
    
    # JSON output
    if args.json:
        output = {
            'tested_frequencies': frequencies,
            'sample_rate': args.sample_rate,
            'playback_device': playback_device,
            'capture_device': capture_device,
            'results': [
                {
                    'frequency': r.frequency,
                    'expected_amplitude': float(r.expected_amplitude),
                    'measured_amplitude': float(r.measured_amplitude),
                    'thd_percent': float(r.thd_percent),
                    'noise_floor_db': float(r.noise_floor_db),
                    'clipping_detected': r.clipping_detected,
                    'pass': r.pass,
                    'notes': r.notes
                }
                for r in results
            ],
            'latency_ms': latency_ms,
            'overall_pass': all_passed
        }
        print()
        print(json.dumps(output, indent=2))
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            if args.json:
                json.dump(output, f, indent=2)
            else:
                # Text format
                f.write("GSP 670 Audio Quality Test Results\n")
                f.write("=" * 60 + "\n\n")
                for r in results:
                    f.write(f"Frequency: {r.frequency} Hz\n")
                    f.write(f"  THD: {r.thd_percent:.2f}%\n")
                    f.write(f"  Noise Floor: {r.noise_floor_db:.1f} dB\n")
                    f.write(f"  Clipping: {'Yes' if r.clipping_detected else 'No'}\n")
                    f.write(f"  Status: {'PASS' if r.pass else 'FAIL'}\n")
                    f.write(f"  Notes: {r.notes}\n\n")
        print(f"\nResults saved to: {args.output}")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
