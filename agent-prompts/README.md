# Runtime agent prompts — not autonomous OS agents

These are **templates for the movie application's internal AI roles**, separate from the developer Codex agent described in `AGENTS.md`. The runtime showrunner must never be granted OS-command privileges. A typed orchestrator passes canonical IDs/schema and receives validated JSON only. Adapt templates to real JSON Schema definitions as implementation proceeds.

Default workflow: 01 showrunner -> 02 series canon -> 03 screenplay -> 04 casting/art -> 05 cinematographer -> 06 audio -> 07 continuity/quality. Each receives only task-scoped context. Separate factual decisions from proposed changes. Do not claim generated images/video conform until the real provider completes.
