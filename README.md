# AI Movie Studio

A private, local filmmaking workspace for Windows. Enter one idea to run the development pipeline through story planning, references, shots, synthetic speech, ambience and a playable MP4. Projects and completed steps survive restarts.

**Current status: working internal development build. Not the complete production application.** Demo scripts are deterministic templates and demo visuals are abstract, conspicuously watermarked motion storyboards. Real GPU image/video generation has not passed its hardware gate. No cloud service, account or API key is required.

## Launch on this workstation

Double-click `StartStudio.cmd`, or run from the repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
```

Open http://127.0.0.1:8765. Type an idea and press **Create movie**. The default is a 30-second portrait development demo. Optional Film/Drama/Series and format controls are in the composer. Series plans have a finite ending; render episode 1, then choose episode 2 in Episodes. Export provides MP4, timed SRT when speech is enabled, and JSON provenance.

Double-click `StopStudio.cmd` to stop the server. Relaunch to resume interrupted work. Pause finishes the current atomic step; Stop production cancels that job permanently and preserves its assets. Failed steps have a finite retry budget. A changed or missing source asset blocks export with diagnostics.

## Setup from source

Python 3.11+ and Node 22.12+ are prerequisites. Verification here used an existing Python **3.12.14** in an isolated `.venv`; Python 3.11 was absent. No drivers or global toolchains were installed.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Development
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
```

Setup downloads pinned Python/npm dependencies and an app-local FFmpeg/FFprobe bundle (~115 MB). It does not install AI weights. Runtime works offline after dependencies are prepared.

Developer API: `.venv/Scripts/python.exe -m uvicorn studio.api:app --host 127.0.0.1 --port 8765`. Frontend: `cd client; npm run dev`. OpenAPI is at `/docs`.

## Local story/provider setup

The Ollama adapter uses its documented localhost structured-output API, bounded JSON repair, and immediate model unload. Select an installed model in Settings, then request Real local in Creative settings. Missing providers fail honestly and retain the idea/story. Real image/video setup remains a separate licensing, download and hardware gate.

An optional tiny CPU feasibility model can be prepared with `.venv/Scripts/python.exe scripts/setup_story.py` (~491 MB model + ~20 MB runtime). It uses official Qwen GGUF weights (Apache-2.0) and pinned llama.cpp CPU binaries (MIT), verified by source checksums. This is a small inference experiment, not a promise of strong scripts. See `ops/HARDWARE_PROOF.md` for observed results.

## Verify

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser
```

Start Studio first for browser tests. Tests use installed Microsoft Edge. Backend tests cover portrait/landscape/square MP4, actual installed Windows speech, series continuity, duplicate requests, path/origin protections, interruption and hard process termination. Browser tests create/download/play a demo, exercise missing-model errors, inspect 320–1920px layouts and run automated accessibility checks. They do not establish screen-reader accessibility or cinematic quality.

## Storage and privacy

`data/studio.sqlite3` stores projects, episodes, jobs, manifests and append-only events with WAL and transactional migrations. Media lives under UUID folders in `data/`; hashes and parent IDs pin lineage. `STUDIO_DATA` overrides the data root. Keep SQLite and its WAL files together when backing up a running app; stop the server before copying the entire directory. Generated source media is never automatically deleted.

All services bind to localhost. Cross-origin browser writes and external hostnames are rejected. Prompts remain data; neither model output nor user text is evaluated as code. FFmpeg uses argv and confined files. Disk reserve defaults to 1 GB. One worker holds an OS lock, preventing concurrent GPU work in the same data root.

## Known incomplete work

- Real GPU references/video, guided model setup and measured 6 GB inference.
- Comprehensive canon rules for knowledge, props, costume changes and world-time flashbacks; current checks cover stable identities, prior outcomes and death contradictions.
- Editing/regeneration, version branches, custom/native HD exports, backup import/restore and advanced quality evaluation.
- Clean-machine packaging, dependency/license release review, full GPU OOM testing and cinematic review.

The copied root specs, backlog and acceptance checklists define the full goal. The original blueprint folder is preserved untouched. See `ops/BOARD.md`, `ops/PROGRESS.md`, `ops/BLOCKERS.md` and `ops/HANDOFF.md` for truthful implementation status and the exact next task.
