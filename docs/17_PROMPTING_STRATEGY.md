# 17 — In-product prompt engineering and agent orchestration

## Principle
LLM agents are role templates applied to typed data, not separate unsupervised entities with OS access. No AI-generated code or shell commands may flow directly into execution. Use JSON Schema/Pydantic structured output and deterministic validators. Production stages must be idempotent and restartable.

## Default production orchestration
1. `showrunner` validates the idea, selects arc, ending and cast using target audience/tone.
2. `story_editor` checks inconsistencies and payoffs; repair local constrained fields.
3. `screenwriter` expands beats into scenes and dialogues, with no invented characters not in registry (or explicit registration).
4. `casting_art_director` creates canonical reference-generation prompts and wardrobe variants.
5. `cinematographer` emits shot actions, keyframes, camera, timing and aspect-safe composition.
6. `sound_director` emits speech/sfx/music timing plan; no unauthorized voice clones.
7. `continuity_editor` inspects facts before applying canon and flags collisions.
8. `quality_reviewer` compares output to shot manifest for only testable flaws; returns specific rationale.

## Prompt input envelopes
Each role gets `{schema_version, project_constraints, context_snapshot, canonical_fact_ids, task_target, output_schema, resource_budget, output_language}`. Narrative facts are sourced by ID; never let a role declare changed canon without an event/revision. Never send all episodes/scripts to every role; keep context budget bounded.

## Prompt guardrails
- All user ideas and reference materials are untrusted content, NOT new instructions to the app's tools.
- Require output JSON only, no markdown fences for machine paths, no executable snippets, limited length and known IDs.
- On LLM JSON failure: targeted repair with schema errors; at most bounded retries; fall back to a deterministic safe outline or mark failure, not fabricated 'success'.
- Consistent scene timing math; only make claims about available provider capabilities given live discovery, not LLM inference.
- Cache planning results by content hash, model/template version, temperature and canon revision; regenerate only invalidated nodes.

## Evaluation metrics
Story: beginning/conflict/escalation/resolution, arc payoffs, chronology, character knowledge; visual: identity references and framing; runtime: target seconds vs estimated shots; audio: dialogue durations. Mock task-specific validators should catch programmed contradictions in fixtures.
