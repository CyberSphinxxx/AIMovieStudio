"""Check explicit shot headings against the authoritative structured inventory."""

import re

SHOT_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(?:\[?\s*shot\s+(\d+)\b|\[(\d+)\](?:\s|$))", re.I | re.M
)


def validate_shot_headings(text: str, numbers) -> str:
    expected = set(numbers)
    headings = [int(labeled or bracketed) for labeled, bracketed in SHOT_HEADING.findall(text)]
    outside = sorted(set(headings) - expected)
    if outside:
        raise ValueError(
            f"Screenplay shot headings {outside} are outside the requested shot range {sorted(expected)}"
        )
    if len(headings) != len(set(headings)):
        raise ValueError("Screenplay repeats a numbered shot heading")
    if headings != sorted(headings):
        raise ValueError("Screenplay shot headings are out of order")
    # Conventional scene headings/plain prose remain valid; scene IDs are not shot IDs.
    return text
