# Execution plans and handoff protocol

For any task spanning >2 components, touching migrations, changing provider contract, or requiring real hardware, create a concise durable plan in `ops/PLAN_ACTIVE.md`:

```
Task/ID:
Motivation/user observable behavior:
Ground truth / files to inspect:
Assumptions and unresolved research:
Smallest vertical slice:
Files/components expected to change:
Safety and licensing review:
Tests and measurable exit criteria:
Rollback/recovery:
Progress (timestamps, actions, observations):
Result (implemented, verified, blocked, deferred):
```

No plans consisting solely of a list of vague tasks. Each step ends in a runnable behavior or artifact. Split into short reviewable edits; guard existing behavior. Do not mark complete because code exists; mark complete when demonstrably tested.

## Continuation after context compaction or a new session
`ops/HANDOFF.md` must contain: last commit hash, branch, environment facts, tests last run and their outcomes, working feature demo commands, exact next backlog ID, pending approvals, known blockers, provider/model selections and required files. Read handoff before editing. Never claim previous results if not witnessed or supported by logs.

## Research note template
For risky claims, include official URL, date checked, scope/version, what verified, limitation/unknown, and recommended decision. Recheck if dependencies change.
