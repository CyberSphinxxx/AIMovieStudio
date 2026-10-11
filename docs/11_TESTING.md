# 11 — QA strategy, test pyramid and release proof

Every feature requires automated evidence. The code must pass on systems WITHOUT a GPU through mocks; actual GPU capability is a distinct hardware acceptance gate.

## Test layers
1. **Static**: TypeScript strict, ESLint, Prettier, Ruff, mypy/pyright where practical, dependency checks, secret scanning, formatting, import cycles.
2. **Unit**: story schema validators, stable IDs, planned ending logic, chronology, asset lineage, prompt templates, aspect conversions, filename/path sanitization, state machine, retry classifier, media manifests.
3. **Database**: migrations from blank and previous fixture DB, transaction rollback, concurrent worker claim, orphan lease recovery, idempotency, backups/restore, revision conflicts.
4. **Contract**: fake provider and WanGP adapter protocol (do not require model), timeouts/progress/cancel/error translation, typed capabilities, invalid results detection. Provider interfaces pinned to observed docs.
5. **API**: create/project/read, SSE event reconnect, pause/resume/cancel, invalid prompts, Unicode, invalid path, missing model, user configuration, HTTP statuses, size limits.
6. **Media integration**: generate test pattern + audio via FFmpeg, assemble valid 9:16 and 16:9 files; verify ffprobe streams, width/height, duration, audio and subtitles. Test corrupt clip rejection.
7. **Frontend E2E**: Playwright new project single prompt, mode/orientation, recent projects, live progress states, failed job retry, history/series screen, preview/export/download, keyboard, mobile viewports.
8. **Real hardware smoke**: short actual image and video outputs on 6 GB GPU with exact settings and resource measurements. Maintain manual repeatable commands and non-sensitive logs, include model IDs and artifacts when safe.
9. **Cinematic QA**: compare character reference, subject count, visible scene cut, lens/light consistency, audio timing; use automated thresholds as advisory and human spot-check to confirm.

## Required end-to-end fixtures
- F01: 30-sec 9:16 social short, one actor, narration, SFX, 6 generated/mock shots, full MP4.
- F02: 60-sec 16:9 horror short, two locations, distinct shot compositions.
- F03: 6-episode season with ending preplanned, reusable protagonist, episode 2 continuation after app restart.
- F04: 2 main characters with distinct voices, dialogue/subtitles, safe music-free export.
- F05: interruption halfway through 10-shot render; restart and reuse 5 completed clips, no duplicates.
- F06: GPU OOM first attempt; lower-memory profile, bound retries, explicit result; never infinite loop.
- F07: corrupt MP4, disk full, missing model, non-ASCII file name, app folder relocated, simultaneous produce requests.
- F08: user changes episode 1 event contradicting episode 4; dependency invalidation and revision prompt.
- F09: reject forbidden external path/access, malformed JSON, model output with prompt-injection instructions.
- F10: a second project runs without stealing GPU or corrupting the first.

## Acceptance test script (to implement)
`npm run lint && npm run typecheck && npm run test && npm run test:e2e` in client; `pytest` and `ruff check` in backend; `python scripts/check_media.py --manifest ...` for generated assets. A `make verify`/`scripts/verify.ps1` convenience runner should return nonzero on failure and print clear summary. CI runs non-GPU checks; GPU tests tagged opt-in to avoid false green.

## Test honesty
A mock-generated MP4 proves workflow and editing, not generative model realism. Each test report records `environment`, `backend`, `is_mock`, `model`, `actual hardware`, `status`. A broken test is never silently skipped without reason and follow-up issue. Keep fixture media tiny and legally distributable. Capture Playwright screenshots for UI testing and inspect visibly for overflow.

## Release exit criteria
- Required P0 flows pass end-to-end on Windows.
- GPU integration succeeds OR is transparently marked unsupported with guided setup, while preserving demo proof.
- All required data survives app restart and project export/re-import.
- No arbitrary code execution through prompts, path traversal, secret exposure, surprise uploads or billable external actions.
- Installer/launcher tested from clean user account or fresh VM profile, without admin demands if feasible.
- UI usability: novice reaches first project easily, understandable recovery actions and visible resource limits.
