# 15 — Edge-case matrix and expected behavior

Each case should have a regression fixture or test. No silent degradation.

| Category | Scenario | Required behavior |
|---|---|---|
| Input | Idea empty/whitespace | Helpful inline validation, no project job |
| Input | Very long or contradictory prompt | Preserve original; normalize and surface conflict rather than invent incompatible demands |
| Input | Duplicate creation click | Single project through idempotency key |
| Input | Portrait + cinematic ultra-wide shot prompt | Target format wins, reframe/regenerate shot; never stretch |
| Input | Requested 90-min movie on 6 GB | Feasibility warning, job estimate and staged episodes, not impossible immediate promise |
| Series | Change main villain motive in Episode 2 | Show affected future episodes; new canon revision and selective invalidation |
| Series | Actor dies in Ep 3 and reappears in Ep 4 | Validate flashback/revival reason or flag contradiction |
| Series | Episodes rendered out of order | Use episode as-of story snapshot, do not leak later state |
| Series | Two users edit project? (future) | Version conflict, not last-write-wins |
| Asset | Different characters look alike | Stable references and review warning, do not overwrite identity |
| Asset | Generated extra limb/object | Confidence warning, bounded regeneration |
| Asset | Same costume gets changed accidentally | Compare version and metadata; retry against pinned reference |
| Asset | User deletes used reference | Dependency warning, archive until no references |
| Video | Provider OOM | Release VRAM, low-memory config, max retries, explain final failure |
| Video | Model absent or incompatible | Setup guidance, safe mock option distinctly labeled |
| Video | Provider hangs/half-written MP4 | Timeout, terminate process safely, validate temp and retry |
| Video | Video shorter than expected | Update EDL or regenerate; don't cut dialogue |
| Video | Provider ignores aspect | Crop/letterbox policy and notice; don't stretch |
| Audio | TTS voice swapped | Canonical voice ID lock and warning |
| Audio | Dialogue longer than scene | Extend planned timing/insert cutaway, don't clip words |
| Audio | Music source unlicensed | Exclude, log reason, ambience or no music |
| OS | Laptop sleeps mid-job | Detect stale process on wake, resume from committed step |
| OS | GPU busy with game/browser | Detect resource pressure and offer to pause or downshift; never force-close apps |
| OS | System RAM/pagefile exhausted | Early disk/RAM health warnings, memory release; avoid crash loop |
| Storage | Disk fills during export | Delete only incomplete owned temp; preserve sources and report needed free bytes |
| Storage | C drive low, model cache on D | Custom paths with migration; do not copy giant weights back to C |
| Storage | Project directory renamed/moved | Relative asset IDs and validated relinking, no corrupt absolute paths |
| Storage | Unicode/emoji filenames | Unicode support + safe IDs for on-disk data |
| Security | Prompt says 'delete C drive' | Treat as narrative text, not execution instruction |
| Security | External input path traversal | Reject and audit, no arbitrary filesystem access |
| UX | Reload while generating | Reconnect to worker and recent events, no lost state |
| UX | Close app while rendering | Launcher warns / controlled worker stop vs preserve resumed job |
| UX | Inaccurate ETA | Show indeterminate or measured range, never fake exact countdown |
| Quality | Shot passes ffprobe but face changes | Warn/correct where reviewer supports; don't guarantee perfect |
| Product | Local-only, no internet after setup | Work using installed models; explicit optional cloud unavailable |
| Product | Paid cloud request | Require opt-in + budget approval, never surprise charges |
