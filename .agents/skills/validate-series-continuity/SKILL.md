---
name: validate-series-continuity
description: Validate or implement screenplay, season-bible, story-memory and character-continuity changes in AI Movie Studio. Use whenever changing story planner, canon state, episode generation, character appearance IDs or downstream invalidation.
---

Read `docs/04_STORY_ENGINE.md`, `architecture/DATA_MODEL.md` and `agent-prompts/02_SERIES_CANON.md`. Check immutable stable entity IDs, as-of episode/world-time snapshot, approved/rejected event status, narrator knowledge versus character knowledge, costume and injury state, prop ownership and full-season planned ending. Test death/reappearance, offscreen action, flashback, timeline edits, different episode order, revised first episode invalidating future scene assets. Persist timeline and versions before any asset generation; report precise contradictions with evidence IDs and make tests. Never rely on the LLM's textual memory as canon.
