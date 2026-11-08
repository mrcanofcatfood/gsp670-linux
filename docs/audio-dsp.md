# Audio DSP: Device vs. Host

The GSP 670's "features" fall into **two different layers**. Keeping them
straight is the whole point of this document.

| Layer | Who runs it | Examples | How to control it on Linux |
|---|---|---|---|
| **Device DSP** | The GSP 670 / GSA 70 firmware | sidetone, noise reduction | This project's CLI / D-Bus / panel (SECOM) |
| **Host DSP** | Software on the PC | speaker & mic EQ, reverb, surround, voice enhancer, noise gate, high-pass, volume | PipeWire — normally via **EasyEffects** |

On Windows, the EPOS Gaming Suite implements the host layer as an *audio
processing object* (APO) in the Windows audio pipeline. Those are **not
SECOM/HID device commands** — the `gsp670` library intentionally makes
`set_volume()`, `set_mic_gain()` and `set_reverb()` no-ops for exactly this
reason. There is nothing to reverse-engineer: the hardware has no such
registers. Volume is a USB Audio Class control handled by ALSA/PipeWire.

So this project **does not** reimplement EQ/reverb/surround. It controls the
device layer, and delegates the host layer to PipeWire.

## Why EasyEffects

EasyEffects is a front-end to PipeWire's `filter-chain` module — it builds the
same kind of DSP graph you could write by hand, using the same plugin kernels.
It is not a quality compromise; it is the convenient harness.

Quality ranking for the host layer:

1. **LSP plugins** (via EasyEffects or a hand-written filter-chain) — pro-grade,
   oversampled filters. This is the ceiling.
2. PipeWire built-in filter-chain DSP — good (biquad EQ, convolver); no extra deps.
3. EPOS APO presets — fixed 9-band EQ + simple reverb. Convenient, not higher quality.

Useful native reference configs shipped with PipeWire:
`/usr/share/pipewire/filter-chain/sink-eq6.conf`,
`sink-dolby-surround.conf`, `sink-dolby-pro-logic-ii.conf`.

## Install

```bash
sudo pacman -S easyeffects lsp-plugins-lv2 lsp-plugins-vst3
```

## GSP 670 presets

`contrib/easyeffects/` contains starting-point presets:

```
contrib/easyeffects/output/GSP 670.json   # speaker EQ  (10-band)
contrib/easyeffects/input/GSP 670.json     # microphone EQ (10-band)
```

Install them into the user preset directory:

```bash
install -Dm644 "contrib/easyeffects/output/GSP 670.json" \
    ~/.local/share/easyeffects/output/"GSP 670.json"
install -Dm644 "contrib/easyeffects/input/GSP 670.json" \
    ~/.local/share/easyeffects/input/"GSP 670.json"
```

Then launch EasyEffects, load the **GSP 670** preset on the output and input
pipelines, and (optionally) set it to **autoload** when the GSA 70 device
appears.

> The shipped curves are conservative, *heuristic* starting points — not
> measured corrections for this headset. Tune them (or import a community
> preset) to taste.
>
> Replace **EQ/reverb/surround** with EasyEffects rather than expecting the
> dongle to provide them. The device has no such controls.

## Latency / quality notes

- Stay at the headset's native **48 kHz** to avoid resampling.
- A PipeWire quantum of **256–512** is a good latency/stability balance.
- Prefer a **convolver** (impulse response) for surround/HRTF over toy algorithms.
- Don't stack redundant processing (e.g. two EQs).
