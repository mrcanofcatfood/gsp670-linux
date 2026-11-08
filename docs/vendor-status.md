# Vendor status

What happened to EPOS's gaming division, what still exists, and why that
matters for Linux users of the GSP 670 and GSA 70.

This is the authoritative account. Everything below is dated and sourced, so
it can be checked rather than taken on trust.

---

## Summary

> EPOS Gaming was wound down by its parent company, Demant, in September 2023.
> The entire staff was laid off and the gaming headset line was gradually
> discontinued. EPOS continues as an **enterprise** audio business; the gaming
> products survive only as remaining stock and legacy support pages.
>
> That left the GSP 670 and GSA 70 with no vendor software for anything but
> Windows. The EPOS Gaming Suite has never had a Linux version, and nobody is
> going to write one now. There is also no route to a firmware update: the
> devices already run the final firmware, so the dongle's ~1.4-second audio
> latency bug will never be fixed by the vendor.

## Timeline

| When | What happened |
|---|---|
| **2018** | The Sennheiser gaming joint venture is sold to **Demant**, a hearing-aid company, and becomes EPOS Gaming. |
| **March 2020** | Sennheiser ends the joint venture with EPOS. EPOS carries the gaming line under its own brand. |
| **2023-09-01** | EPOS Gaming lays off its **entire staff** and announces it will wind down. EPOS Gaming president Jeppe Dalberg-Larsen: *"We will be moving ahead with a gradual wind-down of the Gaming headset portfolio, meaning we will continue to sell our products during 2024 and our customer support will remain unchanged. This change will not impact warranty on our products."* |
| **2024** | Remaining stock is sold through partner resellers. No new gaming headset models are released. |
| **Present** | EPOS continues as an enterprise-audio business (headsets for call centres and conferencing). The gaming support pages remain online and are still maintained. |

Sources: [Dexerto, 2023-09-11](https://www.dexerto.com/tech/epos-gaming-updates-customers-after-shutting-doors-laying-off-all-staff-2288653/),
[PC Gamer](https://www.pcgamer.com/epos-gaming-to-wind-down-but-all-employees-have-already-lost-their-jobs/),
[Esports Insider, 2023-09](https://esportsinsider.com/2023/09/esports-audio-brand-epos-gaming-shuts-down),
[Vortez, 2023-12-02](https://www.vortez.net/epos_gaming_discretely_exits_gaming_headset_market/).

## What still exists

- **The EPOS Gaming Suite for Windows** is still downloadable, and the
  firmware-update procedure still works. It is Windows-only.
- **The support knowledge base** is live and still being edited — the GSP 670
  articles were last modified in September 2026.
- **Warranty coverage** was explicitly unaffected.
- **The devices themselves** work fine; they are not bricked or disabled.

## What does not exist

- **Any Linux support.** The Gaming Suite was Windows-only and there is no
  Linux version, and there never will be one now.
- **Any new gaming hardware** under the EPOS brand.
- **A firmware update that fixes the known bugs.** The devices already run
  the final firmware (dongle 3.3.43, headset 3.2.6), and no corrected
  image exists. This is why the dongle's ~1.4-second audio latency can never
  be fixed — see [limitations.md](limitations.md) §1.
- **A successor to the Gaming Suite** for these devices.

## Why this matters on Linux

Three concrete consequences:

1. **No vendor Linux support will ever exist.** Nobody is going to write a
   Linux driver, so the audio path, the chat/game mixer and the device
   controls have to be maintained by the community.
2. **The dongle's latency bug is permanent.** With no firmware update
   possible, the ~1.4-second wireless latency stays. The wired Micro-USB
   connection is the only low-latency option.
3. **The device's controls are undocumented by the vendor.** Sidetone, noise
   reduction and the auto-power-off timer work over the device's own HID
   interface, but no vendor documentation describes how to reach them from
   Linux.

Interestingly, the **audio** path needs none of the vendor's software. The
kernel's USB audio driver and the stock `usb-gaming-headset.conf` ALSA profile
set already expose the headset's stereo "Game" and mono "Chat" outputs. What
is missing is polish and the device controls — which is what this project
provides.

## Getting the EPOS Gaming Suite

If you want the vendor's Windows software — for example to update firmware or
to use the EPOS EQ presets on Windows — here is where it lives.

> **Note on links:** EPOS moved its gaming section off the main site onto a
> separate host when it wound the division down. Older EPOS support articles
> still link to the old paths, and those links are now dead. The URLs below
> were verified working.

### Live links

EPOS's gaming pages are now served from a separate host:

| What | URL |
|---|---|
| Gaming Suite download page | `https://demant-epi.eposaudio.com/en/us/gaming/gaming-downloads` |
| Gaming support centre | `https://demant-epi.eposaudio.com/en/us/gaming/support` |
| Product support articles | `https://demant-epi.eposaudio.com/en/us/gaming/support/knowledge-base` |
| Gaming Suite FAQ (PDF) | `https://demant-epi.eposaudio.com/globalassets/blocks/gaming/gaming-suite/epos-gaming-suite_faq.pdf` |

The same paths work for other locales — replace `en/us` with `en/gb`, `en/de`,
`en/au`, `en/sg`, `it/it`, `en/jp` and so on.

**Two rules that decide whether a link works:**

- **Page paths take a locale prefix; asset paths do not.** So
  `.../en/au/gaming/gaming-downloads` is right, but
  `.../en/au/globalassets/...` is not.
- **The assets are served from the `demant-epi` host only.** The same paths
  on `www.eposaudio.com` return 404.

### Archive links (durable)

EPOS has already moved this hosting once, and in the process broke the links
in its own documentation. The Internet Archive's copies will not rot:

| What | URL |
|---|---|
| Download page (AU) | `https://web.archive.org/web/20240803225619/https://www.eposaudio.com/en/au/gaming/gaming-downloads` |
| Download page (US) | `https://web.archive.org/web/20260922201830/https://www.eposaudio.com/en/us/gaming/gaming-downloads` |
| Gaming Suite MSI | `https://web.archive.org/web/20260115085911id_/https://www.eposaudio.com/globalassets/__pim/products/gaming-software/epos-gaming-suite/25b0aae0-b019-413d-ad88-8fb5c7d74b8b_42614_eposgamingsuite_original.msi` |
| Gaming Suite FAQ (PDF) | `https://web.archive.org/web/20260922201835/https://www.eposaudio.com/globalassets/blocks/gaming/gaming-suite/epos-gaming-suite_faq.pdf` |

The archived download page carries EPOS's own wind-down notice, and its
download link resolves to the archived installer. The `id_` suffix on the MSI
URL serves the raw file rather than the Archive's viewer page.

**About the installer:** version `42614`, dated 26 May 2023, 18.7 MB. The
archived copy has been verified byte-for-byte against EPOS's live file.

> This repository **links** to the installer but does not bundle it. The
> EPOS Gaming Suite is proprietary and is not redistributed here — see
> [legal.md](legal.md).

## A note on wording

Two statements are both true, and it is worth keeping them apart:

- *"EPOS still maintains the Gaming Suite and the support pages."* — yes.
- *"EPOS no longer supports the GSP 670."* — also yes.

The wind-down was of the **gaming product line and its development**, not a
withdrawal of support for hardware already sold. This project concerns the
second: there is no Linux support, and there will not be any.

## See also

- [limitations.md](limitations.md) — what the hardware itself cannot do
- [legal.md](legal.md) — the legal position and the provenance policy
- [install.md](install.md) — setting the headset up on Linux
