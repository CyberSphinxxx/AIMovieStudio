# Active implementation plan — 2026-10-12

Task/ID: F0 → F1/F2/F3/F4/F6/F7, end-to-end local vertical slice.
Motivation: One idea must immediately persist and progress to an honestly labeled playable MP4; interrupted work must resume.
Ground truth: Original blueprint was nested in AI_Movie_Studio_Codex_Blueprint; preserved intact. Specifications copied to repository root. No existing application or commits.
Assumptions: No configured generation providers; no permission for >1 GB model downloads. Bundled Python 3.12 is available; required 3.11 absent. Use 3.11-compatible code and isolated 3.12 environment for observed verification, record deviation.
Slice: React/TypeScript + FastAPI + SQLite/WAL; durable single worker; typed season plan/canon; watermarked demo references/clips; installed Windows speech; synthetic ambience; FFmpeg H264/AAC export with probe/checksums and downloadable provenance.
Components: studio/, client/, tests/, scripts/, launcher, ops/.
Safety/licensing: localhost only, no cloud, no executable model output, bounded retries/disk reserve, app-owned immutable media. Vendor weights remain separate and permission-gated. Review sources before adapter implementation.
Tests: API validation/idempotency; story contradiction/10-episode ending; media portrait/landscape; worker crash/restart/hash reuse; pause/cancel; UI workflow and responsive screenshots; actual MP4 probe.
Recovery: Retain originals, SQLite migrations transactional, atomic media publication, exclusive process lock, stage checkpoints. Local Git checkpoints after verified work.
Progress: Recon complete. Local development dependencies installing (~small downloads); no GPU model installation.
Result: IN_PROGRESS. Real inference remains unverified.
