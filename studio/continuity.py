"""Declared causal checks. Free-form screenplay prose is not a semantic proof."""

from studio.domain import shot_participants
from studio.canon_timing import valid_position


def draft_events(project, number):
    """Earlier planned changes are simulation inputs, never completed canon."""
    return [
        {**change, "episode": e["number"]}
        for e in project["episodes"]
        if e["number"] < number and e["status"] != "COMPLETED" and e["script"]
        for change in sorted(e["script"].get("proposed_changes", []), key=lambda c: c["after_shot"])
    ] + project["canon"]


class UnknownCheckpoint(ValueError):
    pass


def snapshot(events, episode, plan, *, after_shot=None, episode_length=None, relevant=None):
    state = {
        "alive": {},
        "location": {},
        "prop_owner": {p.id: p.owner_id for p in plan.props} if plan else {},
        "knowledge": {c.id: set(c.initial_knowledge) for c in plan.characters} if plan else {},
    }
    # Modern evidence has shot positions; legacy episodes preserve their prior row
    # order when any state-changing event lacks timing. Exact checkpoints refuse
    # relevant unknowns rather than guessing where they occurred.
    groups = {}
    for event in events:
        groups.setdefault(event["episode"], []).append(event)
    ordered = []
    for number in sorted(groups):
        group = groups[number]
        causal = [event for event in group if event["field"] in state]
        if all(
            valid_position(event.get("after_shot")) or event.get("timing_status") == "episode_end"
            for event in causal
        ):
            group = sorted(
                group,
                key=lambda event: (
                    event["after_shot"] if valid_position(event.get("after_shot")) else float("inf")
                ),
            )
        ordered.extend(group)
    for event in ordered:
        if event["episode"] > episode or (event["episode"] == episode and after_shot is None):
            continue
        field, entity, value = event["field"], event["entity_id"], event["value"]
        if event["episode"] == episode and field in state:
            position = event.get("after_shot")
            if not valid_position(position):
                if event.get("timing_status") == "episode_end":
                    position = episode_length
                else:
                    key = (field, entity, value if field == "knowledge" else None)
                    if relevant is None or key in relevant:
                        raise UnknownCheckpoint(
                            f"Event {event.get('id', 'without an evidence ID')} has no verified shot timing for episode {episode}."
                        )
                    continue
            if position is None or position > after_shot:
                continue
        if field == "knowledge":
            state[field].setdefault(entity, set()).add(value)
        elif field in state:
            state[field][entity] = value
    return state


def check_continuity(script, events, plan, *, episode_lengths=None):
    state = snapshot(events, script.number, plan)
    errors = []

    def apply(after_shot):
        for change in script.proposed_changes:
            if change.after_shot != after_shot:
                continue
            field, entity, value = change.field, change.entity_id, change.value
            actual = (
                ("known" if value in state[field].get(entity, set()) else "unknown")
                if field == "knowledge"
                else state[field].get(entity, "true" if field == "alive" else "")
            )
            if actual != change.before_value:
                errors.append(
                    f"After shot {after_shot}: {entity} {field} before-state {change.before_value!r} conflicts with {actual!r}."
                )
                continue
            if field == "knowledge":
                state[field].setdefault(entity, set()).add(value)
            else:
                state[field][entity] = value

    apply(0)
    for shot in script.shots:
        if shot.flashback_episode and shot.flashback_after_shot is not None:
            length = (episode_lengths or {}).get(shot.flashback_episode)
            if length is None or shot.flashback_after_shot > length:
                errors.append(
                    f"Shot {shot.number}: flashback checkpoint {shot.flashback_after_shot} needs a saved episode {shot.flashback_episode} with that shot."
                )
                continue
            relevant = (
                {("alive", identity, None) for identity in shot_participants(shot)}
                | {("location", identity, None) for identity in shot.character_ids}
                | {("prop_owner", use.prop_id, None) for use in shot.required_props}
                | {("knowledge", use.character_id, use.fact) for use in shot.required_knowledge}
            )
            try:
                current = snapshot(
                    events,
                    shot.flashback_episode,
                    plan,
                    after_shot=shot.flashback_after_shot,
                    episode_length=length,
                    relevant=relevant,
                )
            except UnknownCheckpoint as error:
                errors.append(f"Shot {shot.number}: exact flashback checkpoint unavailable. {error}")
                continue
        else:
            current = snapshot(events, shot.flashback_episode, plan) if shot.flashback_episode else state
        for character in shot_participants(shot):
            if current["alive"].get(character) == "false":
                errors.append(
                    f"Shot {shot.number}: {character} is dead; add an explicit revision/flashback before production."
                )
            location = current["location"].get(character)
            if character in shot.character_ids and location and location != shot.location_id:
                errors.append(
                    f"Shot {shot.number}: {character} is at {location}; declare a move to {shot.location_id} before this shot."
                )
        for prop in shot.required_props:
            owner = current["prop_owner"].get(prop.prop_id, "")
            if owner != prop.character_id:
                errors.append(
                    f"Shot {shot.number}: prop {prop.prop_id} belongs to {owner or 'no character'}, not {prop.character_id}; transfer it before use."
                )
        for use in shot.required_knowledge:
            if use.fact not in current["knowledge"].get(use.character_id, set()):
                errors.append(f"Shot {shot.number}: {use.character_id} has not learned {use.fact!r}.")
        apply(shot.number)
    return errors
