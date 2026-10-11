# Hardware / inference proof — 2026-10-12

Actual machine evidence: ops/evidence/gpu-baseline.txt, os-baseline.json, disk-baseline.json. Windows11 Home, RTX3060 Laptop6144MiB, driver610.88, ~15.2GiB usable RAM. Driver's CUDA capability is not proof of an installed PyTorch runtime.

## Observed

- FFmpeg/FFprobe: actual watermarked 30s portrait, 60s landscape and square exports tested with H264/AAC streams, target aspect/duration, whole-file decoding and checksum manifests.
- Installed Windows speech: actual WAV synthesis/mixing and embedded/timed subtitles tested. Distinct default/secondary binding exists; broad pronunciation/voice-quality review not performed.
- CPU story: official Qwen2.5-0.5B-Instruct Q4_K_M, SHA256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`; llama.cpp b11558 WindowsCPU release SHA `46a0f4327c89846b5cb6fbebda47ad520ffeedd9ffcbb4b4e51dfdea5af66190`. One structured finite plan succeeded in 11.078s, CPU-only, process unloaded after request. Report ops/evidence/real-story-plan.json. First attempt failed schema validation and was corrected against pinned source; quality weaknesses preserved in report. CPU peak RSS not yet measured. This is **real text inference**, not real imagery/video.
- Windows forced process kill: test_crash.py passed after five clips, preserved committed clip hashes, ten clips after restart, one soundtrack/canon checkpoint. Additional pass after kill-on-close process containment added.

## NOT TESTED / incomplete

Real GPU image generation, real GPU video (two reproducible runs), GPU OOM downshift, native portrait/landscape model support, VRAM/RAM peak during inference, temperature/time measurements, character likeness consistency, cinematic quality, sustained feature-length production.

Next hardware procedure: choose licensed low-memory WanGP image/reference-capable + i2v model from installed capability discovery; obtain download approval; one 3–5s shot, modest resolution, `sdpa`/low-memory profile, no concurrent LLM; sample nvidia-smi/OS memory; inspect native+normalized media and hashes; repeat twice; record exact model revision/settings/license. If blocked, continue independent backlog and preserve this NOT TESTED status.
