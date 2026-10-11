# 13 — Cinematic quality rubric and autonomous review

Quality control must discriminate **syntactic success** (a file exists) from **film quality** (satisfying movie). These are different gates.

## Hard gates (machine-checkable)
- playable video/audio container, correct codec, supported pixel format, expected frame count/duration/tolerance, correct target aspect ratio, non-empty media, acceptable black/silence excluding intentional sequences, no manifest mismatch, all referenced assets verified.
- story plot state valid, dialogue speaker IDs exist, characters/props align with scene timestamps; no unsupported licensed media included.

## Soft review criteria 1-5 (document rationale and confidence)
Narrative coherence; hook/payoff; subject/face consistency; location continuity; lighting/color unity; plausible motion/anatomy; camera stability; dialogue intelligibility/voice identity; audio rhythm and ducking; shots paced to story; no unwanted text/watermarks; safe framing for 9:16. Weights differ by format: short social drama prioritizes opening hook and faces, atmospheric horror prioritizes sound and suspense. Never represent heuristic output as objective guarantee.

## Automated evaluator architecture
Begin with deterministic inspection and basic per-frame sampling; add model-assisted scoring only after benchmarks for hallucination/false positives. Use ensemble of cheap checks and thresholded warning. Any AI critic must return typed `{check_id,score,confidence,evidence_frames,explanation,recommended_action}`. If critic unavailable, preserve pass of hard tests but label cinematic review 'not performed'.

## Regeneration policy
Define `max_attempts` globally (e.g. 3/shot) and per-day compute ceiling in minutes/jobs. Small defects: edit, reframe, crop, trim. Severe face/action issue: regenerate using same pinned references, then alternate seed. Resource fault: downshift model resolution, release GPU and retry once. After capped failure: mark REVIEW_REQUIRED or PARTIAL, not `SUCCEEDED`. Never infinite loop.

## Human intervention optional, not required for primary path
No forced user review between every stage. Offer Advanced review after storyboard, script or before export; default automatically continues when hard checks pass. Users can repair/edit failed shots directly. Keep a high-visibility warning if export has unresolved issues.

## Measuring improvements
Keep a set of 5 representative movie prompts and their expected narrative constraints. Re-run clips after prompt/model changes and compare documented scores + manual review; archive before/after sample IDs, duration and model settings. Avoid cherry-picking 1 exceptional AI result as proof of reliability.
