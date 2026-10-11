# 08 — Backend API, validation and contracts

## Stack
FastAPI with Pydantic v2 and typed domain services. Prefer minimal dependencies; SQLite migrations via Alembic, SQLAlchemy or equivalent. Environment configuration validated at launch. All `uvicorn`/local services listen on 127.0.0.1 by default. Never advertise a remote server without opt-in and authentication.

## Essential endpoints (illustrative, finalize in OpenAPI)
- `GET /api/health` service, DB, FFmpeg, disk, providers, GPU visibility; status per component, not single vague boolean.
- `GET /api/providers` list permitted configured providers, capabilities, latest verified availability, license notes.
- `GET /api/settings`, `PATCH /api/settings` validated paths and resource caps, no secrets in response.
- `POST /api/projects` request `{idea,kind,orientation,target_seconds,episodes?,language?,style?,idempotency_key}` returns persisted project ID immediately.
- `GET /api/projects`, `GET /api/projects/{id}`, `PATCH /api/projects/{id}` with optimistic versioning.
- `POST /api/projects/{id}/produce`, `/pause`, `/resume`, `/cancel` -> job IDs/status.
- `GET /api/projects/{id}/story`, `PUT` new version; endpoint must validate canon revision/dependencies.
- `GET /api/projects/{id}/characters`, `/locations`, `/episodes`, `/scenes`, `/shots`.
- `POST /api/shots/{id}/regenerate` with reason/config and user approval to incur new compute.
- `GET /api/jobs/{id}` and `/events` SSE; resume with event sequence on reconnect.
- `GET /api/assets/{id}` metadata, `/content` streaming with safe asset ID validation.
- `POST /api/exports` for specified project/episode profile, `GET /api/exports/{id}`.

## Response contract
All errors `{code,message,details?,retryable,action?}` with no stack secrets. Validation 422, conflicts 409, missing 404, blocked approval 428/409 with structured action; worker internal errors 500 with request/job ID. One request never blocks HTTP for hours; submit returns 202/job reference.

## Security
Validate structured prompts but do not treat LLM output as commands. Escape all user text in UI, sanitize names/path components, validate image/video MIME+magic bytes+size, restrict upload roots and max bytes. CORS exactly localhost dev origins, CSRF/origin defenses if browser cookies, optional local token for stateful mutations. Protect SSE and media paths from path traversal and other local users where relevant. Third-party backend tool output untrusted. Never execute prompts as shell text.

## Client generation
Generate TypeScript API types from OpenAPI, keep shared version numbers, contract tests on both ends. Use React Query/tanstack or simple typed fetch state; avoid unnecessary global state. UI display numeric progress only when stages report numeric measure; otherwise indeterminate.

## Tests
DTO validation for all modes; incorrect aspect/duration/episodes rejected or clamped with clear UI; duplicate create idempotent; stale version conflicts; SSE reconnection ordering; streaming range requests; invalid asset path, non-existent resource and expired job lease. Document stable request examples and negative cases.
