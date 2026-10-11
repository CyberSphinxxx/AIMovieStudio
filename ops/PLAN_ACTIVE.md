# Active plan — 2026-10-12
Task/ID: F2.01 additional CPU writing experiment.
Behavior: Reuse installed CPU runtime with official pinned1.5B weight, guard RAM/hash, bounded resumable real writing-only test and truthful evidence.
Ground truth: Tiny0.5B failed quality/schema;8d30498 bounded orchestration verified71/2/5. Exact official model metadata/license in cpu-story-download-proposal.json.
Slice: Separate reviewed proposal/approval-gated installer, explicit profile, CPU-only sampling, ten-minute/failure ceiling, persisted sections and manual quality review.
Safety: No download until separate human approval. Additional1.2GB network/1.5GB disk; no system changes; original0.5B files retained.
Tests:4 installer fixtures initially PASS;23 profile/API/story PASS; full81 backend/2 Vitest/5 Edge PASS. Later completed-partial EOF repair10 targeted PASS. No actual1.5B inference.
Recovery: Existing runtime/profile/defaults preserved; explicit selection only; interrupted downloads retain charged partials and checked publish.
Progress: Code/proposal verified; human approval question pending. No weights downloaded.
Result: APPROVAL_PENDING for actual installation/inference, not a writing quality pass. Continue independent F7.03 draft editing while waiting.
