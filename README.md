# AI Movie Studio

A private, local filmmaking workspace for Windows. Enter one idea to run the development pipeline through story planning, references, shots, synthetic speech, ambience and a playable MP4. Projects and completed steps survive restarts.

**Current status: working internal development build. Not the complete production application.** Demo scripts are deterministic templates and demo visuals are abstract, conspicuously watermarked motion storyboards. Real GPU image/video generation has not passed its hardware gate. No cloud service, account or API key is required.

## Launch on this workstation

Double-click `StartStudio.cmd`, or run from the repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
```

Open http://127.0.0.1:8765. Type an idea and press **Create movie**. The default is a 30-second portrait development demo. Optional Film/Drama/Series and format controls are in the composer. Series plans have a finite ending; render episode 1, then choose episode 2 in Episodes. Export provides MP4, timed SRT when speech is enabled, and JSON provenance.

For a series, Creative settings includes **Prewrite every episode**. Each screenplay is a separate resumable step. Future drafts are planned fiction; canon records only completed episodes. Saved drafts are validated against current canon before production.

New longer productions write in saved sections of at most four shots. Interrupted writing resumes at its next unfinished section; assembly checks the entire runtime and declared continuity before audio or visuals. Previously persisted jobs retain their original checkpoints. This bounds requests and preserves work; it does not establish the tiny CPU model's writing quality.

Speech is measured before visual generation in new productions. A line that would need more than 1.15× tempo correction fails with its measured duration; the studio preserves the raw voice rather than racing or truncating dialogue. Export → **Audio stems for editing** downloads original voices, scene audio, ambience and the mixed WAV. These hashed source assets are included in portable backups.

Double-click `StopStudio.cmd` to stop the server. Relaunch to resume interrupted work. Pause finishes the current atomic step; Stop production cancels that job permanently and preserves its assets. Failed steps have a finite retry budget. A changed or missing source asset blocks export with diagnostics.

## Setup from source

Python 3.11+ and Node 22.12+ are prerequisites. Main-app verification here uses Python **3.12.14** in an isolated `.venv`. The optional GPU installation has a separate app-owned Python **3.11.14**. No drivers or global toolchains were installed.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Development
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
```

Setup downloads pinned Python/npm dependencies and an app-local FFmpeg/FFprobe bundle (~115 MB). It does not install AI weights. Runtime works offline after dependencies are prepared.

Developer API: `.venv/Scripts/python.exe -m uvicorn studio.api:app --host 127.0.0.1 --port 8765`. Frontend: `cd client; npm run dev`. OpenAPI is at `/docs`.

## Local story/provider setup

The Ollama adapter uses its documented localhost structured-output API, bounded JSON repair, and immediate model unload. Select an installed model in Settings, then request Real local in Creative settings. Missing providers fail honestly and retain the idea/story. Real image/video setup remains a separate licensing, download and hardware gate.

An optional tiny CPU feasibility model can be prepared with `.venv/Scripts/python.exe scripts/setup_story.py` (~491 MB model + ~20 MB runtime). It uses official Qwen GGUF weights (Apache-2.0) and pinned llama.cpp CPU binaries (MIT), verified by source checksums. This is a small inference experiment, not a promise of strong scripts. See `ops/HARDWARE_PROOF.md` for observed results.

Select **Small CPU feasibility model** in Settings to use that installed runtime. It unloads after each story step. The observed worker persisted a real plan and screenplay, then stopped at missing image/video setup. Some attempts exhausted schema repairs; this tiny model remains a writing feasibility test.

The user approved the bounded private GPU installation in `docs/GPU_INSTALL_PROPOSAL.md`. Its source, isolated runtime and image weights are installed with recorded checksums. **The first runtime smoke failed before inference: Windows Application Control blocked PyTorch's CUDA DLL.** No real GPU image or video has been generated. Video weights remain gated on a reviewed image test. See `ops/HARDWARE_PROOF.md` and `ops/APPROVALS.md`. The studio does not alter Windows security policy. Vendor dependencies also have unresolved audit advisories and are not release-certified.

## Verify

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser
```

Start Studio first for browser tests. Tests use installed Microsoft Edge. Backend tests cover portrait/landscape/square MP4, actual installed Windows speech, series continuity, duplicate requests, path/origin protections, interruption and hard process termination. Browser tests create/download/play a demo, exercise missing-model errors, inspect 320–1920px layouts and run automated accessibility checks. They do not establish screen-reader accessibility or cinematic quality.

## Storage and privacy

`data/studio.sqlite3` stores projects, episodes, jobs, manifests and append-only events with WAL and transactional migrations. Media lives under UUID folders in `data/`; hashes and parent IDs pin lineage. `STUDIO_DATA` overrides the data root. Generated source media is never automatically deleted.

Settings → **Download studio backup** exports a consistent database snapshot and saved media with hashes. Models, machine-specific provider commands/settings, unfinished files and server logs are excluded. Backup archives have a 20 GB limit and require a 1 GB free-space reserve. Restoring never overwrites an existing folder or starts imported jobs. A command-line alternative:

```powershell
.venv/Scripts/python.exe -m scripts.backup create --archive studio-backup.zip
.venv/Scripts/python.exe -m scripts.backup restore --archive studio-backup.zip --destination data-restored
```

To inspect a restored studio, stop the existing server, set `$env:STUDIO_DATA` to the absolute `data-restored` folder in that PowerShell session and run `scripts/run.ps1`. Review Settings before resuming paused jobs. Completed media and story IDs are preserved. Keep the original archive and data until you have inspected the restored copy.

All services bind to localhost. Cross-origin browser writes and external hostnames are rejected. Prompts remain data; neither model output nor user text is evaluated as code. FFmpeg uses argv and confined files. Disk reserve defaults to 1 GB. One worker holds an OS lock, preventing concurrent GPU work in the same data root.

## Known incomplete work

- Real GPU references/video, guided model setup and measured 6 GB inference.
- Declared prop ownership, character knowledge, location/life changes and episode-start flashbacks are checked. Fine-grained world time, costumes, relationships and semantic contradictions in prose remain incomplete.
- Editing/regeneration, version branches, custom/native HD exports, graphical backup restore and advanced quality evaluation.
- Clean-machine packaging, dependency/license release review, full GPU OOM testing and cinematic review.

The copied root specs, backlog and acceptance checklists define the full goal. The original blueprint folder is preserved untouched. See `ops/BOARD.md`, `ops/PROGRESS.md`, `ops/BLOCKERS.md` and `ops/HANDOFF.md` for truthful implementation status and the exact next task.
