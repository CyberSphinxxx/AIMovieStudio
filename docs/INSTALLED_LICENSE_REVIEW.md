# Installed dependency and notice review — 2026-10-13

Status: **INVENTORY_ONLY_NOT_CLEARED**. Private workstation development continues; redistribution and a production release remain unreviewed. This report records installed declarations and notice hashes, including development tools. It is not a complete binary SBOM or a determination of rights to models, voices, outputs, codecs or application source.

Run the offline inventory:

```powershell
.venv/Scripts/python.exe -m scripts.license_inventory
```

The output is `ops/evidence/installed-license-inventory.json`:49 main Python packages,161 isolated GPU Python packages and209 installed frontend packages,516 hashed notice/card files and81 findings. Twenty packages have no notice found by the scanner; two lack a compact declaration (llvmlite and tiktoken). These are metadata gaps, not proof of infringement. Other findings include absent optional packages for other operating systems, pending binary/model review and source mapping. Paths are relative; direct download credentials, authors and emails are omitted. The script reads metadata without importing package code, executing GPU libraries, downloading dependencies or contacting any network. Missing/redirected/oversized notice files and lock mismatches are explicit findings. Notice hashes permit later comparison; this does not vendor all texts for a release bundle.

Small model/license source capture is separate and network-enabled:

```powershell
.venv/Scripts/python.exe -m scripts.capture_license_sources
```

It retrieves only public metadata, model cards and license texts for the installed approved image/writing components plus llama.cpp b11558. No weights, logins or terms acceptance. Each run reserves up to512KiB against the existing32GB ledger when present, charges received bodies on completion/failure, and retains conservative reservations if interrupted before completion. Copies use pinned revision filenames; different content at the same revision fails without overwriting its original. Latest source index is `ops/evidence/model-license-sources.json`. Earlier notices remain in `tools/licenses` (ignored by Git). This helper is serial developer tooling; do not run it concurrently with another download process.

Two actual captures received93,830 and103,414 bytes (197,244 total), preserved8 final source files, and updated the approved GPU ledger to11,383,894,606 received bytes plus existing5,632,458,939 reservations. This remains inside the approved32GB scope. No additional models or runtimes installed. Earlier capture index retained as `model-license-sources-first.json`.

| Component | Observed source | Remaining gate |
|---|---|---|
| Main Python/npm | Installed distribution/package declarations + license-file SHA256 |20 notice gaps,2 compact declaration gaps; distinguish dev/runtime and collect exact texts before any bundle |
| WanGP | Pinned6479db36 license text, Community License2.0 | Private-use scope only; monetized embedding/hosting and any required output credits need separate review; vendor security90 advisories remain |
| FFmpeg | Installed9.0.2 Gyan build reports `--enable-gpl --enable-version3 --enable-libx264`; local GPLv3 text | Linked libraries, exact corresponding sources/build notices and codec obligations remain unreviewed |
| Flux Klein4B | Upstream revisione7b7dc27f91deacad38e78976d1f2b499d76a294 card + LICENSE.md declare Apache2 | Converted model origin/changes must be mapped independently |
| Qwen3 4B / Qwen0.5B | Official pinned cards + Apache2 license files | Converted encoder provenance and notices remain distinct from the upstream text |
| Converted VAE | InstalledSHA868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3 differs from current Klein4B upstreamSHAca70d2202afe6415bdbcb8793ba8cd99fd159cfe6192381504d6c4d3036e0f04 | Serialization/conversion or a different source could explain it; exact origin remains unverified. Hash inequality alone does not identify a licensing problem |
| Conversion hosting | PinnedDeepBeepMeep/Flux2c976cb238dbf2bee48f0bd65eeb14c039cf45e03 card has generic Flux2-dev base and no separate license | Broad repository card cannot establish each individual file's rights |
| llama.cpp | SavedMIT notice at b11558 | Binary DLL/runtime dependency notices and exact source linkage still need inventory |
| Windows speech | Installed system voices | Voice/output redistribution and clean-account availability remain unreviewed |
| Application source | No root license selected | Choose rights/distribution terms before packaging; no license was assigned autonomously |

FFmpeg flags were captured by executing the installed binary's `-version`, retained in `ops/evidence/ffmpeg-license-build.txt`. [FFmpeg's official license page](https://ffmpeg.org/legal.html) explains that its enabled components affect licensing; the LGPL checklist is not a clearance for this GPL-enabled build. The actual pinned [WanGP license](https://github.com/deepbeepmeep/Wan2GP/blob/6479db36bdc2619a904a852bba9c2d78e1a83f82/LICENSE.txt), [Flux Klein4B card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) and [Qwen3 card](https://huggingface.co/Qwen/Qwen3-4B) were reread. Source URLs/revisions/SHA/received bytes accompany each captured file. No claim that license declarations establish6GB compatibility; no native inference was performed.

Verification: RuffPASS;10 inventory/capture tests +16 storage regressionsPASS2.21s, covering metadata-only scanning, missing/optional declarations, lock mismatch, path escape,2MBnotice ceiling, corrupted captured checksum,512KiB received-body cap, failure receipt, cumulative budget refusal before network, pinned-original preservation and external environment rejection. Tests use explicit synthetic license text; actual captures/inventory are recorded separately. Last RAM2.43GiB, still below the5GiB model guard.

Next: resolve per-file converted VAE/encoder/model provenance and notice gaps, enumerate binary build dependencies and separate release runtime from development tooling. Any distribution, upload or new restrictive-term acceptance still needs the documented approval. F8.03 remains in progress.
