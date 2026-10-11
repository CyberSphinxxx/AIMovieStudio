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

## Approved GPU installation and first actual import — still no inference

Authorization is recorded in APPROVALS.md; versions/file hashes in gpu-download-proposal.json,wan-runtime-lock.txt,wan-runtime-artifacts.json and ignored tools/gpu/download-ledger.json. WanGP6479db36bdc2619a904a852bba9c2d78e1a83f82; Python3.11.14; Torch2.10.0+cu130. Source/runtime and FluxKlein4B int8/Qwen3 int8/FluxVAE/tokenizer files installed, not video files.

Actual command `.venv/Scripts/python.exe -m scripts.gpu_smoke runtime` FAILED after44.0 seconds before model loading. Preflight7.51GiB free RAM,5438MiB free VRAM,72°C. Windows error4551 while loading shm.dll/dependency; Code Integrity3077 identifies torch_cuda.dll blocked by application-control policy. Import-stage telemetry sampled359,653,376bytes process RSS,942,284,800bytes whole-device VRAM,73°C. No GPU image/video was generated. This is not hardware fit proof. No Windows policy changed.

Source diagnosis: Microsoft App Control troubleshooting documentation explains enforced block events3077 and correlation-signature events3089: https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/appcontrol-debugging-and-troubleshooting (checked2026-10-12). Local event evidence is gpu-code-integrity.json. Vendor audit90 advisories remains unresolved; main-app audit0 is separate.

Next GPU step requires a policy-compatible runtime within authorized scope, then API discovery, one real image plus reference-conditioned variant with manual inspection/telemetry, then image PASS before video downloads. User readiness/resource headroom remains a prerequisite. No automatic security-policy workaround.

## Latest actual CPU writing review

Added declared-continuity schema exposed weak model output. Run e4daeb5e was structurally valid in37.64s but manual writing review FAILED: title-only screenplay, generic physical descriptions, unsupported death and repeated references. After stricter screenplay/camera gates,781abf8b failed at8192-token context overflow. Repair history is now bounded to the latest failed response and concise errors. Latest f6b050ee still FAILED after three attempts with truncated JSON,297.547s total (plan13.437s). Evidence real-story-runs/ and current real-story-plan.json. Earlier shape-valid results are historical, not a writing quality pass. No additional model downloaded.
