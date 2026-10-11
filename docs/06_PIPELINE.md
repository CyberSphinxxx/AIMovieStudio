# 06 — Complete production pipeline

## Job graph
`PROJECT_INIT -> IDEA_ANALYSIS -> ENDING_AND_SEASON_PLAN -> WORLD_CAST_BIBLE -> EPISODE_SCRIPT -> SCENES -> SHOT_PLAN -> REFERENCE_IMAGES -> SHOT_KEYFRAMES -> VIDEO_CLIPS -> TTS -> SOUND_FX_AND_MUSIC -> SUBTITLE_ALIGN -> ASSEMBLY -> VIDEO_QA -> EXPORT -> CANON_CHECKPOINT`.
Use explicit prerequisites, outputs, versions and skip conditions, not a single monolithic `createMovie()` script.

## Stage details and acceptance
1. **Project init**: project ID, original prompt, mode, target aspect, export profile, consent profile and disk quota; immediately save.
2. **Script plan**: complete narrative structure with ending, episode arcs and normalized script; validate schema, tone, character identities.
3. **Visual bible**: image prompts, reusable reference variants, consistent visual tone.
4. **Shot director**: shots sized to provider max seconds, motion complexity, camera style, VO/Dialog matching, no surprise scene cuts; durations sum to target within configurable tolerance. Allow B-roll stills for pacing only if labeled.
5. **Reference/keyframe**: images generated and validated; source hashes tied to prompts, provider and seed.
6. **Video**: one GPU job at a time; prefer image-to-video; 3-5 s initially; cap max attempts (e.g. 2 normal + 1 low-memory). Errors typed `OUT_OF_MEMORY`, `MISSING_MODEL`, `INCOMPATIBLE`, `TIMEOUT`, `BAD_OUTPUT`, `CANCELLED`. Keep diagnostics.
7. **Audio**: TTS line by line with speaker voice binding, concatenate with scene timing, add licensed ambience/SFX/music with ducking; silence is a better fallback than unlicensed music. Dialog may be offscreen/narrated to avoid lip-sync claims until validated.
8. **Subtitles**: from actual finalized speech timing, configurable style, safe margins; include selectable sidecar SRT even if burn-in disabled.
9. **Edit/grade**: normalize pixel format, dimensions, frame rate, timestamps, loudness; assemble FFmpeg filter graph or safe concat workflow; transitions only where intentional. Prevent audio overlap/clipping.
10. **QA**: ffprobe playable duration/dimensions/codec/tracks; detect black frames/silence/duplicate shot, basic visual glitches when feasible; check story/asset version dependency; human review optional.
11. **Export**: MP4 H.264/AAC as most broadly compatible; name sanitized; render via temp file, probe, checksum then atomically publish. Keep edit decision list / project JSON.
12. **Checkpoint**: mark episode rendered and canon snapshot committed; do not rewrite approved narrative events accidentally.

## Auto-regen decision policy
Retry only for measurable failure: missing frame, corrupted container, unacceptable aspect, severe obvious distortion threshold, face/reference mismatch confidence when reliable. Hard limit per stage and project to avoid waste (e.g. 2 retries then choose degraded fallback or review state). Do not make blind aesthetic retries indefinitely. 'Best shot selected' requires scoring evidence, not arbitrary latest.

## Output quality profiles
- **Draft**: 480p native if provider supports, minimal steps, 3-5 sec shots, fast first render.
- **Balanced**: measured stable native res, conservative res/steps, normal audio and quality tests.
- **Cinematic**: optional high-quality model/upscale and increased iterations, gated by available resources. Do not promise native HD generation on 6 GB GPU.
- Export size separate from native generation; UI identifies upscaling/interpolation to avoid false attribution.

## Short vs series behavior
Clip: 1-6 shots; can skip complex episode bibles but still saves entity reference IDs. Drama: hook, setup, escalation, payoff, 30-180 sec. Film: 3-act or alternate structure. Series: complete planned arc before Episode 1 video; prep future scripts in background only while session active, do not compete for VRAM.

## Provider outage policy
If optional cloud offline, fall back to local only if compatible. If local real video backend unavailable, fail transparently or offer DEMO watermarked static animation; do not falsely declare successful AI movie. If audio backend unavailable, create silent video with explicit incomplete badge and retry option; configurable whether 'final' requires audio.
