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

## Durable screenplay sections

New jobs write SCRIPT_BATCH/DRAFT_BATCH sections of at most4 shots, each using existing atomic receipt/transaction/retry machinery; final SCRIPT/DRAFT validates complete runtime/continuity before production. Short scripts and legacy persisted steps retain behavior. Local schema caps section screenplay/action/narration and change counts, includes episode outline/last2 shots/last1500 text plus previous changes, rejects oversized prompt context. Global shot IDs/causal positions retained; no proposed fact commits until export. UI reports episode and shot range and includes prewriting in story progress.

Initial targeted8pass/1fail found backup stage allowlist omitted new sections; fixed and reran23 tests PASS54.31s (sections/media/prewrite/3 real hardkills). Nine new section tests cover600s120-shot fixture, receipt recovery, portable partial restore/no rewrite, batched3-episode prewrite/reuse, cross-section knowledge, missing/invalid sections blocked before visuals and pinned schema/legacy step. Full verify.ps1 -Browser PASS71 backend77.25s,2 Vitest,5 Edge31.0s, lint/type/build/main audits0. Evidence script-batch-verification.log. This proves durable bounded orchestration with labeled deterministic fixtures, not real screenplay quality or GPU filmmaking.

Next: test and prepare additional licensed CPU writing experiment. Exact reviewed proposal CPU_STORY_INSTALL_PROPOSAL.md; no1.5B weights downloaded or approved yet. Keep advancing independent work while GPU App Control remains blocked.

## Additional CPU writing proposal/profile (approval pending)

Official1.5B GGUF revision/hash/license reviewed; proposal caps1.2GB network/1.5GB added disk, no runtime/system install. Bounded installer rejects absent approval, budgets/corrupt artifacts/existing targets and validates resume; explicit profile checks installed weight size/SHA and5GiB RAM before process launch. Writing-only worker smoke stops at failed section/ten minutes/2GiB remaining RAM, preserves checkpoints, samples server RSS/available RAM and never enters imagery. No1.5B weights downloaded; no inference/fit/quality pass. Human async approval question pending.

23 targeted CPU profile/setup/API/story checks PASS3.33s, including actual read-only own-process memory counter. Full verify81 backend79.01s/2 Vitest/5 Edge31.6s and main audits0 PASS. Subsequent inspection fixed completed partial downloads otherwise making HTTP Range past EOF in both GPU/CPU helpers; first added test placed an old assertion in wrong function, corrected.10 download fixture tests PASS0.15s, Ruff PASS. Actual downloads were not performed. Evidence cpu-profile-verification.log.

While this separate approval is pending, next independent work: F7.03 optional saved future-draft dialogue/action editing with optimistic revision, full continuity revalidation, retained history and later-draft invalidation.

## Approved CPU installation and future-draft editor

Human approved bounded CPU installation/tests. Installed official pinned1.5B GGUF/license/card and verified lengths/SHA256. Ledger1,117,336,935received bytes, artifact+ledger disk1,117,337,907bytes (small test evidence separate), within1.2GB/1.5GB caps. First writing-only smoke7059fecb failed preflight0.062s at2.44GiB free RAM (requires5GiB), no process samples or model loading. Later2.99/2.87/2.88 readings still inadequate. Preserve resource failure; no1.5B inference/quality/fit proof, no user apps killed or system changes. Evidence cpu-story-install-result.json,real-cpu-batched-story.json; original proposal stays historical PROPOSAL_ONLY, approval/execution recorded separately.

Optional Story editor now changes action/camera/speaker/spoken lines for saved unproduced episodes; typed sparse patch keeps identities/timing. Atomic optimistic revision checks refuse active/produced scripts, stale edits, unknown IDs and declared contradictions; before-script+edits retained in append-only event. Later drafts REVIEW_REQUIRED; production revalidates current canon and consumes edited draft. Previous draft text API/UI exposes latest25 matching revisions within500 latest project edit events; all versions stay on disk/backups. Unsupported: edited produced media, exact prose semantics, outfit/world-time changes, conflict merge and recovering unsaved edits after changing episode/reloading.

17 edit/continuity/prewrite checks PASS23.91s. Full91 backend PASS101.66s +main audits0;2 Vitest/lint/build PASS. Initial Edge4pass/1fail timeout from getByLabel exact on implicit label containing textarea text. Explicit htmlFor/IDs fixed; all5 Edge passed39.2s including polling/tab preservation,390px editor/Axe, saved history, reload and actual episode2 demo export. Visual inspection found/fixed Demo punctuation mojibake and incorrect Ready-to-watch badge on unproduced episode. Latest14 story/edit tests PASS14.09s,2 Vitest/lint/build/Ruff PASS; final5 Edge39.2s and mobile screenshot visually inspected. Logs draft-editing-verification.log (includes failure),draft-editor-browser-final.log; no fabricated real imagery/writing quality.

## Truthful setup readiness and refresh

Provider discovery now distinguishes installed versus available/demo/speech, weak feasibility model,1.5B low/unknownRAM and last GPU runtime block. Machine-owned bounded runtime-status summary carries timestamp/source evidence digest; imported previous witnessed WinError4551 failure from exact actual GPU evidence without rerunning native code. Later real smoke writes the summary only after attempting runtime discovery; a resource-only failure preserves the last native observation. Other selected installation cannot inherit an unrelated block. Invalid/oversized records become untested; no runtime import on Settings.

Refresh diagnostics fetches health/provider state independently while preserving unsaved preferences. Low-RAM guidance uses5GiB for initial GPU/1.5B profiles; no fit claim. Screenshots revealed SPA navigation retained previous page scroll; reset scroll for explicit navigation and tested Settings opens at top.

19 targeted status/API/CPU profile checks PASS3.47s. Full verify.ps1 -Browser PASS97 backend102.81s/2 Vitest/5 Edge41.9s, Ruff/lint/type/build/main audits0. Subsequent native-smoke-summary guards and path parsing passed8 targeted development fixtures0.15s (no GPU launched); final frontend lint/build and all5 Edge43.2s PASS after navigation fix, screenshots/Axe checked. Evidence setup-status-verification.log,setup-browser-final.log. Latest free RAM3.26GiB still below5; no1.5B inference retry, no GPU generation.
