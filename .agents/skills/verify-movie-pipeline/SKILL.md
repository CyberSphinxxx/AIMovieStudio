---
name: verify-movie-pipeline
description: Verify an AI Movie Studio code change, movie export or release against mock versus real generation, FFprobe media validity, pipeline job recovery, portrait and landscape output, security and UX tests. Use before claiming a feature is complete or shipping.
---

Read `docs/11_TESTING.md`, `checklists/PHASE_GATES.md` and `docs/13_QUALITY_EVAL.md`. Find the changed surface, select cheapest relevant verification (lint/schema/unit, contract, API, media, E2E, hardware). Run tests and inspect actual results. For MP4 run ffprobe metadata, compare shot manifest to output and verify orientation, duration, audio and subtitles. Distinguish mock from real GPU outputs. For interruption work run forced-worker-kill and recovery test. Never mark DONE_VERIFIED without evidence. Save exact commands, exit codes and failures in `ops/PROGRESS.md`; create regressions for fixes. If GPU unavailable report `NOT TESTED`, not success.
