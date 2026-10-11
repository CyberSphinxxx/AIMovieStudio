# 10 — Audio, editing, final film and export correctness

## Script-driven audio
Voice plan maps `character_id -> voice_profile_id` stable across episodes. Scene lines carry sequence, speaker ID, emotion/style hint, language, text and expected timing. Generate speech sequentially on CPU where possible, preserve per-line WAV and exact duration; support narrator voice separate from characters. Avoid cloned real-person voices without rights/consent and never infer that a random audio sample is authorized.

## Placement
Align dialogue and action to shot duration. If speech overflows, adjust shot length/insert planned cutaway/trim pauses or regenerate voice; **do not speed every line arbitrarily or cut mid-word**. After wave assembly, create SRT/VTT using TTS timings or alignment, not fabricated word timings. Keep voices, foley, ambience and score as separate stems before mix. Normalize LUFS and true peaks to practical playback targets and avoid clipping.

## Non-dialogue films
When genre suggests visual storytelling, choose environmental sounds + optional narrator instead of mouth-animation. Include atmos (wind, footsteps, room tone, birds, thunder) tied to time/place. No mandatory paid sound model; can use local cleared assets. Empty music library? Render without music, preserve movie completion quality with atmosphere where rights are clear.

## Video assembly
Use FFprobe for every clip before inclusion. Normalize resolution/pixel format/fps, enforce target aspect using fit+crop/letterbox policies, color/timebase and audio sample rate; never stretch. Trims and transitions are generated from scene and shot EDL. Preserve soundtrack continuity at cuts where intentional; scene transitions not universally fades. Titles and subtitles are readable and respect orientation safe margins. Create MP4(H.264/yuv420p, AAC) with `-movflags +faststart` and playable metadata; optional lossless/archival export later.

## 9:16 portrait vs 16:9 landscape
Both have shot planning and keyframe composition rules. Shot-native resolution may be lower, and export resolution may be higher by resampling; UI describes 'upscaled export'. Output must match exactly the selected width/height and no accidental frame rotations or black strips unless necessary as explicit aspect-safe fallback.

## Fallback modes
If visual AI can't render, deterministic demo media has a 'Demo — not AI generated' overlay on every shot. If AI video inference fails mid-movie, final status is PARTIAL unless user explicitly accepts a still-animation replacement; original attempt manifests preserved. If voice absent, use silent track only with warning and not pretend dialogues played.

## QA for each export
- `ffprobe` status=0; H.264/AAC streams when requested; orientation pixels correct; expected duration tolerance.
- No missing shots relative to validated EDL, duplicate time overlays, black beyond intentional transitions, audio clipping or missing end fade when specified.
- Path cannot escape project root, name sanitized, hash and manifest stored.
- Test with 9:16, 16:9, subtitles off/on, narration off/on, Unicode titles, silent scenes, 1-frame edge cases and FPS conversion.
