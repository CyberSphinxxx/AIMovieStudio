---
name: low-vram-provider-integration
description: Safely integrate or troubleshoot WanGP, FramePack, ComfyUI, image, speech or video inference on RTX 3060 6 GB VRAM/16 GB RAM. Use on provider API changes, model selection, CUDA errors, resource or licensing analysis.
---

Read `docs/00_RESEARCH_GATES.md`, `docs/09_HARDWARE_AND_PROVIDERS.md`, `architecture/PROVIDER_INTERFACE.md` and `docs/14_LEGAL_SAFETY.md`. Inspect official versioned docs/model license. Never invent API names, never assume all models fit 6 GB. Get approval before multi-GB downloads, vendor installation, paid service or system modifications. Start with smallest reasonable smoke test, one GPU workload at a time, measure VRAM/RAM/elapsed/resolution and ffprobe output. Record in `ops/HARDWARE_PROOF.md`. Retry OOM with bounded lower-memory settings, isolate optional provider environment, keep mock distinctly labeled. When blocked by hardware, complete unrelated code/tests and leave precise verification instructions.
