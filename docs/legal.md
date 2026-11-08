# Legal position

This document explains the legal posture of `gsp670-linux`: what the project
does, what it deliberately does not contain, and why.

> **This is not legal advice.** It is the maintainers' understanding of their
> own position, written down so that reviewers and users can see the
> reasoning. Anyone redistributing this software, or operating it in a
> particular jurisdiction, should take their own advice for their situation.

## Summary

| | |
|---|---|
| **What this is** | A Linux driver and setup tooling for the EPOS\|Sennheiser GSP 670 headset and GSA 70 dongle |
| **Who it is for** | People who own the hardware and want it to work on Linux |
| **Does it redistribute any vendor material?** | **No** — no binaries, no firmware, no vendor data, no captures |
| **Does it circumvent any protection measure?** | **No** — the device protocol has no encryption, no access control, no licence validation and no authentication |
| **Is it affiliated with EPOS or Sennheiser?** | **No** |
| **Licence** | MIT (see [LICENSE](../LICENSE)) |

## What the project actually is

`gsp670-linux` is interoperability software. It lets Linux talk to a piece of
hardware the user already owns, in the same way that a Linux network driver
lets Linux talk to a network card.

Most of the project's value is in **audio**, and that part involves no
reverse engineering whatsoever:

- The kernel's stock `snd-usb-audio` driver creates the ALSA card.
- The stock `usb-gaming-headset.conf` ALSA profile set — which ships with
  PulseAudio and is read by PipeWire through the ALSA configuration API —
  provides the "Game" (stereo) and "Chat" (mono) outputs and the microphone.
- This project adds udev rules, a systemd audio guard, and a WirePlumber
  configuration that fixes a suspend/resume race on this particular USB
  device. See [install.md](install.md).

None of that involves the vendor's proprietary software.

The optional Python library adds access to a handful of hardware features
that the OS mixer cannot reach: sidetone, noise reduction, the auto-power-off
timer, device identity readback, and device event notifications. That part
speaks the device's own HID protocol, which is documented in
[protocol-reference.md](protocol-reference.md) and
[verified-secom-opcodes.md](verified-secom-opcodes.md).

## No proprietary material is distributed

This repository contains **none** of the following:

| Not included | Why |
|---|---|
| EPOS Gaming Suite installer, DLLs, or decompiled output | proprietary; not redistributable |
| Device firmware images | proprietary; not needed |
| USB traffic captures | may embed copyrighted firmware |
| Windows virtual-machine images | research artefacts only; not needed |
| The HeSuVi head-related impulse response | third-party; fetched from its own upstream project on demand, with a SHA-256 pin, under its own licence |

