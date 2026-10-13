# Additional CPU writing experiment — approved, quality failed

Approved 2026-10-12 and installed within the bounds below. On 2026-10-14, three actual CPU-only writing trials took 172.625, 151.844 and 137.110 seconds (461.579 cumulative). All passed typed assembly; all failed manual writing review. Final shot-number gates remove observed invented headings, but repeated actions, incomplete speech and physical continuity remain inadequate. No further 1.5B trial is running. Raw outputs and reviews are preserved under `ops/evidence/cpu-writing-runs/`; separate 4B approval is in `CPU_4B_STORY_INSTALL_PROPOSAL.md`.

The installed 0.5B model failed manual screenplay review and recent structured-output runs. Proposed replacement experiment: official **Qwen2.5-1.5B-Instruct Q4_K_M**, using the already installed llama.cpp b11558 CPU runtime. This is an experiment; writing quality, RAM peak and speed remain unproven on this laptop.

Source: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
Pinned revision: `91cad51170dc346986eccefdc2dd33a9da36ead9`. Apache-2.0 model license; existing llama.cpp runtime is MIT. Exact model/notice hashes are in `ops/evidence/cpu-story-download-proposal.json`.

Download: one 1,117,320,736-byte GGUF plus 11,343-byte LICENSE and 4,856-byte model card. **Additional cumulative network cap 1,200,000,000bytes; additional disk cap 1,500,000,000bytes**, including interrupted partial files and test evidence. Preserve existing 0.5B files, license notices and failures. This is separate from the prior pinned GPU approval; its 32 GB/40 GB caps and image-before-video gate stay in force.

Installation writes only app-owned `tools/story/` files. No new executables/packages, driver/security/global Python/paging/firewall/power changes, paid service, cloud upload or external bind. The helper requires `--approved`, exact byte lengths/SHA256, cumulative resumable accounting and 5 GB free-disk reserve. No existing target is overwritten. Files are installed and hash-verified; the approved model's manual writing quality failed.

Tests: CPU only (`-ngl0`), four threads, 8192 context, serial sections of at most four shots; require at least 5 GiB free RAM before loading. Stop at one failed section after its three-attempt ceiling, or ten minutes total test time. Persist plan/section evidence and sampled process RSS/available RAM/time. Review scene content, cause/effect, physical character descriptions and declared canon separately from structural validation. No image/video claim. The child runtime unloads after each request and on interruption.

After approval: prepare files, select the explicit1.5B CPU profile, perform bounded real writing tests, retain failures and either integrate observed success or record the blocker and advance independent work.
