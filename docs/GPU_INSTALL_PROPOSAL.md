# GPU installation proposal — approved bounded private tests

The user approved this scope on 2026-10-12; see `ops/APPROVALS.md`. Source, isolated Python/runtime and selected image files have since been checksum-verified and installed. The first API smoke failed before inference because Windows Application Control blocked PyTorch's CUDA dependency. Video files remain gated. The original file set and ceilings below remain unchanged. This is a feasibility test, not a compatibility or cinematic quality claim.

Use an isolated app-owned `tools/wan-gp` installation of [WanGP](https://github.com/deepbeepmeep/Wan2GP), pinned to `6479db36bdc2619a904a852bba9c2d78e1a83f82`, with a separate Python 3.11 runtime and the documented PyTorch 2.10 CUDA 13.0 wheel family. Resolve and record exact dependency versions before installation. Do not install a system CUDA toolkit or driver. If prebuilt isolated dependencies cannot work, stop that branch and report it.

| Stage | Selected weights | Observed bytes |
|---|---|---:|
| Image | Flux.2 Klein 4B int8 | 4,072,546,826 |
| Image text encoder | Qwen3 4B int8 | 4,414,004,409 |
| Image VAE | Flux2 VAE | 336,211,292 |
| Video | Wan2.2 TI2V 5B int8 | 5,231,471,198 |
| Video text encoder | UMT5 XXL int8 | 6,733,337,738 |
| Video VAE | Wan2.2 VAE requested by official handler | 2,818,780,191 |
| Tokenizers/configuration | Official handler file lists | 37,341,581 |
| **Total models/configuration** | | **23,643,693,235 (~22.02 GiB)** |

The versioned URLs, revisions and available hosting checksums are recorded in `ops/evidence/gpu-download-proposal.json`. File lists come from the official WanGP Flux and Wan handlers. Runtime dependencies add several GB; they have not yet been fully resolved. Proposed ceilings: **32 GB total downloads and 40 GB additional disk use**, with at least 5 GB free disk retained. Stop before crossing either limit; never broaden the download set automatically. Current free disk was 48,315,691,008 bytes at proposal inspection.

Test image generation first with SDPA and sequential offloading; measure peak VRAM, process memory, available RAM, thermals, duration, output dimensions and decoding. Only proceed to video weights if the image smoke passes and disk/memory remain suitable. Then test two 3–5 second image-to-video generations and inspect actual motion and identity. Keep failures explicit, retain logs, and do not swap in fixtures. The currently low available RAM is a meaningful unresolved risk. Performance could be slow, and 6 GB VRAM / 16 GB RAM fit is not established.

Rights: private local use only. [WanGP Community License 2.0](https://github.com/deepbeepmeep/Wan2GP/blob/main/LICENSE.txt) has conditions for embedding/distribution and attribution. [Flux.2 Klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md), [Qwen3 4B](https://huggingface.co/Qwen/Qwen3-4B/blob/main/LICENSE), and [Wan2.2 TI2V 5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B) publish Apache-2.0 upstream licensing. Preserve notices and check converted-file provenance. No paid services, cloud upload, publishing, paid embedding or public distribution is included.

Approval is required by root `AGENTS.md`: “more-than-small model downloads (default >1 GB aggregate)” and “accepting new restrictive terms”. Approval of this proposal covers the bounded private installation/test only; it does not authorize system modifications.
