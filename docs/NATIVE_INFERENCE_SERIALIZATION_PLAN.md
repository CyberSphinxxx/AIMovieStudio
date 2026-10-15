# Next reliability slice: native inference ownership

Status: **researched, not implemented or verified** (2026-10-15).

The existing worker lock protects one data directory. It does not prevent a direct CPU/GPU smoke tool, another data directory or a portable copy from loading a second model. The latest native tests were manually run without concurrent native jobs; that is not a global serialization guarantee.

Use a common app-owned user-profile lock file across copies. Keep it present: deleting/replacing a lock file can let two processes lock different file objects. Use Windows nonblocking byte locking and POSIX nonblocking `flock` with immediate, typed `INFERENCE_BUSY`; other lock I/O errors fail closed. No stale-PID deletion or system/security changes. File location must not be supplied by an HTTP request. Tests inject an isolated path internally.

[Python3.11 msvcrt documentation](https://docs.python.org/3.11/library/msvcrt.html) specifies nonblocking byte-lock failure and explicit region unlocking. [Microsoft's `_locking` reference](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170) distinguishes a locking violation from invalid-descriptor/argument failures. [CreateMutex documentation](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw) warns about precreation of fixed named mutexes and suggests a locked user-profile file for per-user ownership. These API descriptions are research, not laptop acceptance evidence.

Implementation order:

1. Add a small ownership context shared by CPU server, Ollama calls and WanGP bridge lifetime, including child cleanup. Do not hold it for demo/audio/rendering. Repeat resource guards after acquisition. Do not claim control over independently launched third-party apps.
2. Passive scheduler probes return typed `INFERENCE_BUSY` using existing durable `WAITING_RESOURCES`. Preserve the existing deadline and no-attempt waiting, other-project fairness, Pause/Stop, restart and paused imports.
3. Handle the probe/acquire race explicitly: a busy exception before any inference returns the claimed step to READY, refunds only that claim's attempt and records a bounded wait. Do not refund an in-flight failure or revive paused/cancelled work. Direct bounded smokes fail rather than spend test time waiting.
4. Verify threads/processes/independent Store roots, real forced owner kill and reacquisition, exception cleanup, broken lock storage, pre-inference race, cancellation/deadline/backup behavior and provider contract boundaries. Run changed backend tests, full regression and existing waiting UI path. No real model is needed to prove locking; actual generation fit/quality remains separate.

No new model/runtime download or permission is needed for this reversible application change. Preserve the outstanding native experiment limits and image-PASS-before-video gate.
