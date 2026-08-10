# 0.13 Multi-Snapshot History Contract

Stage 0.13 derives ordinal temporal features from a contiguous chain of complete Stage 0.11
longitudinal runs. It opens only the canonical chain manifest and sibling longitudinal databases.
Every database is opened SQLite read-only/query-only, and its file-change, directory-change,
project-graph, stage, and run digests are independently checked.

## Chain boundary

The manifest uses schema `rootwise-longitudinal-chain-v1` and contains between 2 and 10,000
ordered transitions, representing at least three snapshots. Each entry is a sibling filename plus
the exact longitudinal run ID and output digest. Adjacent entries must share the same intermediate
inventory session and analysis run. Duplicate databases, path escapes, incomplete runs,
non-canonical JSON, digest mismatches, and discontinuous or reversed links fail closed.

The 10,000-transition bound validates manifest size only. It is not a performance claim.

## Temporal semantics

File observation state is reconstructed at each snapshot ordinal from explicit `ADDED`, `REMOVED`,
`METADATA_CHANGED`, and `METADATA_UNCHANGED` transitions. Features include first/last observed
ordinal, observed-snapshot count, unambiguous appearances/disappearances, metadata changes,
metadata-unchanged transitions, longest stable transition run, observation ratio, ambiguity count,
and current observation state. Error-intersecting sides remain `AMBIGUOUS_NOT_OBSERVED` unless an
adjacent transition provides a definite observation state for that same snapshot.

Snapshot ordinals are not elapsed time. `METADATA_UNCHANGED` is not content equality. Paths are
identities for this analysis; renames are not inferred, so a rename appears as removal plus
addition. Error-ambiguous transitions remain counted explicitly.

Directory features aggregate covered transitions, change counts, ambiguity, cumulative logical
byte delta, and mean/maximum churn. Project features aggregate appearances, disappearances,
changed-file counts, ambiguity, active transitions, and current presence. Activity, inactivity,
stability, and churn are descriptive evidence only; none implies value, archive eligibility, or
disposal safety.

Stage 0.13 contains no source-path access, content hashing, archive, copy, move, rename, delete,
network, shell, subprocess, approval, or execution capability.
