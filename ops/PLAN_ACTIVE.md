# Active plan — 2026-10-12
Task/ID: F6.05 durable alternate-aspect exports.
Behavior: Download a completed movie in portrait, landscape or square without rerunning writing, speech or AI footage; preserve original files/canon/provider labels.
Ground truth: serialized worker, hashed receipts, unique job per episode. F4.05 intermittent read I/O remains open, not repaired by this slice.
Research: https://www.ffmpeg.org/ffmpeg-filters.html checked2026-10-12 confirms scale decrease/divisible-by and centered pad. Fit complete frame with black bars; no cropping/HD claim.
Slice: typed REFORMAT appended to completed job, idempotent source/profile, no other unfinished jobs; pinned source/hash, two-thread argv FFmpeg, AAC/subtitle copy, probe/decode/atomic publish/receipt recovery/backup validation. Export UI separate download and provenance.
Files: export_variants/media/worker/api/backup; client App/types; API/media/recovery/backup/browser tests.
Safety: no models/downloads/system changes/deletions; scoped UUID files; one worker, bounded attempts, checksum and disk guards.
Exit: concurrent requests create one step; aspects/duration/AAC/subtitles retained; original hashes/canon unchanged; receipt and restored pending stage recover; browser download/mobile/Axe verified. Checks serial and resource-bounded.
Rollback: original files/steps untouched; current app required for new REFORMAT stages.
Progress:5 new tests;15 targeted export/backup/review tests PASS26.43s, Ruff/lint/type/build PASS,1 Edge PASS12.6s. Actual hardkill after receipt, recovery, backup resume, AAC packet hash/subtitle text/padding, concurrent duplicate requests, original/canon preservation verified. Mobile390px screenshot visually inspected; Axe PASS. Main server was absent, normal launcher startup PASS; current source loaded.
Result: Alternate-aspect slice DONE_VERIFIED against development media. Full suite not rerun at new RAM boundary0.24GiB/98%; prior105 backend/2Vitest/6Edge evidence remains historical. F6.05 overall IN_PROGRESS (open-folder/custom HD). Real inference and unclassified SQLite read blocker unchanged.
