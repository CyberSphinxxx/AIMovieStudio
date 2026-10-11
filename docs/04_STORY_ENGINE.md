# 04 — AI showrunner and long-term series continuity

## Design constraint
Do not rely on LLM chat context as permanent memory. Maintain a **canonical versioned Series Bible**, character/location/prop registries, immutable episode production snapshots, event timeline, story arcs, and dependency links in SQLite plus validated JSON exports. Each generation request receives the smallest relevant facts and explicit scene context.

## Stages
1. Classify request and constraints: clip, drama, standalone movie, finite series, open series; desired tone, genre, audience, format, duration, voice/dialogue, target rating.
2. **Story concept**: logline, central dramatic question, setting and cinematic style guide; title candidates; disallow empty conflict.
3. **Finite plan**: end state/series ending first, then setup/payoffs, season arc, episode summaries and beat-level continuity; for open series plan whole current season ending with optional next-season seeds.
4. **World bible**: era, geography, factions, technology/magic, physics, important rules and prohibitions, location graph, pronunciation and visual motifs.
5. **Cast registry**: UUID, name aliases, consistent description (face, age band, physique, hairstyle, signature clothing), traits, goals, flaws, voice ID, relationships; plot states with event provenance. No identity defined by prompt text alone.
6. **Episode scripts**: full screenplay for each episode (all when practical), act and scene IDs, location/time, action, dialogue with speaker IDs, character status, required props; model must return schema-constrained JSON, then render human-readable Markdown.
7. **Shot breakdown**: scene -> shots, staging, camera, start/end state, reference IDs, duration, motion, audio cues, transitions, expected continuity assertions, risky content flags. Estimate whether shots fit runtime budget; combine/stretch intelligently instead of generating 200 costly clips by default.
8. **Update canon** when episode approved/rendered. Record events and `known_by` fields; prevent future episode spoilers from leaking into character dialogue.
9. **Episodic continuation**: retrieve canonical state as of episode start, plus outline of future episodes only for planning not character knowledge; reconcile new events against planned finale; version changes.

## Canonical vs proposed facts
Every fact has `project_id`, `entity_id`, `effective_story_time`, `effective_episode`, `source_event_id`, `status = proposed|approved|superseded`, and optional revision reason. New LLM output is a proposal, not canon until validated. Maintain `visual_ref_version` and `voice_id` pinned at scene generation time.

## Invariants
- Stable IDs for same character despite nickname/spelling; aliases may not create duplicate identities.
- No changing eye/hair color, signature injury, relationship, voice or costume without an explicit story event.
- Character cannot use a prop before receiving it, be in simultaneous locations or know future secrets without explanation.
- Dead/absent characters cannot appear or speak except explicit flashback/dream/revival event.
- Faction and power-system rules enforced; episode narrative must serve setup/payoff or character arc.
- Ending integrity: episode revision that affects finale triggers downstream continuity re-evaluation, not silent recomputation of entire season.

## Planning a series with long token costs
Do not force 10 complete long scripts in one LLM completion. First generate complete canon, season ending, episode beat sheet; then generate full scripts one episode at a time in deterministic batches and validate every script. Permit default: 'plan all episodes, fully script current episode'; add option 'prewrite entire season'. If user explicitly wants full scripts until end, batch through all episodes and persist progress before rendering any expensive video. Track word count, expected screen time and shot budget.

## Schema-first LLM calls
Provider returns JSON conforming to versioned Pydantic model/JSON schema; validator checks referential integrity and logic. On malformed output, one schema-specific repair attempt with exact validation errors, at most 2 retries; then fail job with actionable message. Keep planning temperature measured; control cost/time. Store prompt/template revision and model ID for reproducibility. Never persist complete raw sensitive third-party inputs beyond project scope without need.

## Retrieval
Retrieve recent 2 episodes, scene participants, their state as of story time, world constraints and future arc goals, with token budgeting. Summarize long past arcs but keep structured truth source intact; do not let a generated summary override canonical data.

## Revisions and forks
Edits can modify a draft before approval; published episode gets new revision/branch, preserving original. Detect invalidated shots/images/voices. Prompt user before bulk re-render; clearly show projected workload. Offer 'lock character appearance', 'lock storyline', 'lock voice' toggles in advanced UI.

## Story quality tests
- 10-episode generated outline includes definitive final resolution and logical path.
- Same protagonist IDs from episode 1 to 10.
- Deliberate test contradiction 'character dies Ep3 then speaks Ep4' is detected.
- A stolen object changes owner after event; later shots reflect new owner.
- Out-of-order scene edits invalidate related props and camera reference shots appropriately.
- JSON malformed/too long/model crash: saved stage can resume without losing approved canon.
