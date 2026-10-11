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

Real GPU images/video, OOM recovery/downshift, full prop/knowledge/world-time canon, versioned editing/regeneration, graphical restore, clean-account install, model setup UX and cinematic review remain incomplete. Demo success does not satisfy real generation gate. Release/license distribution review remains open.

## Subsequent implemented slices and observed evidence

- Optional whole-season prewriting: durable DRAFT steps, ten-episode interrupted receipt recovery, saved screenplay reuse, completed-canon revalidation. DRAFTED never means canonical or filmed. Browser three-episode fixture produced chapter2 and blocked chapter3 until prior production.
- Portable archive: consistent logical DB snapshot + hashed immutable assets, 20GB/64MB limits, reserve, exclusive atomic publication; new-folder restore strips commands/settings and pauses unfinished work. Tests checked traversal, checksum rejection, no overwrite and actual interrupted MP4 completion with preserved media hashes. Initial Windows read-only fsync failed; changed to r+b and all four backup tests passed.
- Active pause/resume/cancel, SSE replay cursor, failed retry settings update, and concurrent transactional claims tested. Main API default migration/idempotency tested.
- Earlier full verify.ps1 -Browser passed34 backend tests,2 Vitest and4 Edge flows. Main dependency audit initially found49 advisories in Pillow/pytest/venv pip; upgraded Pillow12.3.0,pytest9.0.3,pip26.2.1. Latest main pip audit0 and npm audit0. The vendor has a separate failing audit.
- Latest targeted recovery/provider/resources run:22 passed in28.96s. Resource fixtures simulate counters; no GPU compatibility claim. Download/policy targeted run:9 passed in0.14s. These prove resume accounting, no unsafe restart over budget, checksum rejection, no overwrite, and actionable Windows-policy errors.
- Real CPU direct smoke: finite plan19.422s, screenplay23.281s with IDs/timing valid. Worker checkpoints passed31.078s(first) and89.656s(latest). An intervening project b43e1969-addb-4fa6-af87-39b4e95ceeff exhausted three JSON repairs; preserved in data/real-pipeline-smoke. No strong writing-quality claim.
- Explicit approval received for private GPU install:32GB network/40GB added disk, no system changes, image gate before video. Pinned WanGP source, app-owned uv/Python3.11.14,161 locked runtime artifacts(2,352,772,985 bytes), local FFmpeg/FFprobe/FFplay and selected Flux image/Qwen3 encoder/VAE/tokenizer files installed and verified. Download ledger records11,383,697,362 received bytes plus conservative reservations; no video weights installed.
- Actual API smoke ran after headroom improved to7.51GiB free RAM,5438MiB free VRAM,72°C. It FAILED after44.0s, before inference: WinError4551 and Code Integrity3077 identify blocked torch_cuda.dll. Telemetry sampled peak RSS359,653,376bytes, whole-device VRAM942,284,800bytes and73°C; these are import-stage sampled maxima, not inference fit proof. Evidence real-gpu-runtime.json/gpu-code-integrity.json. No security-policy changes, no real generated GPU output.
- Vendor lock audit:90 advisories in six packages; Pillow12.3 override conflicts with Gradio's declared constraint. Headless compatibility and remediation unresolved. No vendor UI server/network exposed; no clean vendor audit claim.
- Visual Settings review found initial form editable before saved configuration loaded. Fixed disabled loading/error state and added a gated browser request regression. Latest full regression running; do not infer its outcome from earlier checks.

Final updated verification: Ruff PASS;43 backend tests passed in40.12s;2 Vitest passed; ESLint/TypeScript/Vite build PASS; main Python/npm audit0. First browser run4pass/1fail due ambiguous Series locator matching existing project card. Fixed exact accessible name; rerun5 Edge tests passed in30.1s. Settings screenshot now waits for loaded data; manual visual review performed. Evidence full-verification.json and browser-tests.json.


## Dialogue quality, source stems and Windows restart repair

Speech now runs before visual stages for new jobs. Measured lines exceeding1.15x tempo fail DIALOGUE_TOO_LONG without trimmed/raced dialogue. Actual Windows overflowing-line regression preserved raw WAV and generated no visuals; short speech/subtitles passed. Original voice, scene track and ambience WAVs are immutable hashed assets with soundtrack parent lineage, portable-backup tests (including silent first shot/voice2 identity), and optional Export downloads. Existing jobs retain persisted step order.

First audio regression46 passed; then latest full run46pass/1fail uncovered immediate post-hardkill SQLite disk I/O error. Added extended error diagnostics and3 repeated actual kills:2pass/1fail, identified SQLITE_IOERR_TRUNCATE1546. Failed DB integrity_check=ok. Narrow Windows startup retry uses fresh connections for this code only (3 total attempts,100/200ms), never deletes WAL or retries corruption/write failure. After repair7 tests passed21.87s, including3 actual hard kills;2 actually encountered the truncate error and recovered on retry. Evidence crash-io-inspection.json/crash-truncate-recovery.json. Full updated regression running; do not present earlier passes as its result.

Final speech/restart verify.ps1 -Browser PASS:53 backend60.46s,2 Vitest,5 Edge32.1s; Ruff/ESLint/TypeScript/build and main Python/npm audits0. Browser fetched real RIFF WAV stem. No new GPU inference proof.


## Declared prop/knowledge continuity (current work)

Implemented optional prop registry/initial knowledge, actor-specific prop uses and fact assertions, after-shot changes with before-state and causal reason, offscreen dead-speaker checks, episode-start flashback snapshots (no present-canon changes from flashbacks). Proposed changes remain in drafts until completed export; append-only canon_committed records source step/before/value/reason. Prewriting simulates earlier draft changes separately from actual canon, then production revalidates against completed facts. Prop image references participate in hashed shot lineage; corrupted references block keyframe generation. Frame prompts now include requested cinematic style and camera composition (template2).

Targeted19 passed initially; schema/API extensions20 passed; latest story/continuity/prewrite15 passed. Full intermediate regression62 backend65.38s,2 Vitest,5 Edge32.6s and main audits0 passed before subsequent screenplay/camera/repair-history tightening; final current regression still needed.

Real CPU runs preserved per project in real-story-runs/. First added-fields run3707f8c1 failed30.36s at invalid episode1 flashback. Episode-specific schema constrained allowed flashbacks/IDs/field values; next e4daeb5e run shape/declared checks passed37.64s (plan14.781+script22.859) BUT manual writing review FAIL: title-only screenplay, camera portrait, generic physical descriptions, unsupported death reason and repeated references. Not full screenplay quality proof. Added minimum scene-content gate and cinematic camera enum; next781abf8b run failed222.578s because repair history accumulated8290 tokens beyond8192. Bounded history to latest4000-character response + concise error list, retaining3-attempt ceiling; retest running. Stronger writing model and bounded long-script batches remain necessary research/implementation work, no new model download authorized.

Bounded-history actual CPU retest f6b050ee FAILED after three attempts: truncated JSON,297.547s total,plan13.437s. Preserved complete result; no writing quality pass. Stop tuning this weak model against the same failure and advance bounded screenplay architecture.

Final declared-continuity verify.ps1 -Browser PASS:62 backend75.87s,2 Vitest,5 Edge34.5s; Ruff/ESLint/TypeScript/build and main Python/npm audits0. Command output continuity-verification.log; no real GPU inference or CPU writing quality pass.
