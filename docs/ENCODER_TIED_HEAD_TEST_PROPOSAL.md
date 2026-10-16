# One image retest with a scoped tied-weight fix — approved

Human approved2026-10-16: **“Approve one bounded image retest.”** Approval is for the single additional attempt below and persists across sessions. Do not request it again. Resource guards still apply; no attempt is spent until ownership, resources and installed-file checks pass. Native load/fit/quality remain unproven.

The first approved Q4 image attempt has finished and its allowance is consumed. Run `9c5b708d-10fd-470a-abd4-19853154acf0` failed during loading after83.75s with `Missing keys: ['lm_head.weight']`. It generated no image. Its report, status and durable reservation remain intact.

## Concrete change prepared for review

The installed GGUF header contains token embeddings and omits `output.weight`; the installed Qwen3 configuration has `tie_word_embeddings=true`. The [Transformers GGUF source](https://github.com/huggingface/transformers/blob/main/src/transformers/modeling_gguf_pytorch_utils.py) treats an omitted output projection as shared embeddings. The pinned WanGP mapper remaps names but supplies no tie map, and its MMGP loader strictly rejects the missing head. This diagnosis combines actual local header/source evidence with the upstream convention; it does not establish a successful quantized load.

`studio/vendor_qwen_compat.py` wraps the existing preprocessing callback only in an explicit, separate image experiment. After name mapping it supplies MMGP's existing tied-weight map from token embeddings to the missing output-head alias, retaining the same packed object. It preserves an explicitly stored output head and rejects wrong configurations, shapes, conflicting ties, changed source hashes or another loaded module. The original factory is restored on success and failure. No vendor file or default setting is edited; missing-key checking stays enabled. Five source/config hashes pin the inspected engine6479db36bdc2619a904a852bba9c2d78e1a83f82.

Offline object contracts and an extraction of the actual pinned mapping/MMGP alias loop reproduce the original missing alias and verify the proposed correction without importing AI runtimes or reading tensor payloads. These are **not** native loading, quantized storage, memory-fit or image-quality evidence. The actual installed header-only report is `ops/evidence/encoder-header-4bb9065d0fa94ce58898f63f4c36d51c.json`.

## Requested additional scope

- **One additional image-only attempt**, maximum300seconds plus existing bounded child cleanup. Same512×512, four steps, seed42, SDPA, profile5, transfer buffers off and existing lighthouse-keeper prompt. Stop on first failure; no automatic retry.
- Reuse the existing pinned Qwen3-4B-Q4_K_M/Flux/VAE/tokenizer/runtime. **Zero new model or runtime downloads, zero new installation**, no package/kernel/driver/toolchain/global-Python/system/security/paging/firewall/power changes. No paid service, account, upload or publishing. Original32GB cumulative download/40GB disk-growth ceilings remain unchanged; existing receipts/reservations are not refunded or released. Video stays deferred.
- Acquire shared native ownership before resource checks, checksum validation or attempt reservation; hold it through generation and child cleanup. Require fresh5GiB free RAM/4096MiB freeVRAM/<85C. Parent sampling target0.5s, stop below2GiB or with unknown counters. These guards do not guarantee an unsampled peak cannot cross the floor.
- Use a new immutable `tools/gpu/encoder-tied-head-test-reservation.json` after admission, preserving the original spent reservation and linking its SHA256. Failure or interruption consumes the new attempt. Resource/ownership refusal before reservation consumes nothing.
- Unique output/report in `data/gpu-encoder-smoke/<new-id>` and `ops/evidence/encoder-tied-head-image-<new-id>.json`, with separate `tools/gpu/encoder-tied-head-status.json`. Preserve the original image status/reports. Record compatibility usage, sampled RAM/VRAM/temperature, elapsed time and exact errors. Inspect any generated image before claiming PASS. No automatic default-provider change or video admission.

Only after explicit human approval of **this additional attempt**, and only when resource guards pass:

```powershell
tools/app-test-env/Scripts/python.exe -s -m scripts.gpu_smoke image --encoder-experiment --tied-head-retest --approved-tied-head-retest --max-seconds 300
```

The approval flag records operator authorization; it must not be supplied merely because the harness exists. Calling the retest without it refuses before setup or model import. The original `--encoder-experiment` route remains spent and cannot be used as a workaround.

## Why this needs a new decision

The previously approved proposal explicitly permitted **one** image test, now consumed by the observed failure. This requests a second attempt with a concrete tested loader change, not reapproval of the installation. Offline engineering can continue without this approval. Native quantized alias behavior, memory fit, speed, identity and visual quality remain unproven.
