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
Do not confuse production wall-clock, scene display time, world chronological time, screen duration and episode order. Represent them with separate typed values. Flashbacks may have `narrative_time < current_scene_narrative_time` while displayed in a later episode; continuity lookups use narrative-time snapshot explicitly.

## Asset lineage
Content-addressed immutable originals and mutable project pointers. Inputs and references have hashes and version IDs. An image change invalidates downstream animation/output for linked shot and exports only; an episode ending change may invalidate future plan and canon. Never automatically remove old versions, because published exports may refer to them.

## Edit transactions
Optimistic lock `revision` increments on change; conflicts return 409 and show differences, not silent overwrite. All canon updates append change event in same DB transaction. Rollback returns to last approved story snapshot and triggers only affected job requeue.

## Backups
Store manifest JSON with schema version and append-only event table; support export with media and restore validation/checksums. A binary database by itself is not enough for long-term portability; provide JSON story/shot/asset manifest export too.
