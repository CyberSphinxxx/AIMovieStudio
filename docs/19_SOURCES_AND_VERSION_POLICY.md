# 19 — Primary sources, verification policy, and research refresh

Research assembled 2026-10-12. Links are references, NOT guarantees for future package/API behavior. Codex must visit the upstream version and pin compatible releases before implementation. Do not substitute unofficial random GitHub forks unless clearly justified.

## High-priority primary sources
- WanGP official repository: https://github.com/deepbeepmeep/Wan2GP
- WanGP 2026 low-memory release notes (main README, October 7 entry): https://github.com/deepbeepmeep/Wan2GP#readme
- WanGP official Python API: https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/API.md
- WanGP official CLI/MCP: https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/CLI.md
- WanGP license (Community License 2.0): https://github.com/deepbeepmeep/Wan2GP/blob/main/LICENSE.txt
- FramePack (6 GB / 3060 laptop and large model download claim): https://github.com/lllyasviel/FramePack
- ComfyUI official project: https://github.com/Comfy-Org/ComfyUI
- Ollama structured output: https://docs.ollama.com/capabilities/structured-outputs
- FFmpeg documentation: https://ffmpeg.org/documentation.html
- Remotion pricing/licensing (optional only): https://www.remotion.dev/docs/license/pricing
- OpenAI long-horizon coding-agent cycles: https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
- GPT-6.1 Sol model effort support: https://developers.openai.com/api/docs/models/gpt-6.1-sol
- Codex best practices: https://learn.chatgpt.com/docs/learn/best-practices

## Optional discovery
- AI video production editor: https://github.com/LudwigKienle/ai-video-production-editor
- OpenFilm: https://github.com/openfilm/openfilm
- MoneyPrinterTurbo (mainly stock-footage/shorts automation): https://github.com/harry0703/MoneyPrinterTurbo
- TTS: https://github.com/hexgrad/kokoro
- Alternate local TTS: https://github.com/resemble-ai/chatterbox

## Critical corrections/nuance
1. WanGP describes itself as free/open source but currently ships a custom community license restricting certain commercial embedding/paid services; check full terms.
2. Select WanGP models claim ~6 GB VRAM at certain resolutions. That is not a universal guarantee on RTX 3060 6 GB and 16 GB RAM.
3. FramePack author describes 3060 laptops as workable with 6 GB, but generation may be slow and model weights >30 GB.
4. Do not assume hosting platforms expose allowed free public video APIs merely because they grant consumer-site credits.
5. APIs, names and dependency pins change; integration needs observed API contract, compatibility tests and upgrade notes.
6. Sol Medium default and High supported; agent behavior must still be controlled by actual test evidence.

## Research template
When an upstream dependency changes: commit source URL, version/tag/SHA, date reviewed, license, API usage/verified example, model card, RAM/VRAM benchmark, backout plan. Use official upstream first; when no evidence available, write UNKNOWN rather than guess.
