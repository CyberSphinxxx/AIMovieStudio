# AI Movie Studio handoff — 2026-10-16 (Asia/Manila)

## Current outcome

Application unfinished. Explicit demo works end to end; native writing quality/image/video and release gates remain unproven. No cloud accounts, model downloads, OS/security changes or native inference this continuation. Local branch main; no remote changes. Earlier current checkpoints: d2ed4da exact flashback moments, d06b61a stale continuation guard,25961cd draft story-time controls. Inspect git status/log before editing; the coherent legacy timing slice and its evidence are being checkpointed next.

## Verified current software

Optional flashback_after_shot distinguishes legacy episode start, setup0 and afterN; derives timing from linked immutable evidence and refuses relevant unknowns. Current draft editor can change/clear story time with sparse explicit-null semantics, captured revision, original history/IDs/lengths preserved. Later production requires prior job SUCCEEDED and episode COMPLETED.

New POST /api/projects/{pid}/canon/{event_id}/timing appends a source-linked canon_timing_revision, retains raw facts/media, validates expected revision/reviewed source/count/no active jobs or running steps, marks later episodes REVIEW_REQUIRED. Projection uses highest valid project revision, ambiguous latest timing fails closed. CanonTimeline shows human-readable facts and optional timing correction; open-form revision stays captured during polling. Backup/reopen/import into populated library with changed audit sequence tested. Produced-story replacement/review and arbitrary world-clock/prose semantics remain open.

Current product backend full **568PASS508.70s**, one existing Starlette warning, canon-timing-full-backend.log. New harness guard thereafter4tests plus31timing checks **35PASS9.89s**, canon-timing-final-targets.log; no app backend change after full run. Ruff/static frontend lint/type/eightVitest/build pass;1751modules2.55s. Current mobile timing flow final1EdgePASS7.5s (case4.9/wrapper11.329), ab72faa...; screens viewed, Axe/nooverflow/stale polling edit guard/original facts/scripts/IDs checked. Previous draft time mobileflow1PASS4.9s,83related tests90.05s.

## Full browser gate stopped — do not claim19PASS

All19 UI cases attempted in isolated sample library f8a1dadbd6184594ab8a04b3d753d332. Baseline2.12GiB ->min0.27GiB after52.015s; developer guard stopped/contained only owned server/browser/children. Log shows3completed passes, one Export-folder test failed its old5second render wait, next reference case interrupted. No complete19-case report. Trace shows every stage progressing; subsequent read-only sample inspection confirms COMPLETED/one valid probed mock export. Test wait now bounded30s; full corrected run remains unverified. Native guards unchanged.

Full runner now requires3GiB startup (singlecase0.75) and keeps0.3GiB ongoing/unknown-stop/600s max for full suite (160singlecase). Regression1red3green0.45s ->4PASS within35finaltargets. Actual readiness command exits1before fixture/children because currentRAM1.63GiB. Do not blindly repeat while low. Command when safe:
`tools/app-test-env/Scripts/python.exe -s -m scripts.checkpoint_browser_smoke --all`

Full failure/partial traces/logs/samples preserved in canon-timing-all-browser.log/checkpoint-browser-f8a...json/canon-full-interrupted-browser-artifacts.zip.47priorPNG files4274625bytes byte-archived under ops/archive/ui-before-canon-full-585ef231bef34a3181dd617ad04b4762 with manifest/hash. Rolling browser-tests.json still refers to the earlier completed single-case report, not the interrupted full run. Earlier --list command replaced one rolling report; that exact report was lost but original executed log/telemetry remain. Inventory JSON explicitly NOT_EXECUTED retained and actual single case rerun restored rolling report. Future inventories use --reporter=list. No failures rewritten as passing.

## Native approvals/resources remain unchanged

Human approved bounded image-only encoder experiment, docs/ENCODER_EXPERIMENT_PROPOSAL.md/APPROVALS. Official Qwen3-4B-GGUF Q4_K_M installed/unselected, revisionbc640142c66e1fdd12af0bd68f40445458f3869b;2497280256bytes/SHA7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5. Receipt tools/gpu/encoder-experiment-receipt.json. No inference yet; single reservation absent. Latest canon-timing-final-resource-gate.json1.63GiB RAM (guard1.62)/4974MiBfreeVRAM/66C/ownerFREE fails5GiB startup. User prefers coding while freeing memory later; do not repeat readiness questions or terminate user applications.

One already-approved image only after fresh>=5GiB RAM/4096MiBfreeVRAM/<85C/no owner:
`tools/app-test-env/Scripts/python.exe -s -m scripts.gpu_smoke image --encoder-experiment --max-seconds 300`
512square/4steps/seed42/SDPA/profile5/buffersoff;0.5s sampling,2GiB ongoing/unknown-stop, durable one-attempt reservation before model call. Failure/interruption does not refund. Inspect actual media/telemetry/quality before any PASS. Preserve original failed image reports.

Experiment cap2.6GB cumulative incl26522research/3GB installation disk; received2497306778/remreserved102693222. Overall GPU received13893604149/reserved5722749396/accounted19616353545 under32GB/40GB. Futurevideo14805043208 would exceed32GB by2421396753; video explicitlyDEFERRED until imagePASS and complete cumulative-budget review. No download/cap increase/new restrictive terms authorized.

CPU4B separate approved writer requires7GiB RAM,2GiB running, original269.719s failure leaves330.281s of600; no reservation. Only after safe fresh RAM use saved-plan isolated clone/max320+10cleanup:
`tools/app-test-env/Scripts/python.exe -s -m scripts.story_batch_smoke --profile cpu_4b --max-seconds 320 --reuse-plan`
Stop first failed section, review screenplay quality separately.1.5B manualqualityFAILED, no unchanged retry; image encoder is not writer weights. Native ownership shared across cooperating updated copies/providers, external AI apps/old builds do not cooperate.

## Run and next work

Main app was not started by these tests. Final own server/browser processes exited; no listener8765 observed;2sHTTP health timed out (canon-timing-service-state.json), no claim of live health. Launch original library with `.\StartStudio.cmd`.

1. Collect/checkpoint current slice; full19UI only after3GiB available. Save screenshot/log bytes before reusing rolling paths. Source UI is already built.
2. Follow ops/PLAN_NEXT.md: narrow explicit review for a produced unchanged movie after canonical edits, keeping original exports/canon and rejecting structured contradictions. A complete produced-story rewrite requires immutable new edition design. Reproduce before choosing implementation.
3. Opportunistic resource rechecks may unlock already-approved native tests; do not ask for same approval again. Other gates: true story/identity/motion/listening quality, real long series, clean Windows account, vendor90advisories/83license findings and distribution rights. No background work after session ends.

Previous handoff exact bytes: ops/archive/HANDOFF-2026-10-16-before-canon-timing-refresh.md, SHA2564daba7b6f7e8d21cba4a43f79f6619519571aa4f2271dc8a546186690749ef4c. Full command/failure history remains in PROGRESS/DECISIONS/BLOCKERS/evidence and original archives.
