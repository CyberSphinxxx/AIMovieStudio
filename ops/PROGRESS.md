# Observed development progress — 2026-10-12 (Asia/Manila)

## Session baseline

No existing app or Git commits. Blueprint supplied in a nested directory; preserved intact and copied specs to root. Windows 11 Home, RTX 3060 Laptop 6144 MiB VRAM, NVIDIA 610.88, driver-reported CUDA 13.3, ~15.2 GiB visible RAM, initially ~0.52 GiB free RAM; C: ~54.1 GiB free. Pagefile allocated ~15.2 GiB. No installed Ollama found; no FFmpeg on PATH. System Python 3.14; existing bundled Python 3.12.14 used to create isolated .venv. Node 24.19.0, npm 11.17.0. No drivers/system settings changed.

## Implemented and witnessed

- React/strict TypeScript/Vite workspace, one-prompt creation, local project library, settings diagnostics, story/cast/shots/episodes/export views.
- FastAPI and transactional SQLite WAL migrations, idempotent creation/queueing, persisted original idea and finite season plan, stable character/location IDs, per-episode scripts and prior-outcome canon.
- Serialized worker with exclusive Windows lock, transactional claims, heartbeat, bounded attempts, checkpoint receipts, pause/cancel/resume and atomic files/checksums.
- Watermarked abstract demo references/keyframes/clips, installed Windows speech, synthetic ambience, timed SRT/embedded subtitles, H264/AAC MP4 and provenance manifest.
- Ollama official schema chat adapter, isolated WanGP documented API bridge with missing-weight/unsupported-reference/network-download guards. WanGP contract tests are simulated; actual runtime/inference is NOT VERIFIED.
- App-local FFmpeg/FFprobe downloaded (114,768,076 bytes). No global installation.
- Official Qwen 0.5B CPU GGUF downloaded (491,400,032 bytes) plus pinned llama.cpp CPU runtime (19,501,704 bytes), both checksum-verified. Under 1 GB model-download boundary. Actual CPU plan generation succeeded after correcting schema wrapper against pinned server source. Report: ops/evidence/real-story-plan.json, 11.078 seconds, one episode. This proves structured inference, not strong storytelling; generated world rules were meta-instructions and need quality improvement. Full series/cinematic/GPU quality not established.

## Commands/results so far

- `python -m pytest tests/test_api.py tests/test_story.py -q`: 10 passed.
- `python -m pytest tests/test_pipeline.py -q`: 9 passed. Includes 30s portrait, 60s landscape, square, checksum/corruption/disk errors, series episode 2 and real Windows speech/subtitles.
- `python -m pytest tests/test_crash.py -q`: 1 passed. Actual Windows hard kill after 5 of 10 clips, restarted process completed, committed clip hashes unchanged, one soundtrack/canon checkpoint.
- After Windows job containment added, `pytest tests/test_pipeline.py::test_real_windows_speech_and_subtitles tests/test_crash.py -q`: 2 passed.
- Frontend build/typecheck and ESLint passed; Vitest 2 tests passed after restricting its scope to src/ (initially collected Playwright tests erroneously).
- Playwright Edge: 3 passed after fixing mobile navigation names and exact soundtrack label. Tested actual playback, download, saved project, missing model and settings. Screenshots: 320,360,390,768,1366,1920 widths, studio/export and error. Axe AA checks passed on tested home and mobile studio; no screen-reader test.
- npm audit initially found 4 vulnerabilities; updated Vite/Vitest/esbuild with pinned direct versions and lockfile. Most recent npm audit: 0 vulnerabilities.
- Ruff check passed after cleanup; complete regression after new provider/settings changes running. New changes must not inherit earlier pass claims.

## Known limitations / pending proof

Real GPU images/video, OOM recovery/downshift, full prop/knowledge/world-time canon, versioned editing/regeneration, backups/import, clean-account install, model setup UX and cinematic review remain incomplete. Demo success does not satisfy real generation gate. Release/license distribution review remains open.
