# 02 — UX, workflows, states and design brief

## Design philosophy
Create a premium, cinematic, calm dark UI, not a node graph or admin dashboard. The home screen has one prominent prompt field and a Create button. Progressive disclosure: show only mode + format + approximate duration, with an Advanced drawer. No setup wizard required on every run; first-run GPU/provider health check is skippable into labeled demo mode.

## Main routes
1. **Home** `/` — idea composer, mode chips (Clip/Drama/Film/Series), format segmented selector (Portrait/Landscape/Square), optional duration; featured recent projects and 'Try example'.
2. **Projects** `/projects` — searchable cards, filter by queued/rendered/series, archive/delete (confirmation), free disk indication.
3. **Studio** `/project/:id` — minimal tabs: Overview, Story, Cast & World, Shots, Episodes, Export. Main area current preview/storyboard; right sticky stage progress; dominant action Resume/Generate Next Episode/Export.
4. **Job detail** — pipeline stages, per-shot progress, preview, retry, cancellation, provider/config, actionable failure reasons, approved fallback options.
5. **Settings** — model/provider status, GPU/RAM/storage, output directory, free-first mode, CPU/GPU concurrency limits, local-only privacy, voice/language defaults, license notices, health diagnostics. Never demand users edit config files.

## Visual tokens and accessibility
Charcoal/near-black surfaces, off-white text, one warm gold or burgundy accent, restrained gradients; clear typography, accessible focus rings, proper labels, keyboard navigation, responsive layout. Use meaningful skeletons during loading. Text contrast >= WCAG AA. Avoid giant animations while GPU rendering; respect reduced motion. Graphics are functional: timeline, filmstrip, playable video, portrait device preview. No fake telemetry; use plain language for errors.

## UX sequence: Single prompt
Enter idea -> click Create -> immediately redirect to project with saved idea and stage indicator -> automatic 'Story plan' -> 'Cast and reference images' -> 'Shots and video' -> 'Voice/sound' -> 'Edit and export' -> playable MP4 with Export/Open Folder. No extra confirmation except first-time large download, irreversible data deletion or paid/external action. Sensible auto naming and filename sanitization. On first run explain current local model may take time and consume disk/GPU; show hard requirements and consent for download.

## UX sequence: Series
Idea + mode Series -> default 6 episodes (user can change), length per episode -> AI generates whole-season skeleton and locked ending -> optionally complete scripts for every episode, then render Episode 1 -> Episode 2 button uses persistent canon, not original input alone. Show season timeline, progression and canonical/future event labels. Reorder only if script dependencies can be reconciled. 'Revise season' is a versioned branch, not destructive overwrite.

## UX sequence: Interrupted work
On reopen, project details from SQLite load instantly; completed clips retain thumbnails and checksums. Worker detects interrupted active job and offers automatic safe resume. Pause stops after current atomic step; Cancel safely stops child process and records CANCELLED; Resume never regenerates successful shots unless explicitly invalidated.

## UI copy
Use 'Preparing your story', 'Creating character references', 'Animating shot 3 of 9', 'Building soundtrack', 'Finishing movie'. For mock backend: conspicuous `Demo footage — not AI generated`. For no model: 'Video model not configured; set up locally' with non-blocking diagnostics. Do not display fictitious countdowns.

## Empty/error states
No GPU, model missing, insufficient disk, out of memory, malformed LLM data, video provider timeout, failed voice, unlicensed asset, unrecognized format, paused workflow, crash recovery, 2 projects competing for GPU. Every state offers a safe next action: retry, skip/replace asset, low-memory preset, resume, export partial (clearly marked), or view diagnosis.

## UI tests
Automate 360×800 portrait, 390×844, 768×1024, 1366×768, 1920×1080; keyboard only; screenshot visual regression at home/creating/error/export; no horizontal overflow, obvious controls, labels not truncated, timeline and preview usable. Test reduced motion and tab focus.
