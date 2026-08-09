# Developer Review Notes

## Trust separation

The scanner/viewer/analyzer/optimizer/executor split is appropriate. The most important property is
one-way immutable evidence flow: analysis and optimization must never acquire scanner or executor
capabilities. Keep the future executor in a separately distributed package and repository.

## Language and storage

Python is reasonable for audit.1 because the hot path is OS/SQLite I/O and the runtime dependency
surface is small. Windows handle safety already requires `ctypes`; if acceptance testing reveals
unmanageable handle, cancellation, or filesystem edge cases, a small Rust scanner core is preferable
to accumulating Python platform shims. Do not change languages solely for throughput.

SQLite can handle tens of millions of rows with bounded transactions, a restrained index set,
external free-space monitoring, and measured query plans. Test database growth, checkpoint latency,
crash recovery, and export time at target cardinality before the real drive. Partitioned snapshots
or DuckDB belong downstream, not in the source-facing scanner.

## Analytics and optimization

Canonical NDJSON is a sound replication target if schema/version rules state which OS-specific
fields may differ. Project-boundary tree dynamic programming is a good deterministic baseline;
retain nested-project evidence rather than forcing one root. Independent objective intervals and
interval dominance correctly preserve uncertainty. Use exact tree DP as the oracle and choose the
NSGA-III crossover threshold from measured frontier-state growth, memory, and runtime—not a fixed
candidate count alone.

Hierarchical archive groups with `KEEP_UNPACKED`, `ARCHIVE_AS_UNIT`, `DEFER_TO_CHILDREN`, and
`PROTECTED` naturally encode non-overlap. Temporary space should be a hard constraint with a
conservative safety margin and an independently recomputed peak, not merely an optimizer objective.

## Missing evidence before real-drive use

Required evidence still includes independent Windows reproduction, disposable exFAT VHDX,
OS-enforced read-only source, forced interruption/power-loss recovery, destination-full behavior,
path-length and invalid-metadata cases, hostile concurrent mutation, database corruption, millions-
of-entry stress, thermal observation, and pre/post source manifests. The proposed analytics stack
is intentionally deferred; implementing it before these scanner gates would be premature.
