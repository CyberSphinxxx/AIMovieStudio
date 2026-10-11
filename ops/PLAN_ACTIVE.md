# Active implementation plan — 2026-10-12

Task/ID: F2.03 durable bounded screenplay batches.
Behavior: Longer episodes write at most four shots per model completion. Each section is checkpointed before the next; restart reuses saved sections. Assembly validates complete runtime/continuity before audio/images. Season prewriting keeps independent episode sections and no future canon.
Ground truth:262c256 passed62 backend/2 Vitest/5 Edge. Actual tiny CPU still fails screenplay quality/schema; long scripts currently ask for up to120 shots in3500 output tokens. Reuse transactional ordered steps/receipts/backups.
Slice: New jobs add SCRIPT_BATCH/DRAFT_BATCH followed by existing SCRIPT/DRAFT assembly. Short scripts/persisted old steps keep their behavior. Bounded schema/prompt and previous section context, global shot IDs/change positions, per-section plus final validation, human stage labels.
Components: story provider/local inherited adapter; storage scheduler; worker assembly; UI status; interruption/continuity/long-script tests.
Safety/licensing: No downloads/packages/OS changes. Demo sections remain labeled fixtures. Real writing success/quality is a separate observed gate.
Exit:600s fixture schedules30 four-shot sections, exact120 shots/runtime; receipt recovery preserves outputs; malformed/missing/causally contradictory sections fail before visuals; season prewrite/reuse, full suite and browser pass.
Recovery: Additive stage names/payloads, no migration. Existing IDs/receipts stay valid. Backups include partial sections/paused jobs.
Progress: Implemented; initial backup stage allowlist failure repaired.23 targeted and full71 backend/2 Vitest/5 Edge passed.600s fixture receipt recovery/partial restore reused sections, malformed sections blocked before visuals.
Result: Durable batching slice DONE_VERIFIED with development fixtures; real writing quality remains unproven and phase2 incomplete.
