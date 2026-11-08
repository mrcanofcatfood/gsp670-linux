# Virtual Surround for GSP 670

The GSP 670 has no SECOM device opcode for 7.1 surround. True 7.1
virtualization requires a head-related transfer function (HRTF) and channel
routing — this lives entirely in host DSP.

## This is now implemented and verified

See **[`docs/virtual-surround.md`](../../docs/virtual-surround.md)** for the
full setup and verification guide. Short version:

```bash
scripts/setup-virtual-surround.sh --persist     # IR + PipeWire drop-in
systemctl --user restart pipewire wireplumber
python3 scripts/surround_verify.py --test       # objective 8/8 per-channel check
```

The EasyEffects presets in this directory are **EQ/limiter chains only** — an
EasyEffects preset cannot produce surround, because its sink is stereo and
EasyEffects has no 7.1 upmix/HRTF stage. The earlier
`output-virtual7.1/GSP670-7.1-HRTF.json` skeleton and the preset formerly
named "7.1 Virtual Surround" (now `GSP 670 - Warm.json`) never did surround;
they are EQ starting points.

## Why not baked into the device?

SECOM opcode analysis (`docs/verified-secom-opcodes.md`) shows no
surround/3D/DirectSound opcode. The Windows "7.1" button was backed by the
proprietary Windows APO, not the dongle. On Linux we delegate this honestly
to a PipeWire filter-chain.
