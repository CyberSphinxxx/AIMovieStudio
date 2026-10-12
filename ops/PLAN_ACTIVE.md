# Active plan — 2026-10-12
Task/ID: F1.04 setup and resource diagnostics.
Behavior: Settings distinguishes installed files from proven inference, shows CPU RAM readiness and the last observed Windows GPU runtime block, and lets users refresh measurements without overwriting unsaved preferences.
Ground truth:529f026 verified draft edits/history and real CPU installed but refused2.44GiB RAM; GPU actual WinError4551/CodeIntegrity3077. Provider rows currently call configured/installed stacks Available. GPU runtime status should be app-owned machine evidence, not an unbounded import on page load.
Slice: Small persisted last-check summary from bounded smoke, pure provider-readiness classification, refreshable Settings diagnostics and precise labels. Keep available as discovery signal; no claim of6GB fit or quality. No automatic model loading/downloading or OS changes.
Tests: Installed/absent/low/unknownRAM, failedOScheck versus untested/otherinstall, stale/invalid reports, refresh preserves form selections; current browser paths still pass and visual Settings review.
Recovery: Additive JSON status/readiness fields; absence/corruption means untested, never inferred success. Existing jobs/config preserved.
Progress: Implemented statuses/summary/refresh. Full97 backend/2 Vitest/5 Edge passed, then8 targeted summary guards and final5 Edge after scroll fix passed. Visual Settings/Axe checked.
Result: Setup readiness slice DONE_VERIFIED; GPU inference/CPU1.5B quality and guided full installation remain blocked/unproven.
