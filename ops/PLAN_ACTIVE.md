# Active implementation plan â€” 2026-10-12

Task/ID: F6.01 dialogue timing and early validation.
User behavior: Spoken lines remain intelligible and complete; an overflowing line reports its measured duration before costly visual generation.
Ground truth: Checkpoint4327fa3 passed43 backend/2 frontend/5 Edge tests. soundtrack currently allows arbitrary stacked atempo speed-up; AUDIO is scheduled after all visual clips. Main app and speech use real Windows voices, GPU runtime OS-blocked.
Slice: Cap tempo correction at1.15x, preserve raw voice WAV and measured timing/rate metadata, fail clearly above cap. Schedule AUDIO immediately after SCRIPT for new jobs, before references/frames/clips; preserve existing job order/checkpoints. No model/OS changes or new dependency.
Tests: Actual Windows overflowing line refuses final soundtrack/trim; short real speech+subtitles still pass; worker audio failure creates no visual assets; existing recovery/backup/crash and frontend workflow regressions.
Recovery: Files/receipts immutable once committed; old jobs retain their ordered steps. Failure preserves raw speech and finite retry. No silent dialogue omission.
Progress: Implemented audio cap/early scheduling/source WAVs; real overflow and portable stems tests passed. Full regression uncovered/reproduced Windows startup SQLITE_IOERR_TRUNCATE, narrow bounded repair verified.
Result: Slice DONE_VERIFIED;53 backend/2 Vitest/5 Edge, lint/type/build and main audits passed. Broader audio voice-quality and alignment work remains open.
