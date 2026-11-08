#!/usr/bin/env python3
"""Objective virtual-surround verification for the GSP 670 / GSA 70.

The headset exposes only a stereo ALSA device, so "is surround working?"
cannot be judged by ear from stereo content. This script makes it testable:

1. Generates an 8-channel WAV with a distinct sine tone per channel
   (FL FR FC LFE SL SR RL RR).
2. Plays it into the GSP670_Surround filter-chain sink while recording the
   monitor of the GSA 70 stereo "Game" sink — i.e. exactly the signal the
   headset receives.
3. FFT-analyses the recording: each input channel's tone must survive with
   the expected left/right balance (front left -> far left, center ->
   centred, surrounds -> attenuated on their side).

8/8 PASS means every surround channel provably reaches the headset through
the HRTF chain. 2/8 means you are listening to a plain stereo path.

Modes:
  --generate FILE   write the 8-channel test tone WAV and exit
  --test            play + record + analyse the surround sink (default mode)
  --ab              additionally run the same test against the raw stereo
                    GSA 70 sink and print both signatures side by side
  --listen          run `speaker-test -c 8 -t wav` so you can hear the
                    spoken channel positions through the surround sink
  --set-default     make GSP670_Surround the default sink first (with
                    --listen)

Requires: numpy, pw-cat, ffmpeg (monitor capture), pactl/wpctl.
"""

import argparse
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave

try:
    import numpy as np
except ImportError:  # pragma: no cover
    sys.exit("numpy is required:  pacman -S python-numpy")

RATE = 48000
TONE_SECONDS = 1.2
GAP_SECONDS = 0.25
AMPLITUDE = 0.12
PRE_ROLL = 0.8          # recording lead-in before playback starts
POST_ROLL = 0.4         # recording tail after playback ends

# File channel order == libsndfile/ALSA 7.1 layout (positional WAV mask).
POSITIONS = ["FL", "FR", "FC", "LFE", "SL", "SR", "RL", "RR"]
# All tones kept below 833 Hz (1/(2*815)) so the HRTF's interaural time
# differences (up to ~0.6 ms) do not alias in the per-tone phase measurement.
FREQUENCIES = {
    "FL": 220.0, "FR": 305.0, "FC": 390.0, "LFE": 475.0,
    "SL": 560.0, "SR": 645.0, "RL": 730.0, "RR": 815.0,
}
# pan = 10*log10(R/L) level difference; itd = (phiR-phiL)/(2*pi*f), the time
# by which the right ear lags the left. A left-side source makes the right
# ear later: itd < 0 (the GSX IR gives 0.23-0.56 ms). Right-side: itd > 0.
PAN_EXPECT = {
    "FL": "L", "FR": "R", "FC": "C", "LFE": "C",
    "SL": "L", "SR": "R", "RL": "L", "RR": "R",
}
PAN_DB_TOL = 3.0        # |pan| beyond this counts as L or R
ITD_MS_TOL = 0.08       # |itd| beyond this counts as L or R
CENTER_ITD_MS = 0.50    # center channels must stay within this
CENTER_PAN_DB = 5.0     # ... and this (IR center taps aren't perfectly
                        # symmetric at every frequency; the gsx IR measures
                        # -3.4 dB / -0.44 ms at 475 Hz by design)
PRESENCE_SNR_DB = 12.0  # tone must exceed local noise floor by this

SURROUND_SINK = "GSP670_Surround"
GSA_GAME = "alsa_output.usb-Sennheiser_EPOS_GSA_70-00.stereo-game"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def sink_exists(name):
    out = subprocess.run(["pactl", "list", "short", "sinks"],
                         capture_output=True, text=True).stdout
    return any(row.split("\t")[1] == name
               for row in out.splitlines() if row.strip())


def generate_test_wav(path):
    """8-channel WAV; each channel carries its own tone in its own time slot
    (sequential, so analysis can attribute each slot to one position)."""
    tone_n = int(RATE * TONE_SECONDS)
    gap_n = int(RATE * GAP_SECONDS)
    slot_n = gap_n * 2 + tone_n
    fade = np.hanning(tone_n)
    t = np.arange(tone_n) / RATE
    total_n = slot_n * len(POSITIONS)
    chans = []
    for i, pos in enumerate(POSITIONS):
        f = FREQUENCIES[pos]
        s = np.concatenate([np.zeros(gap_n), AMPLITUDE * np.sin(2 * np.pi * f * t) * fade,
                            np.zeros(gap_n)])
        track = np.zeros(total_n)
        track[i * slot_n: i * slot_n + slot_n] = s
        chans.append(track)
    interleaved = np.stack(chans, axis=1).ravel()  # (frames, 8) -> interleaved
    pcm = (np.clip(interleaved, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(8)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return total_n / RATE


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def play_and_record(wav_path, play_target, record_target, out_wav):
    """Play wav into play_target while recording record_target; return samples.

    Capture uses ffmpeg's pulse client on the sink monitor: pw-record's
    --target silently fell back to the default source on this setup, while
    ffmpeg -f pulse captures the monitor reliably.
    """
    dur = PRE_ROLL + wav_seconds(wav_path) + POST_ROLL + 0.3
    rec = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-f", "pulse", "-i", record_target,
         "-acodec", "pcm_s16le", "-ar", str(RATE), "-ac", "2",
         "-t", f"{dur:.2f}", "-y", out_wav],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=True)
    time.sleep(PRE_ROLL)
    try:
        # NB: no --channels here; pw-cat must take the file's 8ch layout
        run(["pw-cat", "--playback", "--target", play_target, wav_path])
    except subprocess.CalledProcessError as e:
        rec.terminate()
        rec.wait()
        sys.exit(f"playback failed: {e.stderr.strip()}")
    _, err = rec.communicate(timeout=dur + 10)
    if rec.returncode != 0:
        sys.exit(f"monitor capture failed: {(err or '').strip()}")

    with wave.open(out_wav, "rb") as w:
        assert w.getnchannels() == 2 and w.getframerate() == RATE, \
            f"unexpected capture format: {w.getnchannels()}ch {w.getframerate()}Hz"
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return data.reshape(-1, 2)


