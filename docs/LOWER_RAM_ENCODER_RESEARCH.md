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
