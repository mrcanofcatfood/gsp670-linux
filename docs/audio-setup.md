# Audio setup

How to route the GSP 670 / GSA 70 correctly for games and voice chat.

## The two devices

The headset presents two audio paths, which the hardware's two volume knobs
control independently:

| Sink / source | Channels | Typical use |
|---|---|---|
| `EPOS GSA 70 Game` (or `GSP 670 Game`) | stereo | games, music, video |
| `EPOS GSA 70 Chat` (or `GSP 670 Chat`) | mono | voice chat output |
| microphone source (on the *Chat* device) | mono | your voice |

The exact node names come from the ALSA card and its interface numbers:

```
alsa_output.usb-Sennheiser_EPOS_GSA_70-00.stereo-game
alsa_output.usb-Sennheiser_EPOS_GSA_70-00.mono-chat
alsa_input.usb-Sennheiser_EPOS_GSA_70-00.mono-chat
```

Do not hardcode these in your own scripts — the `EPOS`/`Sennheiser` prefix
changes when the dongle firmware is rebranded. Match on `GSA_70` or `GSP_670`
instead.

## Verify the setup

```bash
wpctl status | grep -iE 'GSA 70|GSP 670'
```

Expected:

```
 ├─ Sinks:
 │      75. EPOS GSA 70 Chat                    [vol: 1.00]
 │  *   76. EPOS GSA 70 Game                    [vol: 1.00]
 │
 ├─ Sources:
 │  *   77. EPOS GSA 70 Chat                    [vol: 1.00]
```

If the Game sink is missing, you are on an old kernel — see
[limitations.md](limitations.md) §6.

## Set the defaults

```bash
# Game audio as the system default (stereo)
wpctl set-default "$(wpctl status | grep -oP '^\s+\K[0-9]+(?=\. EPOS GSA 70 Game)' | head -1)"

# Microphone from the Chat device
wpctl set-default "$(wpctl status | grep -oP '^\s+\K[0-9]+(?=\. EPOS GSA 70 Chat)' | head -1)"
```

## Discord (or any voice chat app)

Discord should use the **Chat** device for both input and output:

1. Discord → Settings → Voice & Video
2. **Input Device**: `EPOS GSA 70 Chat` (the microphone lives on the Chat device)
3. **Output Device**: `EPOS GSA 70 Chat`
4. **Input Mode**: *Voice Activity* or *Push to Talk* — leave *Automatic* off
5. **Input Sensitivity**: about 50 % is a good starting point; the headset
   already applies noise reduction

Leave the *Game* device as the system default so that music and game audio go
to the headset in stereo, while Discord's voice goes through the separate
mono path. This is exactly the arrangement the hardware's second volume knob
is for.

> On Linux, "Input Device" in Discord can also be set to the *monitor* of the
> Chat sink if the app insists on a playback device. Prefer the real capture
> source though.

## Per-app routing with WirePlumber

To send one app to the Chat sink and everything else to Game, use WirePlumber's
`metadata` rules. Create `~/.config/wireplumber/wireplumber.conf.d/51-gsp670-chat.conf`:

```lua
metadata.rules = [
  {
    matches = [
      { node.name = "sink_input.routing", node.name = "~discord" }
    ]
    actions = {
      change-node-target = {
        type = "custom",
        node.name = "<id-of-the-Chat-sink>",
      }
    }
  }
]
```

Get the sink id with:

```bash
wpctl status | grep 'Chat'
```

PipeWire's `wireplumber.conf` is written in Lua, whereas the `50-gsp670.conf`
file shipped by this project uses WirePlumber 0.5's SPA-JSON syntax. Both
formats are supported by current WirePlumber; check your version before
copying older snippets.

## Important: do not route voice chat through a host DSP sink

If you use EasyEffects or the virtual-surround sink, keep **voice chat on the
hardware nodes**. Routing Discord through `easyeffects_source` or
`GSP670_Surround` is a common cause of:

- Discord logging `[AVError] no-audio-input-detected`
- Discord's InputWatcher flapping `Silence: true` / `Silence: false`
- Starting one app's audio stopping another app's audio

The doctor script points this out explicitly:

```bash
./scripts/gsp670-audio-doctor.sh
```

Look at the "Host DSP stack" section — it lists any app streams currently
attached to a virtual node.

## Volume control

Three separate levels exist, and they multiply:

1. The **system mixer** level for the sink (`wpctl set-volume`).
2. The **headset's Game knob** — hardware volume for the Game path.
3. The **headset's Chat knob** — hardware volume for the Chat path.

Turning the Chat knob down does not affect game audio, and vice versa. This is
the intended behaviour, not a fault.

Useful commands:

```bash
wpctl get-volume @DEFAULT_AUDIO_SINK@
wpctl set-volume @DEFAULT_AUDIO_SINK@ 80%
wpctl set-mute @DEFAULT_AUDIO_SINK@ 0
```

## Microphone gain and noise reduction

The hardware's noise reduction is a device-side control:

```bash
gsp670 controls list
gsp670 controls set noise_reduction 5
```

Sidetone (monitoring your own voice in the headset) is also device-side:

```bash
gsp670 controls set sidetone 5   # 0-10
```

For software gain and per-app processing, use EasyEffects — but insert it on
the *microphone* path only, and keep Discord off the EasyEffects source unless
you specifically want that.

## Testing the microphone

```bash
# Record five seconds from the Chat device
parecord --device=alsa_input.usb-Sennheiser_EPOS_GSA_70-00.mono-chat \
         --format=s16le --rate=16000 --channels=1 test.wav

# Or with the CLI
gsp670 status
```

A flat waveform means the microphone is not picking anything up. Check that
the headset's mute/flip-to-mute is not engaged.

## Latency

The dongle adds ~1.4 s. Measure it if you want to confirm:

```bash
# Play a click and watch the timestamp difference
speaker-test -c 2 -t wav -l 1 test.wav
```

See [limitations.md](limitations.md) §1 — use the wired USB-C connection for
gaming.
