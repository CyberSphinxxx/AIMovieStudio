# Durable production state machines

## Project states
`DRAFT -> PLANNING -> ASSETS -> RENDERING -> AUDIO -> EDITING -> VALIDATING -> COMPLETED`, with orthogonal interruption statuses `PAUSED`, `WAITING_APPROVAL`, `FAILED`, `CANCELLED`, `PARTIAL`. Project's displayed status is derived from stage statuses, not independent optimistic UI state.

## Job steps
`PENDING -> READY -> CLAIMED -> RUNNING -> SUCCEEDED`; `RUNNING -> RETRYABLE_FAILURE -> READY` bounded; `RUNNING -> FINAL_FAILURE`; `RUNNING -> PAUSE_REQUESTED -> PAUSED -> READY`; `RUNNING -> CANCEL_REQUESTED -> CANCELLED`; any prereq requiring input -> `WAITING_APPROVAL` and resubmit after approval. Each transition is atomic with authoritative timestamps, worker lease, input/output hashes, error code and safe message.

## Restart reconciliation algorithm
1. Startup obtains app instance lock, checks migration version and database health.
2. For every stale CLAIMED/RUNNING job whose heartbeat expired, inspect recorded temporary and final artifacts; `ffprobe` and verify checksum.
3. If output passes and matches input signature, mark SUCCEEDED; else mark READY with incremented attempt IF budget remains, otherwise FINAL_FAILURE.
4. Delete only temporary uncommitted files within app-managed temp paths, retaining logs to diagnose.
5. Queue steps whose dependencies succeeded, honoring active GPU semaphore and user pause.
6. Broadcast replayable events with monotonically increasing event sequence; UI resubscribes from last received.

## Invariant checks
A step may commit SUCCEEDED only when output manifest validation passes; only one active GPU-heavy job per machine; same idempotency key cannot generate conflicting outputs; no job can reference a deleted canonical entity; cancelled jobs cannot silently become successful; retry count cannot exceed budget. A failed optional soundtrack stage can be bypassed only with metadata marking soundtrack omitted and project requirements permitting it.

## Concrete shutdown test
Create 10-shot mock project, wait for shot 5 success, force-kill worker; restart; assert first 5 asset hashes unchanged, number of committed clips=10, no duplicated narration, final MP4 correctly timed. Repeat with SIGTERM, Windows taskkill and simulated power loss where safe.
