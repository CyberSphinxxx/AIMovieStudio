# Persistent data and series canon contracts

## Entities
**Project** `(id, original_idea, format, mode, style, runtime, language, settings_revision, created_at)`
**Season** `(id, project_id, planned_episode_count, ending_event_id, arc_summary, plan_revision)`
**Episode** `(id, season_id, episode_index, logline, outline_revision, screenplay_revision, canon_snapshot_id, status)`
**Scene** `(id, episode_id, narrative_start, setting_id, story_time, character_ids, beats, dialogue)`
**Shot** `(id, scene_id, duration_frames, target_fps, aspect, actor_state_refs, environment_ref, keyframe_asset_id, video_asset_id, sound_ids, deps)`
**Character** `(id, aliases, identity_description, visual_ref_revision, voice_profile_id, canonical_traits, consent_info_if_reference)`
**Location** `(id, reference_asset_ids, set_physical_description, ambience, story_visits)`
**Prop** `(id, description, owner_id, visible_condition, location_id, story_events)`
**Fact/Event** `(id, narrative_time, effective_episode, involved_ids, before, after, known_by, provenance, approval_status)`
**Asset** `(id, content_sha256, role, media_type, stored_relative_path, dimensions, duration, model_id, license, is_mock, parent_asset_ids)`
**Job** `(id, project_id, step, deps, state, attempt, max_attempts, lease_until, input_signature, output_manifest)`

## Time systems

Optional `Shot.flashback_after_shot` is a strict integer0..120 and needs an earlier `flashback_episode`; null preserves the prior episode-start behavior. Exact lookup also needs the saved earlier episode length and verified causal timing. Read projections enrich canon with `after_shot`, `timing_status` (`after_shot|episode_end|episode_only`) and `timing_source_seq` from matching immutable event evidence. They do not add columns or modify original canon/events/media. Conflicting/unlinked evidence stays episode-only; legacy unique manual-revision evidence can establish episode-end without inventing a shot. Explicit manual timed revisions store their event ID and position in the append-only audit record. Backups retain the existing raw-table format and carry this timing via their event log; current readers restore both old and new scripts. Known modern timing is ordered chronologically; episodes containing unknown legacy timing retain prior whole-episode row-order behavior, and exact relevant lookups refuse unknowns. This does not implement arbitrary world-clock time or produced-story branching.

Shot participation is distinct from an unused speaker-ID slot: visible character IDs always participate, while the speaker participates only for nonblank narration. Empty narration preserves the stored ID and existing asset/version identities. Script validation/continuity share the same participant helper. Draft revisions preserve original scripts and log `continuity_cleanup` when explicit silencing removes now-unused offscreen knowledge-use requirements; this never removes learned canon facts or visible actor requirements. No schema migration is needed.
Implemented job scheduling also uses `WAITING_RESOURCES`. The first pending step remains `READY` with its attempt count unchanged. A validated `resource_wait` event stores reason, step ID, stage, wall-clock start and a deadline no more than 24 hours later. The latest event is authoritative across process restart; a 15-second in-memory cache only throttles counter sampling. Claiming after readiness increments attempts transactionally. Explicit pause/cancel prevents automatic claim, expired/corrupt waits require retry, and imported unfinished jobs always restore paused. Waiting counts as active production for canon and draft edit conflicts. No SQLite schema migration is needed because state columns are text without enumerated constraints.

Do not confuse production wall-clock, scene display time, world chronological time, screen duration and episode order. Represent them with separate typed values. Flashbacks may have `narrative_time < current_scene_narrative_time` while displayed in a later episode; continuity lookups use narrative-time snapshot explicitly.

## Asset lineage
Content-addressed immutable originals and mutable project pointers. Inputs and references have hashes and version IDs. An image change invalidates downstream animation/output for linked shot and exports only; an episode ending change may invalidate future plan and canon. Never automatically remove old versions, because published exports may refer to them.

## Edit transactions
Optimistic lock `revision` increments on change; conflicts return 409 and show differences, not silent overwrite. All canon updates append change event in same DB transaction. Rollback returns to last approved story snapshot and triggers only affected job requeue.

## Backups
Store manifest JSON with schema version and append-only event table; support export with media and restore validation/checksums. A binary database by itself is not enough for long-term portability; provide JSON story/shot/asset manifest export too.
