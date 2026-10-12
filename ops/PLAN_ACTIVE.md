# Active plan — 2026-10-12
Task/ID: F4.05 bounded SQLite-only restart diagnosis.
Motivation: Capture the extended error code behind the intermittent first-read disk I/O after a hard kill without video/AI workload.
Ground truth: Prior original read failure unclassified; startup IOERR_TRUNCATE is separately identified. Store.connect currently can let rollback failure mask the original exception and setup failures occur outside its diagnostic scope.
Research: Official https://www.sqlite.org/rescode.html checked2026-10-12 distinguishes IOERR_TRUNCATE, FSTAT and other VFS codes; do not assume all disk I/O errors have one cause.
Slice: Three small writer/read/kill/reopen cycles on newly generated sample data, bounded timeout/memory guard, child logs and structured SQLite codes; retain fixture for inspection. Preserve original exception if rollback also fails, attach cleanup diagnostic rather than replacing it. No retry-policy change.
Files: scripts/sqlite_restart_probe.py, studio/storage.py, tests/test_storage_startup.py; memory/evidence.
Safety: No real projects/models/user processes/security changes, no deletion. App-owned child and generated data paths only; no blanket read/write retry or WAL deletion. Probe stops on first failure/resource guard.
Exit: Code capture fixtures (setup/operation/rollback errors); actual three kills, inspect report/database; distinguish not-reproduced from repaired. Only lightweight tests now (initial freeRAM0.68GiB).
Rollback: No schema/retry changes. New sample fixtures are independent; original app data intact.
Progress: Recon complete, implement probe/diagnostic preservation.
Result: IN_PROGRESS.

Progress: First probe captured actual first-read IOERR_TRUNCATE1546. Implemented read-only bounded Windows retry and atomic query-only snapshot, preserved original cleanup exceptions.23 unit/API checks PASS3.44s;6 SQLite kills PASS (5 actualread/1startup retry);3 media hardkills+5export tests PASS39.24s;RuffPASS. FinalRAM1.76GiB.
Result: Observed first-read class repaired/verified, not a claim that every possible disk I/O cause is solved. Native inference blocked. Next F8.02 graphicalrestore.
