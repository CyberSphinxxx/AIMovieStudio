# 03 — Architecture and engineering choices

## Recommended deployment
A local desktop-like browser experience. React + Vite + TypeScript frontend served by a Python FastAPI backend at 127.0.0.1. Windows launcher starts backend, opens browser, keeps shutdown simple. Avoid Electron until packaging/business case justifies overhead; thin native wrapper (Tauri) is future option. Repo should remain usable via `npm run dev` and Python command.

## Services/modules
- UI shell — idea composer, project navigation, previews, progress/event stream.
- API — schema validation/auth localhost/origin protections, projects, episodes, shots, providers, settings, jobs, files.
- Story engine — structured LLM calls with retry/schema validation, canon checks, versioning and deterministic planning.
- Asset director — stable actor/location prompts, image gen, selects/caches/vets references.
- Render orchestrator — durable DAG planner, scheduler, one-GPU semaphore, worker heartbeats, retries/timeout and assets/provenance.
- Provider adapters — Mock, WanGP (documented local API/MCP), optional FramePack (only if adapter verified), ComfyUI, TTS, local LLM, ffmpeg renderer.
- Media pipeline — FFprobe, aspect-safe layout, edit decision list/shot trim, dialogue mix and subtitle overlay, final MP4 manifest.
- Continuity engine — validates story IDs/plot state, visual/reference consistency flags, timeline and approved canon, invalidates downstream derivative artifacts.
- Storage — SQLite (WAL with appropriate transactional patterns), normalized entities, append-only change events for audit + content-addressed/media manifest files.

## Modularity boundaries
Define `StoryProvider`, `ImageProvider`, `VideoProvider`, `SpeechProvider`, `AudioProvider`, `RenderProvider`, `QualityEvaluator`, `AssetStore`. Each must have capability discovery, health check, plan/estimate (not cost guarantee), submit, poll/await, cancel, and typed errors. Do not equate success with no exception: verify output exists and probes.

## API suggestions
`POST /api/projects` (idempotency key), `GET /api/projects/:id`, `POST /api/projects/:id/start`, `/pause`, `/resume`, `/cancel`; `GET /api/projects/:id/story`, `PUT /api/projects/:id/story` with version header; `GET /api/projects/:id/episodes`; `POST /api/episodes/:id/render`; `GET /api/jobs/:id`; `GET /api/jobs/:id/events` via SSE/WebSocket; `GET /api/assets/:id/stream` scoped; `GET /api/providers` and `/api/health`; `POST /api/exports`. Use stable UUID keys and consistent HTTP codes. Do not accept arbitrary absolute paths/commands in API.

## Durable queue architecture
At least one SQLite transaction per stage transition, worker lease plus heartbeat; resume orphaned RUNNING tasks on startup after verifying artifacts. Job scheduler enforces dependencies: plan -> canon -> references -> frame -> clip -> sound -> timeline -> export. Use atomic temp + rename for outputs, SHA256, reference counts. One VRAM-intensive model at a time; serialized LLM/vision/video stages or unload model. No Redis/complex broker initially.

## Media strategy
Generate low-res native compatible clips (duration/aspect limited by model); assemble with FFmpeg using exact timebase and sampling; optional upscale only if hardware permits. Keep source originals and export profiles separately. Use deterministic Ken Burns motion only as explicitly labeled fallback, not disguised as full AI video. TTS may run on CPU sequentially to free VRAM; cache generated speech.

## Deployment and packaging
Dev: separate frontend + API commands. Release: Windows launcher, local URLs, browser open, first-run health/setup. Download optional models to configurable folder not repository. Keep app updates/migrations independent of models. Capture licenses and model provenance. Consider portable distribution only after license review and actual Windows tests.

## Risks/ADRs
See architecture/PROVIDER_INTERFACE.md and docs/14_LEGAL_SAFETY.md. All libraries and performance plans are proposals until version-verified and benchmarked. Main risk: a real video model may fail on 6 GB+16 GB; preserve end-to-end usefulness, transparency and provider swap capability.
