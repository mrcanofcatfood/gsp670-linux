# GSP 670 EasyEffects Presets

These presets are for EasyEffects 8.x (PipeWire/LSP audio processing).
The GSP 670 dongle has no SECOM opcode for EQ, reverb, surround, or voice
processing — all of that lives in host DSP on Linux, delegated honestly to
EasyEffects.

## Installation

Presets are loaded by EasyEffects directly from `~/.local/share/easyeffects/`:

```bash
cp contrib/easyeffects/output/*.json ~/.local/share/easyeffects/output/
cp contrib/easyeffects/input/*.json  ~/.local/share/easyeffects/input/
```

Then in EasyEffects, select the preset from the pipeline view.

## Output Presets

### GSP 670 - Flat
Clean reference curve: 10-band EQ at unity gain + output limiter.
Use as a starting point for building your own sound.

### GSP 670 - Gaming
EQ gaming curve + output limiter. Good all-round gaming preset:
- Tasteful EQ boost at highs and lows for spatial awareness
- Limiter prevents clipping during loud game audio

### GSP 670 - Warm
EQ warmth curve + output limiter. For games that benefit from a
slightly different EQ tuning. (Formerly mislabelled "7.1 Virtual Surround" —
EQ presets cannot produce surround; see `docs/virtual-surround.md` for the
real, verified virtual surround sink.)

### GSP 670 (Legacy)
Legacy output EQ curve + limiter. Maintained for compatibility.

## Input Presets

### GSP 670 - Voice
Voice-chat optimized mic processing chain:
- **EQ**: slight low-mid boost for warmth, high-shelf cut reduces harshness
- **Gate**: **bypassed by default**. The gate is included but disabled, because
  an aggressive gate makes Discord (and other VoIP clients) report *"No audio
  input detected"* — it closes on quiet input and the client reads that as a
  dead mic. If you re-enable it, the shipped thresholds are relaxed
  (−55 dB / −60 dB hysteresis, 12 dB reduction) and stereo-split is off for the
  mono source.
- **Limiter**: output protection at 0dB

> **Voice chat and EasyEffects:** if EasyEffects is running it inserts
> `easyeffects_sink` / `easyeffects_source` between apps and the hardware. That
> is fine for music, but for voice chat prefer routing the client (Discord,
> etc.) straight to the hardware `...stereo-game` / `...mono-chat` nodes and out
> of the DSP chain. See `docs/troubleshooting.md` § *Discord / Voice Chat*.

## Plugin Notes

- All presets use **LSP plugins** (`lsp-plugins-lv2` package). Install with:
  ```bash
  sudo pacman -S lsp-plugins-lv2 lsp-plugins-vst3
  ```
- EasyEffects automatically discovers LSP plugins; no extra configuration.
- These presets are EQ/limiter chains only — they do not do surround. Real
  virtual 7.1 lives in the PipeWire filter-chain sink (`contrib/pipewire/`,
  `docs/virtual-surround.md`).

## Preset Details

All presets use the LSP sc_limiter_stereo plugin as the output limiter with:
- Mode: "Line Wide" (transparent limiting)
- ALR (Adaptive Loudness Routing) enabled for consistent output levels
- Threshold: 0dB (maximum headroom)
- Release: 5ms (fast enough to not audibly distort)

The input Voice preset uses LSP sc_gate_stereo for noise gating.
