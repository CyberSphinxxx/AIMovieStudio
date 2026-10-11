# 00 — Required remaining research and feasibility gates

As of 2026-10-12, project scope is defined, but precise model/runtime compatibility MUST be measured on the target Windows laptop. Do not spend the implementation budget on an unverified 6 GB stack.

## Gate R0: Workstation discovery
Capture Windows build, NVIDIA driver version, `nvidia-smi` output, physical/available RAM, pagefile policy, free SSD space, Python and Node versions, FFmpeg and Git presence, laptop power/thermal status. Require AC power and ventilation for long jobs. No unauthorized driver change. Disk budget: research actual model size first; many checkpoints are tens of GB, and generated frames/video grow quickly. Never fill system partition silently.

## Gate R1: Provider documentation and license verification
1. Read current `https://github.com/deepbeepmeep/Wan2GP` README, `docs/API.md`, `docs/CLI.md`, `LICENSE.txt`, and the model-specific readmes/model cards. WanGP has a local API/MCP and some models can run with ~6 GB VRAM, but **not every model**.
2. Assess FramePack official `https://github.com/lllyasviel/FramePack`, 6 GB hardware support, Windows package, downloads and current repository/license conditions. It is a possible fallback rather than guaranteed easy backend.
3. Consider ComfyUI only if easier contract integration or better validated 6 GB workflows; the official 5B Wan 2.2 workflow commonly cites 8 GB with offloading.
4. Check license of every downloaded MODEL WEIGHT, LoRA, voice, music/SFX, bundled font, reference asset, and software dependency separately. WanGP's **Community License 2.0 restricts paid embedding/hosting/white-label distribution**; do not call it an unrestricted OSS license. A privately used internal creator tool and a paid app are different products.
5. Test exact provider API parameters in isolated scratch scripts. DO NOT invent `wangp_*` signatures; use its versioned documentation and inspect capabilities.

## Gate R2: Real inference matrix (explicit approval before large downloads)
For 2-3 candidate models, measure same prompt/reference:
- load success, model disk bytes, Windows working set peak, GPU VRAM peak, free disk, time to first output, per-shot time, output fps/duration/resolution, failure rate, image-to-video support, 9:16/16:9, continuity, 2nd-run performance.
- candidate shot: 3-5 seconds, modest resolution, one character, minimal camera motion; image-to-video preferred.
- record `HARDWARE_PROOF.md` and artifact SHA-256. Use actual measured values; no guessed fps/speed.
- accept if 2 consecutive generations succeed with 16 GB RAM, without BSOD/unrecoverable failure, and a valid video file probes successfully. If not, pivot to lowest-resource supported model, smaller resolution or alternative provider. Do not lie about support.

## Gate R3: Story LLM
Test small local quantized model via Ollama/compatible host with schema-constrained JSON. Verify plan consistency for 10 episodes: character IDs, irreversible outcomes, world rules, spoilers, contradictions. The local story model should run without the video model loaded. Provide optional user-configured approved remote LLM, default OFF and no billing.

## Gate R4: Voice, music and legal
Test local TTS language coverage, voice persistence, punctuation, speaker identity; prefer ordinary non-cloned voices. Voice cloning only with verified consent. For music either user-provided licensed tracks or locally generated assets with license evidence; include a soundtrack-free fallback and synthetic ambience. Never assume 'AI-generated' means copyright-safe.

## Gate R5: Long-running operation
Simulate process crash, reboot, sleep, disk full, provider disconnection, corrupted file and cancel. Validate SQLite durable task state and no duplicate generation. Test 50 task queued operations in mock mode. Set temp cleanup and quota. Windows sleep/hibernation interrupts local jobs; do not promise 24/7 rendering.

## Exit artifacts
`ops/HARDWARE_PROOF.md`, `ops/DECISIONS.md` ADR, provider compatibility sheet, asset/license manifest. If tests blocked by GPU availability, proceed in mock mode but mark the real-providers milestone explicitly BLOCKED.

## Sources to revisit
- https://github.com/deepbeepmeep/Wan2GP
- https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/API.md
- https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/CLI.md
- https://github.com/deepbeepmeep/Wan2GP/blob/main/LICENSE.txt
- https://github.com/lllyasviel/FramePack
- https://docs.comfy.org/development/comfyui-server/comms_routes
- https://docs.ollama.com/capabilities/structured-outputs
- https://www.remotion.dev/docs/license/pricing
- https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
