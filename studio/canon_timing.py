"""Recover explicit timing from linked immutable events, never display-text guesses.

Raw canon rows and backup format stay unchanged. Unknown provenance stays unknown;
an old/manual whole-episode revision means episode-end, not an invented shot.
"""

from __future__ import annotations

import json
from collections import defaultdict


def valid_position(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 120


def canon_key(value, revision):
    return tuple(value.get(key) for key in ("episode", "entity_id", "field", "value", "reason")) + (revision,)


def with_timing(rows, sources, *, project_revision=None):
    by_id = {row["id"]: row for row in rows}
    by_key = defaultdict(list)
    candidates = defaultdict(list)
    annotations = defaultdict(list)
    for row in rows:
        by_key[canon_key(row, row["revision"])].append(row["id"])
    for source in sources:
        try:
            data = json.loads(source["data"])
            if not isinstance(data, dict):
                continue
            if source["kind"] == "canon_committed":
                change = data.get("change", {})
                if not isinstance(change, dict) or not valid_position(change.get("after_shot")):
                    continue
                identity = data.get("event_id")
                row = by_id.get(identity)
                if not row or any(row.get(key) != change.get(key) for key in ("entity_id", "field", "value")):
                    continue
                if (
                    row["episode"] != data.get("episode")
                    or row["reason"] != f"After shot {change['after_shot']}: {change.get('reason')}"
                ):
                    continue
                candidates[identity].append(("after_shot", change["after_shot"], source["seq"]))
            elif source["kind"] == "canon_revision":
                event = data.get("event", {})
                if not isinstance(event, dict):
                    continue
                identities = by_key.get(canon_key(event, data.get("revision")), [])
                identity = data.get("event_id")
                if identity is None and len(identities) == 1:
                    identity = identities[0]  # Unique exact legacy revision evidence, no guessed timestamp.
                if identity not in identities:
                    continue
                after = event.get("after_shot")
                if after is not None and not valid_position(after):
                    continue
                candidates[identity].append(
                    ("episode_end" if after is None else "after_shot", after, source["seq"])
                )
            elif source["kind"] == "canon_timing_revision":
                identity = data.get("event_id")
                row = by_id.get(identity)
                original = data.get("source_canon")
                revision = data.get("revision")
                if not row or row["field"] not in {"alive", "location", "prop_owner", "knowledge"}:
                    continue
                if not isinstance(original, dict) or canon_key(
                    original, original.get("revision")
                ) != canon_key(row, row["revision"]):
                    continue
                if (
                    type(revision) is not int
                    or revision <= row["revision"]
                    or (project_revision is not None and revision > project_revision)
                ):
                    continue
                if (
                    "after_shot" not in data
                    or not isinstance(data.get("reason"), str)
                    or not 8 <= len(data["reason"].strip()) <= 500
                ):
                    continue
                after = data["after_shot"]
                if after is not None and not valid_position(after):
                    continue
                annotations[identity].append(
                    (revision, "episode_end" if after is None else "after_shot", after, source["seq"])
                )
        except (ValueError, TypeError, KeyError):
            # A corrupt/unlinked source never grants an exact checkpoint.
            continue
    result = []
    for row in rows:
        linked = candidates[row["id"]]
        revised = annotations[row["id"]]
        if revised:
            latest = max(revision for revision, *_ in revised)
            linked = [(kind, after, seq) for revision, kind, after, seq in revised if revision == latest]
        distinct = {(kind, after) for kind, after, seq in linked}
        if len(distinct) == 1:
            kind, after, seq = linked[0]
        else:
            kind, after, seq = "episode_only", None, None
        result.append({**row, "after_shot": after, "timing_status": kind, "timing_source_seq": seq})
    return result


def saved_episode_lengths(project):
    return {
        episode["number"]: len(episode["script"]["shots"])
        for episode in project["episodes"]
        if episode["script"] and episode["status"] in {"COMPLETED", "DRAFTED", "SCRIPTED"}
    }


def flashback_label(shot):
    if shot.flashback_episode is None:
        return ""
    position = shot.flashback_after_shot
    moment = (
        "before the episode begins"
        if position is None
        else "before the first shot, after setup"
        if position == 0
        else f"after shot {position}"
    )
    return f"Flashback — Episode {shot.flashback_episode}, {moment}."
