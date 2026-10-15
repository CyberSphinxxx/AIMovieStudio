"""Declared causal checks. Free-form screenplay prose is not a semantic proof."""

from studio.domain import shot_participants


def draft_events(project, number):
    """Earlier planned changes are simulation inputs, never completed canon."""
    return [
        {**change, "episode": e["number"]}
        for e in project["episodes"]
        if e["number"] < number and e["status"] != "COMPLETED" and e["script"]
        for change in sorted(e["script"].get("proposed_changes", []), key=lambda c: c["after_shot"])
    ] + project["canon"]


def snapshot(events, episode, plan):
    state = {
        "alive": {},
        "location": {},
        "prop_owner": {p.id: p.owner_id for p in plan.props} if plan else {},
        "knowledge": {c.id: set(c.initial_knowledge) for c in plan.characters} if plan else {},
    }
    for event in sorted(events, key=lambda e: e["episode"]):
        if event["episode"] >= episode:
            continue
        field, entity, value = event["field"], event["entity_id"], event["value"]
        if field == "knowledge":
            state[field].setdefault(entity, set()).add(value)
        elif field in state:
            state[field][entity] = value
    return state


def check_continuity(script, events, plan):
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
