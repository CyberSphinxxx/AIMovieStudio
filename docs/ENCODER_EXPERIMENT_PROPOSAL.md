# Experimental image encoder — approval proposal, 2026-10-16

**Not approved or installed. No image-generation success is claimed.**

The installed image encoder stopped at the RAM guard. This experiment tries a smaller quantized copy of the same Qwen3 base family through the existing pinned WanGP engine. Smaller disk size does not establish RAM fit, acceptable speed, image quality or identity consistency. The native PyTorch fallback may materialize dense weights; the experiment can still fail.

## Exact scope

- One official [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF/blob/bc640142c66e1fdd12af0bd68f40445458f3869b/README.md) file: `Qwen3-4B-Q4_K_M.gguf`, revision `bc640142c66e1fdd12af0bd68f40445458f3869b`, **2,497,280,256 bytes**. SHA256 `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
- **2.6 GB cumulative experiment downloads**, including failed attempts and 26,522 bytes already received for public metadata/license/card. The durable GPU ledger reserves only the remaining 2,599,973,478 bytes; interruptions do not restore spent allowance. **3.0 GB additional installation disk use**, no duplicate weight copy. Retain at least the existing 8,315,691,008-byte installation reserve (also exceeds the 5 GB free-disk floor).
- Reuse the existing Flux Klein 4B int8, Flux VAE and nine Qwen3 tokenizer/config files; verify all eleven hashes. Verify eight inspected engine source/default files. Preserve the installed int8 encoder, original source, defaults, settings, existing projects and all failure evidence. Only add the separately named `flux2_klein_4b_studio_q4` experimental profile, its receipt and notices after the weight verifies.
- No new runtime package, kernel, driver, CUDA toolkit, global Python, Windows/security/firewall/paging/power setting, paid API, cloud upload, login, publishing or distribution. The installer does not run inference or switch Studio's default provider/model. It uses the shared native lock and a separate serialized GPU download ledger.
- After installation, perform **one image-only test**, 512×512, four steps, seed42, SDPA, memory profile5 and transfer buffers off; **300 seconds maximum**, with bounded process cleanup. No automatic inference retry. Require at least5GiB free RAM/4096MiB freeVRAM/<85°C before loading; sample RAM at the existing0.5s target and stop below2GiB or if readings become unknown. Sampling is not a guarantee that usage cannot briefly cross the floor. Log elapsed time/RAM/VRAM/thermals, inspect actual output, preserve any failure. Shared ownership prevents concurrent Studio model calls; independent third-party apps remain outside this cooperation.
- The test writes unique reports/output in `data/gpu-encoder-smoke` and `ops/evidence/encoder-experiment-image-<id>.json`, with a separate `tools/gpu/encoder-image-status.json`. It does not overwrite the original real-image report or make the original video gate pass.

## Overall budget and video gate

After recording all26,522 research bytes once, the existing GPU ledger has11,396,323,893 bytes received and5,620,056,174 bytes reserved. Reserving the remaining experiment allowance accounts for **19,616,353,545 bytes**, within the existing **32 GB total-download /40 GB disk-growth ceilings**. These ceilings do not increase.

The previously proposed video files total14,805,043,208 bytes. Adding them to those reservations would account for34,421,396,753 bytes, **2,421,396,753 bytes over32 GB**. Therefore this proposal **defers video downloads and inference**, pending both an actual visually reviewed image PASS and a complete new cumulative-budget review. Do not refund received bytes, release existing reservations, delete originals, broaden the model set or raise ceilings implicitly. This approval would cover the image experiment only; it would not approve a larger video budget.

## Rights and checks

The pinned [model license](https://huggingface.co/Qwen/Qwen3-4B-GGUF/blob/bc640142c66e1fdd12af0bd68f40445458f3869b/LICENSE) is Apache-2.0; raw license/card bytes and their hashes are captured in `ops/evidence/encoder-candidate-notices/`. Keep notices alongside the installed file. WanGP retains its separate Community License2.0; this is private feasibility work and does not clear paid embedding/public distribution or the outstanding vendor security/license review.

The offline installer fixtures and actual pinned selection-function contract are software checks, not model-load/generation evidence. See `ops/PROGRESS.md` for the exact current test counts/results. No full cinematic-quality, RTX3060 compatibility or finished-product claim follows from these checks.

## Run steps

Read-only preparation, no approval required:

```powershell
tools/app-test-env/Scripts/python.exe -s -m scripts.encoder_experiment inspect
tools/app-test-env/Scripts/python.exe -s -m scripts.check_encoder_selection
```

Only after explicit approval of this proposal:

```powershell
tools/app-test-env/Scripts/python.exe -s -m scripts.encoder_experiment install --approved
```

Only after installation and fresh safe resource readings, within this proposal's single-test limit:

```powershell
tools/app-test-env/Scripts/python.exe -s -m scripts.gpu_smoke image --encoder-experiment --max-seconds 300
```

No readiness reply is inferred from elapsed time. If memory remains insufficient, continue independent coding; do not repeatedly ask the user to close apps.

Approval is required by root `AGENTS.md`: **“more-than-small model downloads (default >1 GB aggregate)”**; the earlier GPU approval limited the selected file set. The [low-VRAM integration skill](../.agents/skills/low-vram-provider-integration/SKILL.md) also states **“Get approval before multi-GB downloads”**. This is a new file, rather than a request to reapprove the already installed stack.
