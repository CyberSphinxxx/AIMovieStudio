# Active backlog — 2026-10-14

Do not interpret partial task evidence as full phase acceptance. See PROGRESS and HANDOFF.

| ID | Status | Evidence / remaining work |
|---|---|---|
| F0.01 | DONE_VERIFIED | ops/evidence/*baseline*, actual workstation commands |
| F0.02 | IN_PROGRESS | docs/SOURCE_REGISTER.md; private-use assumption; distribution/weight review incomplete |
| F0.03 | BLOCKED_OS_POLICY | Approved stack/image files installed; actual API smoke blocked by Windows CUDA DLL policy before inference |
| F0.04 | DONE_VERIFIED | Architecture implemented + runnable tests; CPU Python 3.12 deviation recorded |
| F1.01 | DONE_VERIFIED | API and frontend run; build/lint/typecheck pass |
| F1.02 | DONE_VERIFIED | API persistence/idempotency/reopen tests, browser create |
| F1.03 | IN_PROGRESS | Responsive screenshots + Axe passed; broader UI/screen-reader review open |
| F1.04 | IN_PROGRESS | Live RAM/GPU/temp/driver, install versus proof statuses, resource guidance and last native block/refresh tested; CUDA runtime OS-blocked |
| F1.05 | DONE_VERIFIED | Five Edge flows passed including blocked settings save while loading; actual demo playback/download and series prewrite |
| F2.01 | IN_PROGRESS | 1.5B real CPU trials 461.579s total: structure passed, manual writing failed; approved 4B installed/hash-verified, awaiting 7GiB RAM; no reliable writer proof |
| F2.02 | IN_PROGRESS | Finite ending and episode outline persisted; real quality evaluation open |
| F2.03 | IN_PROGRESS | Durable four-shot batches,600s fixture/recovery/partial backup and whole-script continuity verified; real writing quality unproven |
| F2.04 | IN_PROGRESS | Declared ownership/knowledge/location/life before-state checks, export-only canon, prop reference lineage and episode-start flashbacks tested; precise world time/prose semantics open |
| F2.05 | IN_PROGRESS | 10-episode outline fixture; episode2 reference/canon reuse tested; real series not proven |
| F2.06 | DONE_VERIFIED | Ten screenplay checkpoints, interrupted receipt recovery/reuse, no future canon; 3-episode browser flow |
| F3.01 | DONE_VERIFIED | Demo references/keyframes + sidecar receipts/hash/lineage |
| F3.02 | DONE_VERIFIED | Serialized references/frames/clip dependencies and pinned reference IDs |
| F3.03 | BLOCKED_OS_POLICY | Approved image weights verified; torch_cuda.dll blocked before actual inference |
| F3.04 | IN_PROGRESS | Immutable portrait/profile/full-body/angle candidates and future-only selection; mock end-to-end/backup/recovery verified; native view quality blocked |
| F3.05 | IN_PROGRESS | Bounded reference-view requests, original lineage/hash, optimistic selection, pending discard and future-shot pins verified; real inference unverified |
| F4.01 | DONE_VERIFIED | Single OS-lock worker, claims/heartbeat/checkpoints |
| F4.02 | DONE_VERIFIED | Persisted SSE cursor/Last-Event-ID replay and frontend polling tested |
| F4.03 | IN_PROGRESS | Active atomic pause/resume/hash reuse, cancel/no-export, settings freeze and retry budget tests; broader UI smoke open |
| F4.04 | IN_PROGRESS | Sequential scheduling, CPU unload, disk reserve; quota/resource measurements incomplete |
| F4.05 | IN_PROGRESS | First-read IOERR_TRUNCATE reproduced/captured; bounded Windows snapshot retry, atomic read consistency,6 SQLite kills+3 media kills verified; broader interruption release gate open |
| F5.01 | IN_PROGRESS | Official API bridge, offline guard and telemetry; real runtime failed at OS CUDA import; no inference proof |
| F5.02 | BLOCKED_OS_POLICY | Real 6 GB image/video inference NOT TESTED; video download requires image PASS |
| F5.03 | TODO | Sequential real shots and inspection |
| F5.04 | TODO | Validated model-dependent OOM downshift |
| F5.05 | DEFERRED | FramePack >30 GB; first WanGP gate before fallback |
| F6.01 | IN_PROGRESS | Actual SAPI, <=1.15x correction, overflow fails before visuals, hashed WAV stems/SRT/backups tested; broad voice QA open |
| F6.02 | IN_PROGRESS | Original synthetic ambience, no music; managed SFX library open |
| F6.03 | DONE_VERIFIED | Aspect-correct draft demo EDL/concat/shot fades |
| F6.04 | DONE_VERIFIED | Atomic H264/AAC export + FFprobe/full decode/hash |
| F6.05 | IN_PROGRESS | Durable fit copies/hash/canon/subtitle/audio/hardkill/backup verified; latest export Show in folder guard/UI/API/Windows shell success observed; external selection visual QA/custom native HD open |
| F7.01 | DONE_VERIFIED | One-click demo through playable MP4, real failures never substitute demos |
| F7.02 | IN_PROGRESS | Hard media/hash gates; cinematic review not performed |
| F7.03 | IN_PROGRESS | Optional review/pre-media/future edits; immutable one-shot seed retakes, cumulative MP4 cuts, pinned references/audio/canon, originals/earlier copies, bounded attempts, pause/discard/backup/hardkill/API verified; produced-story edits/reference variants/version branches open |
| F7.04 | IN_PROGRESS | Tested viewport/focus/Axe; broader keyboard/screen-reader work remains |
| F7.05 | IN_PROGRESS | Episode2 across reopen uses prior outcome/references; longer real movie open |
| F8.01 | IN_PROGRESS | Actual localhost launcher stop/start observed; approved app-local GPU install; clean-account test open |
| F8.02 | IN_PROGRESS | ZIP-to-Library UI, explicit interrupted-restore resume, paused jobs/IDs/hashes/defaults retained, conflict/security/hardkill/Edge verified; broader manual/troubleshooting review remains |
| F8.03 | IN_PROGRESS | Offline419-package/516-notice hash inventory; official source captures197244bytes;10 tests+16 storage PASS;20 missing notices/2 declaration gaps, converted VAE/source mapping/binary/release rights remain open |
| F8.04 | TODO | Clean Windows account + real GPU resource benchmarks |
| F8.05 | IN_PROGRESS | Main npm/Python audit0; hostile backups/download budgets tested; vendor90 advisories unresolved |
| F8.06 | IN_PROGRESS | Screenshots/evidence/run docs; release still blocked by listed gates |

Next: bounded approved 4B writing test after 7GiB free-RAM guard/readiness, then inspect narrative separately from schema. Independent: F8.03 converted VAE/encoder provenance and missing notices; produced-story revisions/export controls. Latest full core 189 backend PASS259.65s, 34 CPU-profile/setup/status checks PASS5.22s and 10 license checks PASS0.17s; lint/type/build/2Vitest and main audits0. Final 10 Edge flows PASS (see reference-4b-browser-final.log/browser-tests.json). Native GPU remains OS-blocked; no security changes. App remains unfinished.
