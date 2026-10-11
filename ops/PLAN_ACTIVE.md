# Active implementation plan — 2026-10-12

Task/ID: F2.06,F4.02–04,F8.02/05 and F0.03/F3.03 approved provider feasibility.
Behavior: Prewrite a finite season with recoverable screenplay checkpoints; download/restore portable hashed project backups; diagnose hardware honestly; install approved private GPU stack without system changes.
Ground truth: Main app runs through explicitly labeled demo MP4. Actual CPU story works with weak/unreliable quality. Initial checkpoint c05ee35. No pre-existing GPU engine.
Scope: Durable DRAFT steps, completed-canon validation, consistent logical backup archives/new-folder restore, settings freeze on imported resume, live RAM/GPU diagnostics and conservative resource preflight. Approved downloads use pinned sizes/checksums, allocation ledger and offline bridge. Video download requires actual reviewed image PASS.
Safety: 32GB downloads/40GB disk growth, no OS/driver/toolchain/security change. Vendor audit separate from main app. Archives never execute imported commands or overwrite folders.
Tests: Ten-episode prewrite with interrupted receipt recovery; current-death revalidation; backup corruption/traversal/no-overwrite/config-strip and actual resumed MP4; controls/SSE; resource refusal; download resume/budget/hash failures; browser load/save race and Axe.
Observed progress: Earlier full regression passed34 backend,2 frontend and4 Edge tests. Latest recovery/provider/resources targeted22 passed; downloader/policy targeted9 passed. Main audit0. Source/runtime/image files installed. First API smoke failed after44.0s with Windows Application Control blocking torch_cuda.dll, before inference. Telemetry preserved. No GPU image/video proof. Full updated regression next.
Recovery: App-local tools/data retained, isolated runtime, immutable source artifacts; atomic files/SQLite checkpoints; no global changes. OS-blocked GPU path stays blocked while independent work continues.
Result: Implemented slices need final updated browser/full regression before checkpoint. GPU feasibility BLOCKED_OS_POLICY; vendor advisory remediation unresolved.
