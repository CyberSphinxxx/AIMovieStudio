# Handoff — 2026-10-12

ACTIVE DEVELOPMENT. The complete application is unfinished. Branch: main. Previous HEAD: 6731e46; previous implementation: c8af09b. Verified implementation checkpoint: dd1da30 (durable alternate-aspect exports). No remote changes or original deletion; blueprint preserved.

Environment: Windows 11 Home, RTX 3060 Laptop (6144 MiB), driver 610.88, 16 GB RAM. Main .venv Python 3.12.14; Node 24.19/npm 11.17. Separate app-owned GPU Python 3.11.14/Torch 2.10+cu130; app-local FFmpeg; llama.cpp CPU b11558 and Qwen 0.5B/approved 1.5B. Latest available RAM: 0.24 GiB, 98% load. Heavy work stopped. Current server is ready at http://127.0.0.1:8765 with new source, database ok and worker alive. It was absent before normal launch; cause unknown.

Working: one-idea development pipeline through deterministic story, references, shots, audio and valid MP4, with conspicuous mock labels. Finite series planning; stable reference IDs and export-only declared canon; durable four-shot screenplay sections; serialized worker, leases, receipts, hashes, pause/cancel/bounded retries. Saved future/current pre-media editing retains history and originals, with revision guards and optional story review. Actual Windows speech has a timing cap and downloadable source WAVs. Hashed backup/CLI restore, typed Settings/readiness/refresh and mobile/keyboard/Axe checks are implemented.

New F6.05 slice: Export offers whole-frame portrait, landscape and square copies with black bars. No AI rerun. REFORMAT appends to the completed job, duplicate source/profile requests reuse the same stage, original checksum is pinned. AAC and subtitles are retained; two-thread FFmpeg validates and atomically publishes separate media/provenance. Original files and canon stay intact. Backup, receipt and hard-kill recovery verified. Open-folder/custom HD controls still remain. Imported REFORMAT steps require the current app version.

Latest verification: five new tests plus backup/review tests = 15 PASS in 26.43s; initial four PASS in 11.21s. Ruff, frontend lint, TypeScript and build PASS. One new Edge flow PASS (9.0s test, 12.6s total): MP4 download/persistence, unchanged canon/script, 390px layout and Axe. Mobile screenshot visually inspected. Logs: export-copy-tests.log, export-copy-regression.log, export-copy-browser.log/.json, export-copies-mobile.png, export-copy-resource-boundary.json. Historical full run: 105 backend/2 Vitest/6 Edge PASS; NOT rerun on this change because RAM collapsed. Historical browser-tests.json preserved separately from targeted export-copy-browser.json.

Approvals: User approved pinned private GPU installation/tests within 32 GB cumulative downloads/40 GB added disk, image PASS before video, and no system changes. Source/runtime/image weights installed. Ledger: 11,383,697,362 received bytes plus 5.6 GB conservative runtime/Python reservations. Actual API discovery smoke FAILED after 44.0s before inference: WinError4551 and CodeIntegrity3077 identify torch_cuda.dll blocked by Windows App Control. No native image/video, 6 GB fit or cinematic proof. Video weights NOT downloaded. No security-policy changes or bypass. Vendor 90 advisories and Pillow/Gradio constraint remain unresolved. GPU_INSTALL_PROPOSAL.md and APPROVALS.md are authoritative.

CPU: Separate approved 1.2 GB downloads/1.5 GB disk experiment is installed, exact hashes verified, 1,117,336,935 received bytes including notices. Existing CPU runtime reused. Profile cpu_1_5b: first test 7059fecb FAILED preflight in 0.062s at 2.44 GiB free RAM, zero inference samples. No 1.5B quality/fit claim. Qwen 0.5B failed manual quality; latest strict run f6b050ee failed three JSON repairs in 297.547s. Existing approval covers scripts.story_batch_smoke once at least 5 GiB RAM is free: ten-minute ceiling, stop below 2 GiB during sampling or after first failed section. User said they would close heavy apps/report ready; no explicit ready reply. No user apps killed.

OPEN F4.05: Unclassified first-read SQLite I/O after hard kill/restart, targeted run 14 PASS/1 FAIL in 44.43s. Preserved fixture: pytest-53/test_hard_kill_mid_ten_shots_p1/content with spaces/studio.sqlite3, integrity ok, status FRAME. Original extended code was not captured; nine later actual kills passed. Connection diagnostics now expose code/name. This is distinct from the identified startup SQLITE_IOERR_TRUNCATE initialization retry. No blanket read/write retry or WAL deletion. Capture exact extended code on recurrence before a targeted fix; max three unidentified fix attempts.

Run from repository:
```powershell
.\StartStudio.cmd
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser
.venv/Scripts/python.exe -m pytest tests/test_export_variants.py tests/test_backup.py tests/test_story_review.py -q
.venv/Scripts/python.exe -m pytest tests/test_crash.py -q
.venv/Scripts/python.exe -m scripts.story_batch_smoke
.venv/Scripts/python.exe -m scripts.backup create --archive studio-backup.zip
.venv/Scripts/python.exe -m scripts.backup restore --archive studio-backup.zip --destination data-restored
```
Run heavy verification only with adequate RAM. Story smoke requires the reviewed resource guard/readiness; GPU work needs a policy-compatible runtime and reviewed image gate. StopStudio.cmd targets only the owned server. No background development promised after the session ends.

Next: F4.05 extended-code reproduction when RAM permits; otherwise F8.02 graphical restore, F7.03 produced-asset versioning, or license inventory. Run the full new regression when resources permit. Real writing/image/video, hardware/OOM/cinematic QA, fine canon semantics, managed SFX/music, clean-machine packaging and release acceptance remain incomplete. Existing approval boundaries still apply.
