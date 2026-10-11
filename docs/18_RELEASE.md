# 18 — Release criteria and future roadmap

## V0 internal developer demo
Full mock pipeline with deliberately watermarked footage; project creation, persistent story and simple showrunner, shot queue, local audio, FFmpeg MP4, 9:16 and 16:9 export, interrupted task recovery and tests. No real-model claim.

## V1 personal alpha
Real image and video generation on a supported local provider with measured 6 GB resource data; model setup UX, project bibles, series episodes, characters/locations, one-prompt flow, optional editing, TTS/SFX, QA, MP4 export, Windows start/stop. Source-model rights/provenance and brand labels visible.

## V1.1 usability/polish
Good 16 GB RAM performance, resumable model downloads, sample presets, optional storyboard acceptance, bulk episode rendering within bounded resource settings, enhanced continuity, timeline edit.

## V2 optional/public consideration
Commercial viability/license review FIRST; switch to sufficiently licensed provider stack, cloud API access through approved paid providers with budgets, user accounts/remote GPU workers, collaboration, public content safety, backup/restore and legal review. Do not prematurely build SaaS in V1.

## Manual release review
User enters a vague prompt (e.g. 'a scary story in a foggy town') and receives a complete narrative and valid locally produced movie without being forced to prompt every shot; character and world assets reusable; 10-episode plan has stable ending; next episode continues after restart; there is a working Stop button; all errors recover; no unexpected cost. Actual quality compared against representative scene rubrics, not screenshots alone.

## Final Codex report (required)
`SHIPPED: [features backed by tests]`; `VERIFIED: [exact commands and counts, mock vs real]`; `NOT VERIFIED: [GPU/Windows/quality blockers]`; `RESOURCES: [actual downloads sizes + measurements]`; `SECURITY/LICENSING: [review status]`; `RUN: [exact Windows command]`; `NEXT: [first unblocked task ID]`. Never conclude 'bug free', 'complete' or 'all polished' if criteria haven't passed.
