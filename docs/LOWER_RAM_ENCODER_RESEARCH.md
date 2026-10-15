# Lower-RAM image encoder candidate — research only

No weights downloaded, profile installed or inference performed. This is the next feasibility investigation, not an approved download or verified backend.

The installed int8 image text encoder is4,414,004,409bytes and the latest FluxKlein profile5/buffers-off test stopped at the RAM guard before producing an image. A smaller on-disk encoder is a plausible changed strategy; file size does not prove resident RAM, GPU fit, speed, image quality or tokenizer compatibility.

[Qwen's official GGUF repository](https://huggingface.co/Qwen/Qwen3-4B-GGUF) declares Apache2.0 and base model Qwen/Qwen3-4B. Public metadata read on2026-10-16 (7402bytes) is saved in `ops/evidence/qwen3-base-gguf-candidate.json`:

- Revision:`bc640142c66e1fdd12af0bd68f40445458f3869b`.
- File:`Qwen3-4B-Q4_K_M.gguf`,2,497,280,256bytes.
- SHA256:`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
- This differs from the installed CPU writer's Qwen3-4B-Instruct-2507 weights; do not substitute the writer file or reset its experiment allowance.

The pinned WanGP `docs/FINETUNES.md` documents custom text_encoder_URLs and inherited base model weights, and `models/flux/modules/text_encoder_qwen3.py` contains GGUF name mapping. Existing original tokenizer/config advertises Qwen3ForCausalLM/2560hidden/36layers. These are static compatibility leads, not a successful load. The installed gguf parser is0.17.1; required CUDA-kernel/fallback behavior and exact public configuration path still need checking without new models or vendor source edits. No new package/driver/toolchain is implicitly authorized.

Next authorized work: verify the pinned configuration/loader route, prepare an exclusive named finetune profile reusing current Flux/VAE/tokenizer files, contract-test offline/no-download/missing-file/hash-failure behavior, and write a bounded download/test proposal with cumulative32GB/40GB accounting. Preserve original weights/defaults; no automatic model upgrade. Then request approval before fetching this new multi-GB file: the original GPU proposal explicitly limited the download set, even if its overall cap has room. Keep5GiBRAM/4GiBVRAM/<85C startup,2GiB ongoing floor/shared ownership, bounded first-failure stop, actual image review before video. Current resources and existing CUDA arithmetic do not prove this candidate fits.

## Pinned source inspection and budget check

The installed source at6479db36bdc2619a904a852bba9c2d78e1a83f82 provides a plausible public route without editing defaults:

- A separately named `finetunes/<id>.json` can use architecture`flux2_klein_4b`, inherit `URLs` from`flux2_klein_4b`, and supply a single `text_encoder_URLs` item. `wgp.py:get_model_filename` selects the sole item independent of the configured int8 preference; `get_model_recursive_prop` resolves inherited base URLs. This is static source evidence, not a published/loaded configuration.
- `wgp.py` registers `shared.qtypes.gguf` with the vendored MMGP router. `load_gguf_state_dict` keeps memory-mapped packed tensors, and `Qwen3Embedder` provides the standard GGUF-to-Hugging-Face name mapping using the existing local configuration. `mmgp/offload.py:fast_load_transformers_model` accepts a registered file extension and uses the supplied `defaultConfigPath`. No new external llama.cpp process is part of this route.
- Optional `llamacpp_gguf_cuda` is probed by the handler and failures use a PyTorch fallback. The fallback materializes a dense weight for a linear operation; packed-row embedding dequantizes requested rows. This does **not** prove lower peak RAM/VRAM or acceptable speed. Optional CUDA package availability/compatibility has not been tested, and no package/toolchain installation is assumed.
- The existing offline bridge refuses external sockets and checks model availability before submitting. Keep this behavior; an absent candidate must never trigger an engine download. The existing smart-pinning-off option remains appropriate for an experiment because the GGUF loader explicitly rejects pin-to-memory loading.

Read-only snapshot `ops/evidence/encoder-candidate-readiness.json`: current app/worker/database healthy on own Python3.11.14, ownership free, RAM4.32GiB (app reading4.33), freeVRAM4670MiB/56C, free disk34,112,110,592bytes. No model loaded; both native startup RAM gates still block. Original GPU ledger received11,396,297,371bytes plus5,620,056,174bytes reserved. Adding this candidate accounts for19,513,633,801bytes, within32GB **for this image experiment only**. Adding the remaining proposed video files14,805,043,208bytes would total34,318,677,009bytes, **2,318,677,009bytes over the approved cap**. Reservations must not be silently released, past downloads refunded, originals deleted, or ceilings raised. A concrete proposal must explicitly defer/rebudget video; no experiment approval has been requested yet. Image visual PASS remains a separate prerequisite for any video download/inference.

Next: contract-test that exact separately named profile using local file fixtures, verify loading configuration provenance and tokenizer coverage, and prepare the complete bounded proposal. Source inspection and metadata alone are insufficient to install or advertise this candidate as ready. The approved saved-plan CPU test remains independent, needs7GiB free RAM and retains330.281seconds of total experiment allowance.