def analyse(rec):
    """Per-time-slot analysis: channel i owns slot i, so attribution cannot
    be confused by routing, harmonics, or frequency collisions. Within each
    slot, measure the slot's tone: presence (SNR), level difference (pan)
    and interaural phase delay (ITD)."""
    slot = int(RATE * (GAP_SECONDS * 2 + TONE_SECONDS))
    core = int(RATE * TONE_SECONDS)
    start0 = int(RATE * PRE_ROLL)
    rows = []
    for i, pos in enumerate(POSITIONS):
        f = FREQUENCIES[pos]
        seg = rec[start0 + i * slot + int(RATE * GAP_SECONDS):
                  start0 + i * slot + int(RATE * GAP_SECONDS) + core]
        if len(seg) < core // 2:
            rows.append({"pos": pos, "freq": f, "snr": -99, "pan": 0.0,
                         "itd": 0.0, "present": False, "side": "?", "ok": False})
            continue
        n_fft = 1 << 14
        win = np.hanning(n_fft)
        step = n_fft // 2
        n_bins = n_fft // 2 + 1
        accL = np.zeros(n_bins, dtype=complex)
        accR = np.zeros(n_bins, dtype=complex)
        done = 0
        for j in range(0, len(seg) - n_fft, step):
            accL += np.fft.rfft(seg[j:j + n_fft, 0] * win)
            accR += np.fft.rfft(seg[j:j + n_fft, 1] * win)
            done += 1
        XL, XR = accL / done, accR / done
        magL, magR = np.abs(XL), np.abs(XR)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / RATE)
        band = (freqs > f - 25) & (freqs < f + 25)
        floor_band = (freqs > 30) & (freqs < 4000) & ~band
        k = int(np.argmax(magL[band] + magR[band]))
        fL, fR = XL[band][k], XR[band][k]
        mL, mR = abs(fL), abs(fR)
        floor = max(np.median(magL[floor_band]), np.median(magR[floor_band])) + 1e-12
        snr = 20 * math.log10(max(mL, mR) / floor)
        pan = 10 * math.log10((mR + 1e-12) / (mL + 1e-12))
        # interaural time difference from the tone's interaural phase
        dphi = np.angle(fR * np.conj(fL))
        itd_ms = dphi / (2 * np.pi * f) * 1000.0
        present = snr >= PRESENCE_SNR_DB
        if pos in ("FC", "LFE"):
            # LFE is folded into the center taps; the IR's fine structure
            # gives it a small legitimate asymmetry (see CENTER_* bounds)
            ok = present and (abs(itd_ms) < CENTER_ITD_MS
                              and abs(pan) < CENTER_PAN_DB)
            side = "C"
        else:
            want = PAN_EXPECT[pos]
            ild_side = "L" if pan < -PAN_DB_TOL else ("R" if pan > PAN_DB_TOL else "C")
            itd_side = "L" if itd_ms < -ITD_MS_TOL else ("R" if itd_ms > ITD_MS_TOL else "C")
            ok = present and (ild_side == want or itd_side == want)
            side = itd_side if itd_side != "C" else ild_side
        rows.append({"pos": pos, "freq": f, "snr": snr, "pan": pan,
                     "itd": itd_ms, "present": present, "side": side,
                     "ok": ok})
    return rows


def print_table(title, rows, strict):
    print(f"\n{title}")
    print(f"  {'ch':<5}{'tone':>7}{'SNR':>8}{'pan L<- ->R':>13}{'ITD':>10}"
          f"{'heard':>8}  verdict")
    for r in rows:
        heard = "yes" if r["present"] else "NO"
        if not r["present"]:
            verdict = "FAIL (absent)"
        elif not strict:
            verdict = "present"
        elif r["ok"]:
            verdict = "PASS"
        else:
            verdict = (f"FAIL (positioned {r['side']}, "
                       f"want {PAN_EXPECT[r['pos']]})")
        print(f"  {r['pos']:<5}{r['freq']:>6.0f}Hz{r['snr']:>7.1f}dB"
              f"{r['pan']:>+12.1f}dB{r['itd']:>+9.2f}ms{heard:>8}  {verdict}")


