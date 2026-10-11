# 14 — Licensing, privacy, AI-generated media, abuse prevention

## Key license finding (checked 2026-10-12)
WanGP `LICENSE.txt` is **WanGP Community License 2.0**, permitting local/internal company use and output creation, with restrictions on paid API/SaaS, embedding/white-label/monetized access; direct output sale/credit conditions described in full text. **It is NOT permissively licensed for arbitrary commercial distribution.** If packaging or selling AI Movie Studio with WanGP bundled, stop to seek clear rights/authorization. Keep provider as separate user-installed optional integration, still review what counts as embedding under the license. This is a product design gate, not a loophole.

Model checkpoints/LoRAs remain under their own licenses; code license doesn't license weights, likeness, training data or music. Maintain machine-readable `asset_rights`, `model_license`, attribution rules and manual user acknowledgments. Avoid default copyrighted movie franchise characters or impersonation; permit original work and rights-owned references.

## User permissions and privacy
App must be local by default. No automatic upload of scripts, images, voices or generated videos. Third-party APIs are opt-in and show provider, data sent, cost policy and terms; explicit consent per provider, not hidden toggle. Do not store secrets in Git, SQLite plaintext if avoidable, or logs. Local file scanning only inside selected project roots. AI-generated content is labeled in metadata/UI where relevant; platform disclosure policies may apply to publishing.

## Likeness, voices and sensitive outputs
Use licensed synthetic voices or user's consensual voice input; reject/flag unauthorized cloning or deception of identifiable individuals. Avoid generating nonconsensual explicit likeness media, minors in sexualized content, deceptive public figure endorsements, or instructions for illegal acts. Local user photos treated private and deletable, metadata minimized. Honor applicable local laws and platform rules; implement abuse controls appropriate to a future public release.

## Security threat model
Prompt injection in imported scripts/web descriptions must not cause tool use, filesystem reads outside project root, code execution, destructive commands, uploads or prompt-based policy bypass. LLM returns data only; validated JSON -> domain operations. No arbitrary filenames from model in shell. FFmpeg input URLs disabled unless explicitly authorized; path traversal blocked; zip archives screened for symlinks and `../`; subprocess command list (no `shell=True`). Bound uploaded media size and decompress cost. Rate limit local create actions and cap jobs to avoid disk exhaustion. Web UI localhost, no unauthenticated bind to 0.0.0.0.

## Commercial distribution checkpoint
Before adding SaaS/paid endpoints/cloud workers/marketplace, re-audit licensing for WanGP, FramePack, ComfyUI, model cards, Remotion (pricing for automation products differs), packaged FFmpeg encoder licenses, fonts, music and SFX. Store signed review checklist. For personal/internal use, packaging stays private; do not imply ownership or exclusive rights to generated material.

## Resource and physical safety
Long laptop GPU workloads create heat, power consumption and fan wear. Default to low-memory profile, AC power and unobstructed vents. Avoid disabling laptop thermal safeguards. Do not change Windows paging or GPU driver automatically. Expose Stop and job caps.
