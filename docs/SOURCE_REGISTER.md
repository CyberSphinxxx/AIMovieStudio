# Provider and runtime source register

Checked 2026-10-12. Intended use: private local development; no public distribution or paid integration authorized.

| Component | Primary source | Verified scope / unresolved gate |
|---|---|---|
| WanGP | https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/API.md and shared/api.py | `init(root, output_dir, cli_args)`, `get_model_schema`, `get_model_availability`, `submit_task`, `job.result`, `job.cancel` inspected. Out-of-process adapter contract is separate from inference proof. |
| WanGP rights | https://github.com/deepbeepmeep/Wan2GP/blob/main/LICENSE.txt | Community License 2.0. Paid embedding/hosting requires separate authorization; applicable output credits and component licenses need review. Not bundled. |
| FramePack | https://github.com/lllyasviel/FramePack | Documents 6 GB GPU minimum, Windows and >30 GB auto-downloaded models. Does not establish this laptop's RAM feasibility. Large download gate blocks testing. |
| Ollama | https://docs.ollama.com/capabilities/structured-outputs and https://docs.ollama.com/api/chat | Schema in `format`, non-streaming chat, `keep_alive:0`. No installed service found. Contract tests are simulated and labeled. |
| Qwen CPU smoke | https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF | Q4_K_M file: 491,400,032 bytes, Apache-2.0. Model SHA checked against hosting metadata. Small model quality not established. |
| llama.cpp | https://github.com/ggml-org/llama.cpp/releases/tag/b11558 and tools/server/README.md | Windows CPU runtime 19,501,704 bytes; release SHA verified. Schema-constrained chat endpoint. MIT; notices needed before redistribution. |
| FFmpeg tools | https://www.gyan.dev/ffmpeg/builds/ | App-local essentials bundle 114,768,076 bytes. H264/AAC/FFprobe observed. Review actual build licensing and encoder obligations before redistribution. |
| Windows speech | https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer | Installed voices only; no cloned voice or downloaded assets. Actual voice availability and WAV generation tested. Redistribution rights not claimed. |
| Windows process containment | https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects | Nested job objects and kill-on-close supported since Windows 8. Tested on Windows 11; no OS settings changes. |

All model weights, LoRAs, voices and media need separate rights/provenance. No third-party inference framework or weights are committed to Git. No paid/cloud provider is enabled. Source URLs may evolve; recheck before selecting a GPU model or changing adapter contracts.


## Approved isolated GPU sources — checked2026-10-12

- WanGP source pinned6479db36bdc2619a904a852bba9c2d78e1a83f82: https://github.com/deepbeepmeep/Wan2GP/tree/6479db36bdc2619a904a852bba9c2d78e1a83f82 . Original handlers/API determine selected paths/capabilities; checksum in installer/evidence. No inferred inference success.
- uv portable Windows release0.13.0: https://github.com/astral-sh/uv/releases/tag/0.13.0 . App-owned Python install with --no-bin --no-registry; no global toolchain changes.
- Official CUDA13.0 PyTorch Windows wheel index: https://download.pytorch.org/whl/cu130/ . Exact cp311 hashes/sizes pinned in wan-runtime-artifacts.json. Torch2.10.0 import blocked by local Windows policy.
- Model converted-hosting revisions/URLs/hashes and upstream licenses are pinned in gpu-download-proposal.json and GPU_INSTALL_PROPOSAL.md. Private local installation only; distribution remains unreviewed.
- Gyan FFmpeg9.0.2 official GitHub release mirror: https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2 . Same114,768,076byte archive/SHA as selected direct source; app-local ffplay required by vendor offline init.
- Microsoft enforced-policy block diagnosis: https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/appcontrol-debugging-and-troubleshooting . Local event3077 identifies torch_cuda.dll. Read-only diagnosis; no OS changes.
- Runtime security audit uses pinned lock and pip-audit advisory service. Audit JSON retained verbatim. Main app0known advisories; vendor90 unresolved. No compatibility claim for major package upgrades or experimental Pillow override.

- SQLite error codes: https://www.sqlite.org/rescode.html#ioerr_truncate (checked2026-10-12). Extended TRUNCATE code1546 observed locally immediately after Windows hardkill. Specific file-handle race is an inference; retry outcome measured, no data-file cleanup.
# Additional CPU writing candidate (checked2026-10-12)

Official model card: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF. Official API metadata and pinned LICENSE/README at revision91cad51170dc346986eccefdc2dd33a9da36ead9 were read; Apache-2.0, Q4_K_M1,117,320,736bytes, exact SHA256 in cpu-story-download-proposal.json. Separately approved weights/notices installed and hash-verified;1,117,336,935network bytes. First inference preflight blocked at2.44GiB free RAM; no model loading/quality result. Installed llama.cpp b11558 CPU runtime is reused. Model-card capabilities are upstream claims; laptop RAM/speed/story quality remain unproven.
