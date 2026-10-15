"""Only stopped, complete scripts before committed media can be revised safely."""


def stopped_before_media(project, job):
    return (
        job["state"] in {"PAUSED", "FAILED"}
        and not any(s["state"] == "RUNNING" for s in job["steps"])
        and any(s["stage"] == "SCRIPT" and s["state"] == "SUCCEEDED" for s in job["steps"])
        and not any(
            not isinstance(a["metadata"], dict)
            or a["metadata"].get("episode") is None
            or a["metadata"]["episode"] == job["episode"]
            for a in project["assets"]
        )
    )


def edit_eligibility(project, episode):
    if not episode or not episode["script"]:
        return False, "Wait for a complete saved screenplay before editing"
    target = next((j for j in project["jobs"] if j["episode"] == episode["number"]), None)
    if target and not stopped_before_media(project, target):
        return (
            False,
            "Editing requires a stopped screenplay with no committed media; produced/cancelled episodes remain unchanged",
        )
    if not target and episode["status"] not in {"DRAFTED", "REVIEW_REQUIRED"}:
        return False, "Choose an unproduced saved draft"
    if any(
        j["state"] in {"RUNNING", "QUEUED", "PAUSED", "WAITING_RESOURCES"}
        and not stopped_before_media(project, j)
        for j in project["jobs"]
    ):
        return False, "Finish writing or stop the current production before editing"
    return True, ""
