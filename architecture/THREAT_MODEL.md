# Mini threat model

Assets: private movie ideas, reference photos, voices, story scripts, workstations files, model credentials, model cache, output video and local API. Entry points: idea prompt, imported documents/scripts, media uploads, provider output, downloaded model/checkpoint/extension, local browser/API requests, zip project imports.

Trust boundaries:
1. LLM text -> validated domain JSON (never code/path/shell instruction).
2. External model/provider metadata -> capability validation and rights review.
3. User-supplied paths -> storage-root confined IDs and canonicalized paths.
4. FFmpeg/process invocation -> list args and scoped input, no shell interpolation.
5. Network optional API -> explicit consent, cost approval, credential storage outside repo.
6. Browser front end -> origin/CSRF controls, safe file streaming and escaping.

Threats: prompt-injection suggesting OS operations; malicious media/model file; poisoned plugins; unlicensed SFX; sensitive voice disclosure; local API bound public; runaway GPU/disk jobs; repeated failed downloads; path traversal in project zip; accidental overwrite of old export. Mitigations in `docs/14_LEGAL_SAFETY.md`, automated negative tests and explicit permissions. Tests must not run untrusted downloaded binaries without review.
