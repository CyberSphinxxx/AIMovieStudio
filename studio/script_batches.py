"""Bounded screenplay sections using the worker's existing durable checkpoints."""

from studio.domain import EpisodeScript, SeasonPlan, validate_script


def merge_sections(sections, number):
    if not sections or any(s.number != number for s in sections):
        raise RuntimeError("BAD_STORY: Missing section or wrong episode in screenplay checkpoints.")
    return EpisodeScript(
        number=number,
        screenplay="\n\n".join(s.screenplay for s in sections),
        shots=[shot for section in sections for shot in section.shots],
        proposed_changes=[change for section in sections for change in section.proposed_changes],
    )


def validate_section(section, plan: SeasonPlan, start, count, seconds_per_shot):
    if len(section.shots) != count or [s.number for s in section.shots] != list(
        range(start + 1, start + count + 1)
    ):
        raise RuntimeError("BAD_STORY: Section shot count or global numbering does not match its checkpoint.")
    if any(abs(s.duration - seconds_per_shot) > 0.001 for s in section.shots):
        raise RuntimeError("BAD_STORY: Section shot durations do not match the runtime budget.")
    if any(not start <= c.after_shot <= start + count for c in section.proposed_changes):
        raise RuntimeError("BAD_STORY: Section changes must occur within its own shot range.")
    local = section.model_copy(deep=True)
    for shot in local.shots:
        shot.number -= start
    for change in local.proposed_changes:
        change.after_shot -= start
    validate_script(
        local, plan, count * seconds_per_shot, screenplay_numbers=range(start + 1, start + count + 1)
    )
