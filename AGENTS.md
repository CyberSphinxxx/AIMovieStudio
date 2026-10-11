# Codex standing instructions — AI Movie Studio

## Mission and priority
Build, verify and polish the self-contained, local-first, single-input creative filmmaking product described in this package. Prioritize: (1) end-to-end usability; (2) correctness/data durability; (3) truthful provider capabilities; (4) safety/licensing; (5) low-resource operation; (6) visual polish. User is not a production engineer: make installation and creation self-explanatory.

## Continuous but bounded engineering cycle
Follow this cycle within every available coding session:
1. RECON: `git status`, inspect tree, read `ops/BOARD.md` and `ops/HANDOFF.md`, run quick baseline checks. Preserve existing changes.
2. SELECT: choose the highest-priority dependency-unblocked item with a testable end state. Limit change scope; write a small plan if complex.
3. RESEARCH: confirm current APIs/versions/licenses on official docs when uncertain; record sources, pin compatible dependencies, avoid guesswork.
4. IMPLEMENT: make a thin vertical slice with typed boundaries, structured data, explicit UI states, migrations and accessibility.
5. VERIFY: lint, typecheck, unit tests, provider-contract tests, database migration tests, API tests, frontend E2E, media probe and manual smoke check as applicable.
6. CHALLENGE: test failure modes: lost power, 6 GB OOM, bad output, invalid JSON, unavailable model, wrong aspect ratio, disk full, corrupted MP4, duplicate job, conflicting canon.
7. FIX: reproduce, root-cause, add regression test, repair, rerun. Max 3 consecutive attempted fixes per same unidentified blocker; then record and switch to a dependency-independent task.
8. UPDATE: edit `ops/BOARD.md`, `ops/PROGRESS.md`, `ops/DECISIONS.md`, `ops/BLOCKERS.md`, `ops/HANDOFF.md`; include actual command/results and next step.
9. CHECKPOINT: make a descriptive local commit for verified coherent changes if Git/permissions permit. Never change remote branches without approval.
10. REPEAT while session/resources/authorized work allow. Treat unfinished tasks as unfinished rather than hiding them.

Do not implement an 'infinite loop' that blindly edits files; automatic iterations stop on operational or permission boundaries, and resumable state is written to disk. Do not claim background execution after the Codex session stops.

## Explicit approval boundaries
Approval required for: purchases, billable APIs, any publishing/upload of user content, real social media posting, third-party service login, more-than-small model downloads (default >1 GB aggregate), installing drivers/toolchains that alter the system, firewall or OS security changes, deleting originals, bulk cleanup outside app-owned temp, exposing servers beyond 127.0.0.1, accepting new restrictive terms or writing to third-party repos. In test/dev operate on sample data.

## What counts as real vs simulated
- **Mock** provider: deterministic colored/sample media with conspicuous MOCK watermark and metadata `is_mock=true`. Useful for pipeline tests ONLY.
- **Real local** provider: end-to-end generation from an installed model observed, outputs probed, resource usage logged.
- **Cloud** provider: only documented authorized API; never script consumer websites to harvest free credits without explicit permitted API/terms.
- UI must always show actual provider, stage, duration, quality tier and error messages; no false 'AI video rendered' success from placeholders.

## Coding discipline
- Python 3.11 backend, TypeScript strict frontend unless verified incompatibility documented. Prefer FastAPI, Pydantic v2, SQLite migrations, SQLAlchemy or equivalent, a durable in-process/single-host worker; use FFmpeg through safe argv subprocess calls.
- Keep big optional AI runtimes in isolated environments/processes. No hard requirement that every dependency install at app startup.
- Provider interfaces for StoryLLM, Image, Video, TTS, Sound and Renderer. Do not couple app code to WanGP internals or fork vendor repo by default.
- Use one VRAM-heavy inference job at a time on 6 GB GPU, release models between stages where needed; don't run the local LLM with the image/video model concurrently by default.
- Keep reproducible project manifests and stable file IDs, hashes, lineage, seeds, prompt template versions; avoid raw paths as public API identifiers.
- Use bounded retries, idempotency keys, atomic writes, checksums, per-stage checkpoints, heartbeat/stale-job recovery, cancellation and pause/resume.
- Secrets outside repo; log scrubber; localhost by default; narrowly scoped file access; sanitize shell paths; no shell interpolation.
- Introduce tests at the same time as features. Track exceptions explicitly; no silent 'pass'.

## Completion gates
A milestone is complete only when acceptance tests, error states, UX path and docs pass, recorded in `ops/PROGRESS.md`; GPU-dependent items need actual inference evidence, not promises. Final response shall be concise but list shipped features, verified checks, known blockers, manual approval items, exact run commands and next task.

## First session prep
Read `PLANS.md`, `docs/12_IMPLEMENTATION_BACKLOG.md`, `checklists/PHASE_GATES.md` and `docs/00_RESEARCH_GATES.md`. Establish facts before selecting real backends. Avoid dependency explosion: deliver a coherent MVP before multi-model orchestration.