def resolve_record_target():
    """Prefer the GSA 70 Game monitor; fall back to the surround sink monitor."""
    out = subprocess.run(["pactl", "list", "short", "sources"],
                         capture_output=True, text=True).stdout
    names = [row.split("\t")[1] for row in out.splitlines() if row.strip()]
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required for monitor capture (pacman -S ffmpeg)")
    if f"{GSA_GAME}.monitor" in names:
        return f"{GSA_GAME}.monitor", "GSA 70 Game (headset input)"
    if f"{SURROUND_SINK}.monitor" in names:
        return f"{SURROUND_SINK}.monitor", f"{SURROUND_SINK} monitor"
    sys.exit("No capture target found: neither the GSA 70 monitor nor "
             f"{SURROUND_SINK} exist. Run scripts/setup-virtual-surround.sh")


def cmd_test(sink, do_ab, workdir):
    if not sink_exists(sink):
        sys.exit(f"Sink '{sink}' not found. Run scripts/setup-virtual-surround.sh first.")
    record_target, rt_label = resolve_record_target()
    wav = os.path.join(workdir, "surround_test_8ch.wav")

    print(f"Sink under test: {sink}")
    print(f"Recording from:  {rt_label}")
    dur = generate_test_wav(wav)
    print(f"Playing {dur:.1f}s of per-channel tones...")

    rows = analyse(play_and_record(wav, sink, record_target,
                                   os.path.join(workdir, "rec_surround.wav")))
    print_table(f"== {sink} (HRTF filter-chain) ==", rows, strict=True)
    passed = sum(r["ok"] for r in rows)
    if passed == len(rows):
        print(f"\nVERDICT: SURROUND VERIFIED — {passed}/{len(rows)} channels "
              "reach the headset with correct positioning.")
    else:
        print(f"\nVERDICT: FAIL — only {passed}/{len(rows)} channels verified.")
        if all(not r["present"] for r in rows):
            print("No tones reached the recording target at all: check the "
                  "sink's node.target routing and that the headset is linked.")

    if not do_ab:
        return
    if not sink_exists(GSA_GAME):
        print(f"(A/B skipped: {GSA_GAME} not found)")
        return
    print("\n--- control run: same tones straight into the raw stereo "
          "GSA 70 sink (no HRTF) ---")
    ab_rows = analyse(play_and_record(wav, GSA_GAME, record_target,
                                      os.path.join(workdir, "rec_stereo.wav")))
    print_table(f"== {GSA_GAME} (plain stereo downmix) ==", ab_rows, strict=False)
    print("\nInterpretation: with a plain downmix every channel is still "
          "audible, but surrounds are as loud as fronts and arrive without "
          "the HRTF's attenuation/delay. Compare the pan and level columns "
          "of the two tables — differences there are what your ears "
          "perceive as 'surround'.")


def set_default_sink():
    out = subprocess.run(["wpctl", "status"], capture_output=True, text=True).stdout
    import re
    m = re.search(r"^\s+(\d+)\. GSP670_Surround\b", out, re.M)
    if not m:
        sys.exit("GSP670_Surround sink not found; cannot set default.")
    run(["wpctl", "set-default", m.group(1)])
    print(f"[ok] GSP670_Surround (id {m.group(1)}) is now the default sink")


def cmd_listen(set_default):
    if not sink_exists(SURROUND_SINK):
        sys.exit(f"Sink '{SURROUND_SINK}' not found. Run scripts/setup-virtual-surround.sh first.")
    if set_default:
        set_default_sink()
    else:
        print("Tip: route this test to the surround sink, e.g. "
              f"'python3 {os.path.abspath(__file__)} --listen --set-default', "
              "or set GSP670_Surround as default with wpctl.")
    if not shutil.which("speaker-test"):
        sys.exit("speaker-test not found (pacman -S alsa-utils)")
    print("Listen: each spoken position should sound from a distinct "
          "direction — 'rear right' clearly behind you. Ctrl+C to stop.\n")
    subprocess.run(["speaker-test", "-D", "pipewire", "-c", "8", "-t", "wav"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--test", action="store_true", help="verify surround path (default)")
    mode.add_argument("--generate", metavar="FILE", help="write 8-ch test WAV and exit")
    mode.add_argument("--ab", action="store_true",
                      help="verify surround path, plus a control run against the raw stereo sink")
    mode.add_argument("--listen", action="store_true",
                      help="subjective speaker-test through the surround sink")
    ap.add_argument("--set-default", action="store_true",
                    help="with --listen: make GSP670_Surround the default sink")
    ap.add_argument("--sink", default=SURROUND_SINK, help="surround sink name")
    args = ap.parse_args()

    if args.generate:
        dur = generate_test_wav(args.generate)
        print(f"wrote {args.generate} ({dur:.1f}s, 8ch {RATE}Hz)")
        return
    if args.listen:
        cmd_listen(args.set_default)
        return
    with tempfile.TemporaryDirectory(prefix="gsp670-surround-") as workdir:
        cmd_test(args.sink, do_ab=args.ab, workdir=workdir)


if __name__ == "__main__":
    main()
