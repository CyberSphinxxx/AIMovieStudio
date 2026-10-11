# 12 — Ordered implementation backlog (do not stop at scaffolding)

**Priority:** P0 required, P1 after MVP, P2 later. Only mark DONE with tests + artifact evidence in `ops/PROGRESS.md`. Preferred task unit: 1 independently testable change set. Start with synthetic media so the complete product flow can be built before heavy model downloads. Dependencies listed in brackets.

## Phase 0 — Grounding and feasibility [P0]
- F0.01 inspect repo and OS, git status, disks, driver/GPU, ffmpeg/toolchain; save evidence.
- F0.02 source/license register with WAN GP license, model cards, third-party terms and attribution; record approved project distribution assumptions.
- F0.03 reference WanGP API/MCP contracts, evaluate FramePack fallback, choose first smoke model on measured hardware. No huge download without consent.
- F0.04 minimal monorepo architecture ADR + database and provider contract ADR; acceptance test runner.
**Exit:** documented provider decision or honest blocked status; no unsafe downloads.

## Phase 1 — Functional project skeleton [P0, F0]
- F1.01 scaffold Python FastAPI + SQLite/migrations, React/Vite TS strict, automated lint/tests, Windows development launcher.
- F1.02 create persisted project API, mode/aspect/duration validation, frontend idea composer, project list/reopen.
- F1.03 consistent design system/components, mobile-responsive cards, meaningful empty/loading/error states.
- F1.04 local health/diagnostics settings and explicit demo-vs-real backend indicator.
- F1.05 Playwright E2E new project from one input, restart/reopen.
**Exit:** persist prompt and reopen project after restart, tests green.

## Phase 2 — Scriptwriting and canon [P0, F1]
- F2.01 structured `StoryProvider`, deterministic mock and local LLM adapter (Ollama or compatible), schema-repair.
- F2.02 story outline, complete finite ending, episode beats, world/characters/location registry.
- F2.03 full screenplay scripts via bounded batches, reference IDs, pronouns/aliases, dialogue timings.
- F2.04 continuity engine event log, knowledge per character, chronological state, contradictions and optional lock.
- F2.05 series create, save/restart, episodes 1..N, episodes maintain ending and character canon.
- F2.06 optional 'prewrite every episode' with bounded batch progress, no unbounded single completion.
**Exit:** F03 series fixture passes across restarts; corrupted/malformed LLM responses handled.

## Phase 3 — Media asset pipeline [P0, F2]
- F3.01 typed image/media provider mock, file store + sidecar manifests, versioned references.
- F3.02 image storyboard job dependency graph, stable cast/location prompts and reference locking.
- F3.03 provider discovery/config and first tested REAL image generation on hardware (separate gate).
- F3.04 auto characters (portrait/side/full-body feasible), locations/props and per-shot keyframe approval automatically.
- F3.05 per-asset failure/retry, caching, lineage, user optional replace/approve.
**Exit:** prompt creates saved reference images; real model proof recorded separately.

## Phase 4 — Reliable job orchestration [P0, F1/F3]
- F4.01 durable worker with transactional task claim, leases, deps, no duplicate task execution, heartbeat.
- F4.02 granular stage/shot status event streaming to frontend.
- F4.03 pause, cancel, resume, retry caps, idempotency, atomic outputs and recovery.
- F4.04 GPU semaphore, model unload between resource-heavy stages, disk quota/notifications.
- F4.05 simulate power loss, stale RUNNING and FFmpeg crash regression tests.
**Exit:** crash fixture F05 passes with complete shot reuse.

## Phase 5 — Real video backend [P0, F0/F3/F4]
- F5.01 implement strictly documented WanGP adapter, project metadata/attribution and health; no hardcoded unknown API signatures.
- F5.02 run first 3-5 sec real image-to-video test in suitable low-VRAM mode with 6 GB and 16 GB proof logs.
- F5.03 connect 6-10 shots into sequential queue, per-shot provider settings and output inspection.
- F5.04 implement graceful OOM retry profile, provider downgrade only if capabilities validated; bounded attempts.
- F5.05 optional FramePack adapter if WanGP cannot pass measured smoke. DO NOT web-scrape a local UI if official callable surface exists.
**Exit:** real local AI video clip verified; otherwise milestone remains blocked, demo is NOT mislabeled.

## Phase 6 — Audio, timeline, export [P0, F2/F3/F4]
- F6.01 voices by speaker, local TTS adapter, WAV stems, duration adjustment and subtitles.
- F6.02 SFX/ambience rights-managed library, optional score, no paid service required, audio normalization.
- F6.03 timeline/EDL, portrait/landscape fit without stretch, ffmpeg concat/transitions.
- F6.04 H264/AAC MP4 atomic export + ffprobe verification + manifest.
- F6.05 final preview, open folder, re-export 9:16/16:9 and subtitle sidecars.
**Exit:** mock F01/F02 and real-provider short when available, all media validation checks pass.

## Phase 7 — Automated directing and polish [P0/P1, F2..F6]
- F7.01 orchestrate from **one** create button all pipeline stages; no manual stepwise setup after first-time provider install.
- F7.02 quality gate: deterministic media faults plus optional image-review score, bounded regenerations, honest partial statuses.
- F7.03 shot/story/characters/episodes UI and editable advanced views, user revisions invalidate only needed assets.
- F7.04 accessibility/responsiveness, shortcuts, details on cost, duration and resources.
- F7.05 complete long-form fixture, series episode 2 generation reusing actor, render queue.
**Exit:** novice can use app without docs after setup; screenshot/manual review.

## Phase 8 — Distribution, documentation and audits [P0, F1..F7]
- F8.01 Windows launch/start/stop scripts, one-click first-run diagnostics, offline demo, model setup with consent.
- F8.02 user manual, troubleshooting, model selection, rights/licensing disclosures, backup/restore and privacy.
- F8.03 packaging architecture and license review; no paid embedding of WanGP without legal clearance.
- F8.04 clean-machine end-to-end verification; performance log, GPU safe temps guidance, sleep/power interruption.
- F8.05 security review, threat model, dependency audit, no-secret scan, final regression test suite.
- F8.06 release notes, screenshots, known limitations, actual exact user commands.
**Exit:** release checklist fully satisfied or truthful list of remaining blockers.

## Phase 9 — Stretch [P1/P2]
A) advanced edit timeline with per-shot regen, advanced references and model presets; B) storyboard/higher-res export; C) cloud approved provider adapters with opt-in cost ceilings; D) portable PC-to-GPU worker; E) optional batch production, trailer/trailers and YouTube presets; F) fully local model ecosystem as weights improve. Gate by hardware, licenses and user demand.

## Scheduling policy for Codex
Implement tasks in dependency order but favor a testable end-to-end vertical slice early. While real GPU/download approval is blocked, advance story engine, mock media, job reliability, FFmpeg export, UX and tests. Never stall all useful work behind a single provider install. Each phase needs demo evidence before next large milestone.
