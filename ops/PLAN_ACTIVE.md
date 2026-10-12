# Active plan — 2026-10-12
Task/ID: F7.03 optional future-draft editing.
User behavior: Edit scene action/camera/spoken lines/speaker in a saved unproduced episode. Saves retain old draft history and optimistic revision; later drafts require review. Normal one-button production remains unchanged.
Ground truth:56ce212 CPU proposal/profile verified81/2/5 (plus10 download fixtures); real generation gates blocked/pending. Saved season drafts exist; editing is absent. Existing worker validates a saved DRAFTED script before production.
Slice: Typed sparse shot edits API; selected episode must have saved script/no production job; project cannot be queued/running/paused. Transaction checks revision, full script/declared continuity, stores append-only previous version and changes, increments revision, marks later drafts REVIEW_REQUIRED. Optional Story view editor with preserved unsaved values and accessible labels.
Safety: No media deletion/overwrite; refuse already produced/active scripts. No model downloads. Earlier planned changes are simulated solely for draft validation, never committed canon. Stable identities/runtime retained.
Tests: API stale/active/produced/unknown shot/speaker/duration content, history/restart, future invalidation, production consumes edited script unchanged, actual Edge edit/reload/episode2 export, responsive/keyboard.
Recovery: Existing script receipt retained; append-only edit event preserves original; future production rechecks completed canon.
Progress: Implemented typed patches/history/UI; initial exact-label browser failure fixed with explicit IDs. Full91 backend, latest14 story/edit,2 Vitest and final5 Edge passed;390px visual/Axe reviewed.
Result: Saved future-draft editing slice DONE_VERIFIED; full editing/regeneration remains incomplete; CPU approval remains pending.
