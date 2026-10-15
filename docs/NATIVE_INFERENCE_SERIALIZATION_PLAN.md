# Next reliability slice: native inference ownership

Status: **implemented;20ownership/94related backend checks and16Edge passed; full backend regression running** (2026-10-16).

The per-data-directory worker lock is now complemented by `studio/inference_lock.py`: cooperating updated Studio copies, CPU model servers, Ollama requests and WanGP bridge calls share one per-user ownership file. Older copies and independently launched third-party programs do not participate; ordinary hardware guards still apply. No new native model generation was performed to verify this coordination.

Windows default: `%LOCALAPPDATA%/AIMovieStudio/runtime/native-inference.lock` (user-profile fallback); POSIX: `~/.local/state/AIMovieStudio/runtime/native-inference.lock`. Paths are internal, never an HTTP setting. Ownership is nonblocking, the file remains present and unchanged, descriptors are non-inheritable, and only actual contention raises the typed pre-inference `InferenceBusy`. Background HTTP request threads retain ownership until they exit even if the controlling callback is cancelled. This coordinates Studio calls; it does not establish the model-unloading behavior of an independently managed external server after a transport failure.

The scheduler records `INFERENCE_BUSY` in durable resource waits without spending attempts. A probe/acquire race refunds only the unstarted claim, once, preserving prior deadlines and explicit Pause/Stop. In-flight inference failures and crashed attempts still count. Demo/audio/render paths remain independent.

Current proof:20 targeted ownership tests PASS17.85s, including two independently copied modules choosing the same default simulated user-profile file, distinct Store roots/threads/processes, real owner+child and worker kills/recovery, request-thread cancellation, cleanup, deadlines/controls/backup and API automatic wait->demoMP4. Earlier94 provider/resource/story checks PASS23.32s; no native inference/quality claim. A copied-module fixture initially omitted `studio.processes`, failed1/passed18, then was corrected; failure log retained. Full backend and16Edge tests are running; results go in ops/PROGRESS.md.

Use a common app-owned user-profile lock file across copies. Keep it present: deleting/replacing a lock file can let two processes lock different file objects. Use Windows nonblocking byte locking and POSIX nonblocking `flock` with immediate, typed `INFERENCE_BUSY`; other lock I/O errors fail closed. No stale-PID deletion or system/security changes. File location must not be supplied by an HTTP request. Tests inject an isolated path internally.

[Python3.11 msvcrt documentation](https://docs.python.org/3.11/library/msvcrt.html) specifies nonblocking byte-lock failure and explicit region unlocking. [Microsoft's `_locking` reference](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170) distinguishes a locking violation from invalid-descriptor/argument failures. [CreateMutex documentation](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw) warns about precreation of fixed named mutexes and suggests a locked user-profile file for per-user ownership. These API descriptions are research, not laptop acceptance evidence.

Implemented sequence and acceptance scope:

1. Add a small ownership context shared by CPU server, Ollama calls and WanGP bridge lifetime, including child cleanup. Do not hold it for demo/audio/rendering. Repeat resource guards after acquisition. Do not claim control over independently launched third-party apps.
2. Passive scheduler probes return typed `INFERENCE_BUSY` using existing durable `WAITING_RESOURCES`. Preserve the existing deadline and no-attempt waiting, other-project fairness, Pause/Stop, restart and paused imports.
3. Handle the probe/acquire race explicitly: a busy exception before any inference returns the claimed step to READY, refunds only that claim's attempt and records a bounded wait. Do not refund an in-flight failure or revive paused/cancelled work. Direct bounded smokes fail rather than spend test time waiting.
4. Verify threads/processes/independent Store roots, real forced owner kill and reacquisition, exception cleanup, broken lock storage, pre-inference race, cancellation/deadline/backup behavior and provider contract boundaries. Run changed backend tests, full regression and existing waiting UI path. No real model is needed to prove locking; actual generation fit/quality remains separate.

No new model/runtime download or permission is needed for this reversible application change. Preserve the outstanding native experiment limits and image-PASS-before-video gate.
