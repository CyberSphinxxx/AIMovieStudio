# Blockers — 2026-10-12

- **GPU inference, BLOCKED_APPROVAL:** No local image/video model/runtime is installed or verified. Appropriate stack downloads exceed the >1 GB model approval boundary in AGENTS.md. WanGP/weight licenses, exact model/download list and RAM/SSD budget must be reviewed before seeking concrete installation approval. No approval inferred. Adapter code/contracts alone do not prove generation or 6 GB support.
- **Memory:** Initially ~0.52 GiB available; later ~1.72 GiB observed. A real GPU smoke must measure available RAM, VRAM, process RSS and thermals; no paging/power/driver changes made.
- **Python version:** Specification names 3.11; used existing 3.12.14 for local development. Python 3.11 and clean-user install remain untested; no global install attempted.
- **Model story quality:** Tiny CPU model produced valid data but weak world rules in first successful plan. Grammar/semantic checks, real screenplay and series consistency still need work. Do not advertise high-quality automatic writing yet.
- **Release gaps:** Remaining backlog explicitly open: full canon knowledge/props/world-time, optional editing, backup/restore, model setup, cinematic QA, rights/security packaging. Do not declare full application completed.
- **Approvals unchanged:** no paid APIs, cloud uploads, remote bind, system changes, large model downloads or restrictive new license acceptance authorized.
