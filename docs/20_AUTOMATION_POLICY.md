# 20 — What 'do everything automatically' actually means

The runtime system must autonomously produce **ideas-to-film** while respecting feasibility, cost, device, rights and quality boundaries. All normal creative choices are automatic: story, screenplay, ending/series plan, character names/appearances, initial reference prompts and image generation, settings inferred from actual provider capabilities, shot timing/composition, generation queue, audio/voices, soundtrack selection from cleared catalog, subtitles, editing, export and project preservation.

## Permissions the user should encounter only once, when necessary
1. First-time selection of local model/provider installation, explanation of weight size and optional drive selection.
2. Approval to download large weights. User can choose to skip and try DEMO.
3. Consent for optional use of remote services/paid model; default off.
4. Confirmation for deleting originals, bulk re-render exceeding configured compute cap, sensitive likeness/voice rights.

## What to do when no clarification is provided
Reasonable defaults: mode auto inferred from prompt unless explicit; short movie=60 secs, series=6 episodes of 60 secs (adjustable), clip=15 secs, short drama=60 secs; photorealistic style; English; narration for shots where lip sync would be poor; 9:16 for 'social/reel/tiktok/short' intents otherwise 16:9 for 'movie/film' intents, but show and let user override; safe sound and no paid service; a 6 GB low-memory profile. These are product defaults, not fixed invariants.

## Production fallback hierarchy
- Preferred: stable real local models with reusable reference images, image-to-video and real local voice.
- Safe alternative: simpler low-memory model or reduced native resolution, still REAL and visible configuration.
- Partial completion: valid editable script + storyboard + characters and missing shots marked incomplete; offer explicit continue later.
- Demo: deterministic watermarked generated test footage to exercise pipeline with NO claim of photorealistic AI.

## Autonomy versus quality
No compulsory manual reviews at every stage. Programmatic validators and bounded regenerations make common errors self-correcting. When it cannot meet integrity/safety/quality thresholds, it must clearly mark the project as requiring attention rather than export a fake 'perfect' result. Preserve all intermediate assets to avoid lost work.

## Offline promise
'Works without subscriptions' means basic pipeline and installed models can run offline. First install downloads still require network unless weights preinstalled. Runtime should not require ChatGPT/Codex/paid LLM; these are tools used to *develop* the application, not mandatory app dependencies. Small local story models may produce weaker scripts; advanced users may optionally configure an approved external provider.
