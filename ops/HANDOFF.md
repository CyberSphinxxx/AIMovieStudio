# Handoff — 2026-10-12

Status: ACTIVE DEVELOPMENT; full application unfinished. Original blueprint preserved. Latest coherent checkpoint described in Git log (parent c05ee35, branch main). Main app runs at127.0.0.1:8765 with current backend. No remote changes.

Environment: Windows11 Home, RTX3060Laptop6144MiB, driver610.88,16GB RAM. Main .venv Python3.12.14; isolated tools/gpu/python Python3.11.14 and tools/wan-gp/.venv Torch2.10.0+cu130. Node24.19/npm11.17. App-owned FFmpeg and tinyCPU Qwen0.5B/llama.cpp. No global driver/Python/security changes.

Verified:43 backend tests(40.12s),2 Vitest,5 Edge flows(30.1s),Ruff/lint/TypeScript/build PASS, main Python/npm audit0. First latest browser run failed ambiguous Series locator; fixed exact name and reran all5 PASS. Tests include hard process termination/hash reuse, active pause/cancel/SSE, ten-episode screenplay checkpoint recovery, backup hostile/corrupt/no-overwrite restore and actual resumed MP4, resource preflight and download budget/resume. See full-verification.json/browser-tests.json. Settings screenshot loaded and inspected.

Working commands:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser
.venv/Scripts/python.exe -m scripts.story_smoke
.venv/Scripts/python.exe -m scripts.backup create --archive studio-backup.zip
```

Approval: User approved pinned private GPU stack/model install with32GB downloads/40GB disk growth, image PASS before video, no system changes. APPROVALS.md/proposal authoritative. Source/runtime/image files installed/checksum-verified; ledger11,383,697,362 received bytes plus conservative reservations. Video weights NOT downloaded. User said they would close heavy apps and report ready; actual model loading awaits readiness plus fresh preflight.

GPU blocker: Actual API smoke FAILED44.0s before inference. WinError4551 and CodeIntegrity3077 identify torch_cuda.dll blocked by Windows Application Control. No OS policy changes authorized/made. real-gpu-runtime.json includes import-stage sampled RSS/device memory/temp; gpu-code-integrity.json includes event. No GPU generation/fit/quality proof. Do not keep blindly retrying or bypass policy. Vendor audit90 advisories in6 packages; Pillow12.3 override vs Gradio<12 constraint, headless compatibility unproven. Main clean audit does not cover vendor.

CPU story: Direct plan19.422s+script23.281s; worker checkpoints31.078s first/89.656s latest, then missing-provider/license in isolated fixture. One intervening attempt exhausted3 JSON repairs(project b43e1969-addb-4fa6-af87-39b4e95ceeff). Tiny model weak/unreliable; no high-quality real season claim.

Next exact task: F6.01 restrict excessive speech speed-up and move CPU audio validation before expensive references/clips. Add actual Windows overflowing-line regression; preserve raw voice and fail clearly, never cut dialogue to fake success. Then continue F2.04 richer canon or F6.05 export variants. GPU branch requires policy-compatible runtime within approval; no security workaround or video download before reviewed image PASS.

Main files: studio/{domain,story,storage,worker,backup,media,providers,vendor_bridge,vendor_telemetry,diagnostics,api}.py; scripts/{backup,gpu_smoke,setup_gpu,prepare_gpu_runtime}.py; client/src/App.tsx; tests/. Backups strip executable settings; imported paused jobs freeze current reviewed settings on first resume.

Open: knowledge/props/world-time canon, editing/asset replacement, export variants, graphical restore/setup, clean-account packaging/licensing, GPU OOM/hardware and cinematic QA. Continue independent work while GPU is blocked.
