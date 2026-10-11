# Provider compatibility architecture

## Goals
App is not a WanGP fork. User may install compatible providers separately; integration must honor their licenses. All providers expose typed capability descriptions at runtime; settings/prompt templates are selected per capability and resource profile, not hardcoded by app assumptions.

## Example Python protocols (illustrative, implement tested signatures)
```python
from typing import Protocol

class VideoProvider(Protocol):
    async def health(self) -> dict: ...
    async def capabilities(self) -> dict: ...
    async def submit(self, request: dict) -> str: ...
    async def progress(self, provider_job_id: str) -> dict: ...
    async def cancel(self, provider_job_id: str) -> None: ...
    async def result(self, provider_job_id: str) -> dict: ...

class ImageProvider(VideoProvider, Protocol): ...
class SpeechProvider(VideoProvider, Protocol): ...
class StoryProvider(Protocol):
    async def structured_generate(self, task_kind: str, input_data: dict, output_json_schema: dict) -> dict: ...
```
Use Pydantic contract classes instead of bare dict in production, version inputs/outputs and track provenance. Do not require all providers support async immediate cancellation or even progress; advertise capability flags honestly.

## WanGP real adapter
Research official `https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/API.md` and current version's `shared/api.py`; possible documented in-process API and MCP adapter. Match official session/model-list/settings/export job calls EXACTLY, not guesses from old examples. Prefer an out-of-process local bridge to isolate WanGP's Python/CUDA environment from app's FastAPI dependencies. Bind MCP HTTP only to localhost if used. File exchange by controlled project-scoped relative asset paths or validated Media IDs, not arbitrary host paths. Honor WanGP UI/docs attribution requirements. Capture license/version in provider metadata and setup disclosure.

## FramePack adapter
Only implement after confirming supported callable Python API or safe documented CLI; avoid fragile browser click automation. Run in separate environment. Translate app request to source image, prompt, frame count, size; result validated with ffprobe. If not realistically scriptable, mark manual or unsupported and remain on WanGP.

## ComfyUI adapter (optional)
Use official prompt/queue API and websocket/status protocol; store workflow JSON templates outside frontend and supply only validated mapped parameters. Reject incompatible workflows/VRAM. Do not accept arbitrary user-uploaded untrusted nodes or remote workflows without approval.

## Resource scheduler
On RTX 3060 Laptop 6 GB only one video/image heavy provider loaded at a time. Before large model load free previous model/LLM workers. Use available RAM/disk thresholds; settings allow low-memory mode and max storage. OOM triggers cleanup, bounded downshift, not uncontrolled repeated attempts.

## Provider evaluation gate
`is_real_provider` must be proven by artifact metadata and provider inference job logs; mock provider is conspicuous in UI and export. `provider_license_verified` is a separate flag; unknown license requires review. `available` means health and actual model presence, not code package installed.
