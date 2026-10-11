# Handoff — 2026-10-12

Status: ACTIVE DEVELOPMENT; full app unfinished. Initial demo pipeline implemented and observed. Real CPU plan smoke passed; real GPU image/video untested. Original blueprint preserved.
Branch: main, initial local checkpoint pending after current regression. Record final commit before ending session.
Environment: Windows11, RTX3060Laptop6GB, 16GBRAM with low free memory; Node24.19/npm11.17; .venv uses existing Python3.12.14. App-local FFmpeg tools and optional tinyCPU story model in ignored tools/. No system changes.

Working commands:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1 -Browser
.venv/Scripts/python.exe -m scripts.story_smoke
```

Live development server started by Codex at 127.0.0.1:8765; it initially loaded code before newest settings/provider changes. Restart before verifying new backend changes (`scripts/stop.ps1`, then `scripts/run.ps1 -NoBrowser`). Do not kill unrelated processes.

Tests observed: 10 API/story +9 media/pipeline +1 hardkill; after process containment targeted2 passed. Edge Playwright3 passed, Vitest2, frontend build/lint, npm audit0. Full new regression currently running; inspect actual outputs before recording it. CPU story initially failed three schema validations, then real structured plan passed11.078s with nested schema wrapper.

Next exact tasks: F2.01 finish CPU screenplay/semantic validation and provider settings UI contract; F4.02/03 stream/recovery controls regression; F8.01 smoke launcher. Then choose licensed GPU models and seek concrete approval for >1GB downloads after exact sizes/runtime risks documented. Do not silently download GPU runtimes.

Important files: studio/{api,storage,worker,story,local_story,media,processes,providers,vendor_bridge}.py; client/src/App.tsx and style.css; tests/; docs/SOURCE_REGISTER.md; ops/evidence/.

Known caveats: full prop/knowledge/world-time canon, retcon/shot editing, backup restore, guided downloads, clean-user install and cinematic QA incomplete. WanGP contracts tested with fake session only. UI must not claim configured=hardware verified. CPU plan has weak meta-world-rules; stronger models require further proof.
