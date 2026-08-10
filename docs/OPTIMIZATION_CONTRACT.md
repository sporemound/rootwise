# 0.6 Proposal-Only Optimization Contract

Stage 0.6 reads a `COMPLETE` 0.5 ranking, its recorded `COMPLETE` analysis run, and a query-only
decision snapshot. It writes a new plans database beside those external databases. It never opens
the inventory or observed source paths and contains no archive, copy, move, rename, delete,
subprocess, shell, or network capability.

Only directories with the current explicit `ARCHIVE_ELIGIBLE` decision may receive
`ARCHIVE_AS_UNIT`. `KEEP`, `PROTECT`, and `NOT_REBUILDABLE` are hard protection evidence. Actions
are `KEEP_UNPACKED`, `ARCHIVE_AS_UNIT`, `DEFER_TO_CHILDREN`, and `PROTECTED`; archived parents make
descendants inactive and parent/descendant archives cannot overlap.

The exact tree solver is the deterministic reference for frontiers that remain under the measured
state budget. A budget overrun is recorded as `SKIPPED_LIMIT` before validated evolutionary search
continues. Fixed seeds 0, 1, and 2 drive NSGA-III exploration. R-NSGA-III attempts a safest-plan
refinement; zero-width objective normalization is recorded as a `degenerate-fallback`, and its
suspect evolutionary result is discarded.

Every retained proposal is independently reconstructed and checked for candidate identity,
eligibility, hierarchy, protection, maximum archive size, destination capacity after safety
margin, unique proposed names, and exact objective reconciliation. Objectives remain independent:
negative potential recoverable bytes, remaining loose files, preservation risk, peak temporary
bytes, archive count, and archive incoherence.

All output plans have approval state `UNAPPROVED`. Proposed ZIP names are labels only: Stage 0.6
does not create archives, recover space, approve a plan, or imply that originals may be removed.
The optimizer is fixture-tested, not scale-qualified or approved for the real source.
