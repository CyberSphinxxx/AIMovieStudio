# 01 — Product requirements document

## Vision
A first-time user enters **one idea** and selects an optional mode; software becomes screenwriter, showrunner, casting director, art department, cinematographer, animator, sound designer and editor. Output is a playable, editable, provenance-tracked short movie or episodic series. Default path requires no prompt engineering or external paid service.

## Who and why
Solo creators, hobby filmmakers, social media storytellers, horror creators, anime/murim/historical fiction fans, educators; user target has RTX 3060 laptop 6 GB, 16 GB RAM and limited budget. Primary metric: prompt-to-first-valid-MP4 with minimal intervention; quality and continuity measured separately.

## Modes
- **Short clip**: 5-30 seconds, 1-6 shots, fast turnaround. Defaults to visual action with optional sound.
- **Short drama**: 30-180 seconds, dialogue/narration, clear hook/conflict/payoff. Social formats.
- **Short movie**: 1-10 minutes initially, acts, several locations and characters; avoid promising fast 10-minute generation.
- **Series**: project bible; episodes/seasons, beat outline and planned finale; user may ask for N episodes × target duration. Default render one episode at a time while preplanning whole season. Preserve long-term story memory.
- **Trailer/teaser (later)**: derive from preplanned assets.

## Supported formats
Portrait 9:16 (default 1080×1920 export if requested, generation native lower res); landscape 16:9, square 1:1, custom. Output target FPS selectable 24/25/30 with generation FPS separate from export FPS. Respect safe areas for subtitles, thumbnails, platform crop and black bars. Do NOT merely stretch portrait clips to landscape. For differing frame ratio, regenerate or intelligently crop with preview. Default render resolutions/lengths driven by measured hardware, then encode/upscale to export target with clear labeling.

## One prompt requirements
Input minimum one meaningful idea. Optional: title, mode, target episodes, duration, format, language (English default), style (photorealistic default), rating/tone, voice/dialogue preference, quality/time/resource profile, local/cloud consent. Sensible defaults visible. Button 'Create movie'. Save prompt immediately before expensive steps. Offer 'Generate sample' preset. Never force advanced configuration.

## Core capabilities — MUST
- AI develop premise -> outline -> screenplay -> character arcs/ending -> scene list -> cinematic shot list.
- Auto create/reuse character sheets, location images, prop references, visual style bible; identity locking.
- Auto generate one or more images for every shot then animate into short videos; preserve versioned inputs/outputs.
- Synthetic narrated/dialogue speech with language/voice consistency, optional subtitle generation, SFX and music/ambience; distinct dialogue and narrator tracks.
- Programmatic edit: frame trim, transitions, soundtrack mixing/ducking, fades, subtitles, title cards where needed; MP4 export and project reopen.
- Durable series canon and changes/retcons tracked; detect conflicts between scripts or episodes.
- Progress UI, ETA only if measured and clearly tentative; cancel/pause/retry/resume; errors actionable.
- Configurable free local providers; no mandatory API key, login, subscription, telemetry, or cloud account.
- Mock/demo works without a GPU, clearly labeled. Real outputs claim only when model inference performed.
- Local API bound to localhost; limited model downloads approved by user.

## SHOULD after verified MVP
- per-shot regeneration, timeline editor, prompt edit, swap actor/costume, voice reassignment, subtitle editor, configurable render presets, batch episode queue, continuity compare, thumbnails, backup/export project bundle.

## COULD later
- storyboard grid and optical consistency agent, LoRA training with explicit rights, GPU worker on LAN with authentication, approved cloud API, collaborative storytelling, camera-controlled generation, multilingual dubbing, publishing assist (manual final approval), model marketplace with vetted license badges.

## Quality bar
Movie has a cohesive beginning/middle/end or an intentional episodic cliffhanger (ending already planned); no blank clips, malformed audio, missing media, dialogue cut off by next scene, portrait cropping that decapitates faces, 2 characters switching identities, or unexplained costume jumps unless flagged. Automated detectors can identify obvious failures but not guarantee cinematic perfection; optional human review should remain accessible.

## Success metrics
- Steps from new project to working generation: <=3 interactions excluding first install/approval.
- Guided install: user does not manually edit Python scripts/JSON.
- Mock pipeline: one click creates valid 30-sec sample MP4 in E2E test with clearly fake media.
- Real provider: at least 1 successful image and 1 short video on target hardware, recorded with exact settings.
- Resume: killing worker mid-job and restarting does not lose completed shots or duplicate commits.
- Series: 10 episodes planned, fixed main-character IDs, seeded plot consistency, end known; after restart next script uses canon.
- Aspect: exported MP4 dimensions match selection, tested using `ffprobe`.

## Constraints/tradeoffs
- 6 GB VRAM is a hard resource constraint. Favor small shot counts and sequential GPU processing.
- 16 GB RAM and SSD free space may prevent certain optimizations; must check rather than assume.
- Free-first means 0 mandatory recurring cloud cost, not 0 electricity/disk/hardware use.
- Massive movies render slowly, possibly many hours/days; no SLA or fabricated completion time.
