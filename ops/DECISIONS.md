# Decisions — 2026-10-12

1. Preserve original blueprint directory untouched; copy specifications into root to make AGENTS/PLANS discoverable. Original source files remain untracked/ignored, not deleted.
2. React/TypeScript strict with Vite; FastAPI/Pydantic2; stdlib SQLite transactional migrations instead of an ORM/broker. Single local worker owns OS lock and runs heavy stages sequentially.
3. Existing bundled Python 3.12.14 is the tested interpreter because specified Python 3.11 is absent. Code targets >=3.11. No global Python/driver installation. Python 3.11 clean-machine verification still needed.
4. Demo fixtures are conspicuous in media, manifests and UI. Actual Windows synthetic speech is distinct from demo visuals. Original synthetic ambience, no downloaded music and no cloned voice.
5. WanGP remains separately installed. Bridge calls inspected official API, inspects installed-weight/capability status, confines output paths, blocks external network and isolates optional CUDA processes. No vendor implementation copied into source; runtime integration remains unverified until installed.
6. Small CPU inference experiment uses official Qwen 0.5B Q4_K_M (~491 MB) and pinned llama.cpp b11558 (~20 MB). Permissive license checks, source hash verification and app-local extraction; below model approval threshold. First schema attempt failed because source docs example differed from pinned parser; fixed nested response_format.json_schema.schema after source inspection. Valid plan observed; story quality not claimed.
7. Output profile is small draft resolution, 24fps; no fabricated native-HD generation. Real provider normalization uses letterboxing and records native dimensions/parameters; no stretching.
8. Settings freeze per production job. Explicit retry of failed work may adopt current settings and records configuration event, preserving finished media/lineage. Pause retains settings.
9. No automatic aesthetic regeneration or unverified OOM downshift. Three-attempt stage budget, typed failure messages, user-visible recovery. Models unavailable → fail transparently and retain story.
10. Windows child processes receive kill-on-close job containment to prevent orphan inference after hard worker termination. This is application process management, not an OS configuration change.
