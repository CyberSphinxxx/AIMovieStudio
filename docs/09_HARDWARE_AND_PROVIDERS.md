# 09 — Exact target hardware, provider strategy, installation

Target: NVIDIA RTX 3060 Laptop 6 GB, Ryzen 5 6600H, 16 GB system RAM, Windows. Focus on sequential low-memory rendering. Model 'supports 6 GB VRAM' does NOT prove it supports 16 GB system RAM, every resolution, or unattended API.

## Provider ranking and admission
**Default candidate: WanGP** — official project https://github.com/deepbeepmeep/Wan2GP ; official `docs/API.md` offers in-process generation/session/progress, and `docs/CLI.md` offers headless and MCP. October 7 2026 release cites select H3 workflows ~5-6 GB at 480p; validate on laptop. License: Community License 2.0, review precise restrictions and attribution. No vendoring into a monetized product without legal clearance.
**Fallback: FramePack** — official https://github.com/lllyasviel/FramePack says at least 6 GB NVIDIA GPU and specifically 3060 laptop support, >30 GB model downloads. Research appropriate automation interface rather than auto-click web UI; consider a thin direct Python adapter in separately installed environment if license permits. Long generation slow.
**Optional: ComfyUI** — proven graph/job API but some Wan 2.2 5B docs cite 8 GB. Test only a published low VRAM compatible workflow; do not assume.
**Story LLM** — Ollama/local OpenAI-compatible API in separate CPU/quantized runtime. Test JSON schema support and throughput; give explicit availability checks. A high-end GPU LLM can't be loaded alongside video on 6 GB.
**Images** — choose small local text-to-image or image editing model with reference-control capability and 6 GB proof, ideally accessible via same WanGP provider; test license/quality rather than specifying one large unsupported model. GPU models serialized.
**Speech** — lightweight local TTS (Kokoro is one candidate) or WanGP TTS if resource budget allows; use openly consented generic voices. Model licenses distinct from code license.
**Music** — local royalty-cleared/CC0 SFX library and optionally model-generated soundtrack with separate license. Default must generate a film with ambience even if optional music model unavailable.
**Renderer** — FFmpeg via command argv; H.264 + AAC MP4. Check FFmpeg binary/license if app redistributes it; configure path. Optional Remotion only after review: licensing can vary by company/use, especially automated products.

## Automatic setup UX
Detect NVIDIA driver/CUDA capability, RAM, FFmpeg, Python, free disk, internet availability, installed models; present a simplified 'Install local AI engine' with model size, license link and expected disk use before downloads. User approves downloads. Work in application-managed directory, not Windows system folders. Show progress/checksums; allow custom model path and 'Try demo without downloading' route. No mandatory administrative privileges. A failed step leaves retry/remediation, not a broken app.

## Real provider adapter contract
- `discover_capabilities`: supported task kinds, min/max dimensions/duration, format, reference inputs, audio support, license, resource estimate.
- `health`: running/not installed/model missing/unsupported/ready.
- `generate`: typed request IDs, input asset URI(s), prompts, reference IDs, seed, resolution, frames/duration, deadline, local output directory.
- `progress`: events if supported; fallback poll bounded, never assume.
- `cancel`: best effort with accurate status.
- `result`: verified media metadata, original model/provider manifest.
- `errors`: OOM, network, disk, model/download missing, driver/toolchain, input invalid, unimplemented.

## Benchmarks and rejection
Record GPU VRAM and system RSS peak, disk use, output dimensions, frame rate, elapsed time with real local input. Require two successful reproducible test generations. If all candidate models fail, do not pretend. Keep mock pipeline and expose 'real generation unavailable on current configuration' plus safe lower-res suggestions. No promise of unlimited rendering or hard ETA.