The impulse response used by the optional virtual-surround feature is
**downloaded** by `scripts/setup-virtual-surround.sh` from the
[HeSuVi project](https://sourceforge.net/projects/hesuvi/) at the user's
request. It is not committed to this repository.

`scripts/check-provenance.sh` enforces this mechanically. It runs in CI as a
**required** check and fails the build if a tracked file matches a forbidden
pattern — a binary extension, an oversized file, a vendor code address, an
internal symbol name, a disassembly listing, or a licence-key artefact. See
[Provenance policy](#provenance-policy) below.

## No circumvention

This is the most important point, so it is worth being precise about it.

A "technological protection measure" (TPM) is, in substance, technology that
effectively controls access to a copyright work, or that restricts the
exercise of a copyright owner's rights. The anti-circumvention provisions in
both the Australian and US copyright statutes (and in EU law) bite on
*circumventing* such a measure, and on *supplying a device* whose only
significant commercial purpose is to do so.

**The GSP 670 / GSA 70 control protocol contains no such measure.** Verified
directly against the code in this repository:

- **No encryption, decryption, cipher or obfuscation.** No cryptographic
  library is imported anywhere in `src/`, `scripts/` or `tests/`.
- **No access control.** Every command is a plain HID report; there is no key
  exchange, no challenge, no session token.
- **No licence or activation validation.** The device does not check whether
  the host is licensed, and there is nothing for it to check.
- **No authentication.** The device answers identity and status queries on a
  plain read, with no prior handshake.
- The **CRC-8** on each frame is an *integrity check* — it detects a
  corrupted packet. It is not a protection measure, and it is not keyed.
- The firmware-update command is rejected by the device's own firmware
  level, and no fixed firmware image is redistributed or required. This
  project does not attempt to bypass that gate, and does not ship tooling
  that could.

So there is **nothing to circumvent**. The anti-circumvention provisions are
not engaged by anything this project does. This is categorically different
from, for example, extracting keys from a copy-protection scheme or
neutralising an activation check.

## Interoperability exceptions, and why they are not needed here

Because the project involves reverse engineering of a proprietary protocol,
it is worth recording where the interoperability exceptions sit — and, just
as importantly, recording that **this project does not rely on any of them**.

| Jurisdiction | Provision | Applies to |
|---|---|---|
| Australia | *Copyright Act 1968* (Cth) s47D — "Reproducing computer programs to make interoperable products" | Reverse engineering to create an interoperable product |
| Australia | ss116AN–116AP (civil), ss132APC–132APE (criminal) | Circumventing a TPM; supplying a circumvention device |
| United States | 17 USC §1201(f) — "Reverse Engineering" | Circumvention for interoperability; developing and distributing the means |
| United States | 17 USC §1201(a), (b) | Circumventing a technological measure; trafficking in circumvention devices |
| European Union | Directive 2009/24/EC Art. 6 (InfoSoc) | Decompilation for interoperability |

If a protection measure were ever identified, the interoperability exception
in each of these jurisdictions would be the relevant framework: they each
permit reverse engineering to create an interoperable product, and each
disapplies the trafficking provisions for means "necessary to achieve such
interoperability".

**But that contingency does not arise here.** As set out above, the device
protocol has no protection measure, so no exception needs to be invoked, and
no statutory condition needs to be satisfied. The project is safer by
construction than by relying on an exception.

## Hosting on GitHub

This project is hosted on GitHub, so two GitHub-specific points are worth
recording.

**GitHub's circumvention-claim review.** GitHub's DMCA Takedown Policy
describes a separate, more intensive review track for circumvention claims,
conducted by both technical and legal reviewers. A claimant is required to
state (1) what the technical measures are, (2) how they effectively control
access, and (3) how the accused project circumvents them. GitHub also states
that where it cannot determine that a claim is valid it will "err on the side
of the developer, and leave the content up", and that it offers repository
owners a referral to independent legal consultation through its Developer
Defense Fund.

For this project, requirement (2) is unsatisfiable: there is no measure that
controls access to anything, because there is no encryption, no access
control and no licence validation. GitHub's policy separately notes that its
circumvention review does not extend to content concerning product licensing
keys or activation checks — which this project also does not touch.

**Fork handling.** GitHub does not automatically disable forks when it
disables a parent repository, and it expects a rights holder to investigate
forks explicitly. The maintainer's separate private research workbench is
therefore never published.

## Provenance policy

The maintainers follow one rule for anything derived from the study of
closed-source software:

**Published:** the *interface* — the wire format, the opcode numbers and
their payloads, the event names and their layouts, and behavioural
descriptions of how the device responds. This is what interoperability
requires, and it is the project's legitimate output.

**Not published:** the vendor's *implementation* — binary data, decompiled
source, vendor executables, USB captures, disassembly listings, internal
symbol names, and code addresses from the vendor's binaries.

Detailed analysis of the vendor's proprietary software is kept in the
maintainer's private workbench and is deliberately not part of this
repository. See [analysis/README.md](analysis/README.md) for the high-level
summary of what was learned and how.

The boundary is enforced by `scripts/check-provenance.sh`:

```bash
./scripts/check-provenance.sh
```

It inspects **tracked files only**, so it cannot be affected by local
artefacts, and it fails on:

- vendor binary extensions (`.msi`, `.exe`, `.dll`, `.so`, `.qcow2`,
  `.pcap`, …)
- any tracked file larger than 256 KiB
- vendor code addresses (`0x00…` with six hex digits)
- internal symbol names (`FUN_…`)
- disassembly listings in the documentation
- licence-key and private-key artefacts

A small allow-list exists so that this document and the provenance policy can
*discuss* these patterns without tripping the check.

## Trademarks

EPOS, Sennheiser, GSP 670 and GSA 70 are trademarks of their respective
owners. They are used here **nominatively**, to identify the hardware this
project supports. This project is an independent effort and is **not
affiliated with, endorsed by, or sponsored by** EPOS or Sennheiser.

The MIT licence in [LICENSE](../LICENSE) covers this project's own work only.
It grants no rights in any EPOS or Sennheiser trademark, firmware, or
software.

## Why publish this document

Two reasons:

1. **It lets a reviewer check the claims rather than take them on trust.**
   Every statement above is verifiable against the code in this repository.
2. **It makes the maintainers' obligations explicit**, so that future
   contributions can be checked against a stated boundary rather than
   negotiated case by case. If you are considering a contribution that
   would include vendor-internal detail, please read
   [analysis/README.md](analysis/README.md) first — the answer is usually
   that it belongs in the private workbench, not here.

## See also

- [analysis/README.md](analysis/README.md) — high-level summary of the
  protocol findings and the method used
- [protocol-reference.md](protocol-reference.md) — the wire format
- [verified-secom-opcodes.md](verified-secom-opcodes.md) — the opcode table
- [limitations.md](limitations.md) — what the hardware cannot do
- [LICENSE](../LICENSE) — the MIT licence and the third-party note
