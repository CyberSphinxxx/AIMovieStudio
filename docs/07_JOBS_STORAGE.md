# 07 — Durable jobs, storage, cancellation and recovery

## DB core tables (indicative)
`projects`, `project_versions`, `seasons`, `episodes`, `scenes`, `shots`, `characters`, `locations`, `props`, `continuity_facts`, `story_events`, `references`, `assets`, `asset_lineage`, `provider_configs`, `jobs`, `job_steps`, `job_attempts`, `export_profiles`, `exports`, `media_rights`, `approvals`, `audit_events`.
All rows have stable UUIDs, created/updated timestamps, schema version, logical deletion where appropriate. Relationships and unique constraints enforce no orphaned assets and IDs. Use migrations from day 1; foreign keys enabled; backup before breaking migration; use WAL safe for local machine.

## Task state machine
`PENDING -> READY -> CLAIMED -> RUNNING -> (SUCCEEDED | FAILED_RETRYABLE | FAILED_FINAL | CANCEL_REQUESTED | CANCELLED | PAUSE_REQUESTED | PAUSED | BLOCKED_APPROVAL)`. Terminal states `SUCCEEDED, FAILED_FINAL, CANCELLED`. Retries are new attempts under same step, not duplicate independent assets. See `architecture/STATE_MACHINE.md`.

## Idempotency
Tasks derived from tuple project/episode/shot/stage/input hashes/provider version/config revision. Compute deterministic idempotency key; if same verified output exists with checksum, reuse it. If model seed/provider changed, generate new revision. Never replace files referenced by approved exports in place. Store each step's `input_manifest` and `output_manifest`.

## Atomicity and crash recovery
Use `.partial` files on same filesystem, fsync where appropriate, checksum validation and atomic rename. On restart, inspect stale RUNNING worker leases, verify existing outputs before resubmitting. Output file appearing is not equal to commit success; DB and manifest reconcile. During SIGTERM/Windows shutdown, mark cancellation intent and stop launching new steps, best-effort finalize in-flight process; forcibly terminated jobs become resumable.

## Storage policy
Model cache separate from project content; user-selectable directory and free-space check before download/render; reserved-space threshold, warning at 80%, safe temp quotas and retention. Do not auto-delete originals, prompt, character sheets, finished films, or canon. Temporary files may be pruned after validation and backup policy. Detect disk full mid-FFmpeg and offer cleanup of app-owned temp only. No cleanup outside configured root.

## Outputs and provenance
Each media asset logs parent IDs/hashes, prompt template revision, model/provider ID, render parameters (seed/steps/resolution/frame count, hardware profile), license/rights info if relevant, duration and dimensions via ffprobe, SHA256, quality scores, human approvals, output path relative to project root.

## Concurrency and scheduler
6 GB VRAM default GPU semaphore=1; run CPU-only jobs alongside within resource budget, but do not queue simultaneous large LLM + video. Use backpressure and priority: user-requested active shot first; preplanning asynchronous only inside active process and no GPU collision. No spin-wait loops; bounded polling with backoff/cancellation.

## Export and restore
Offer full project archive (DB export, source scripts, event timeline, references and assets or manifest-only lightweight variant) with explicit large-file warning. Verify import with zipped path traversal protections, conflicting UUID handling, checksum review; preserve original project. Test a moved project directory and reinstated app.
