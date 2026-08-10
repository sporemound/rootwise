# 0.11 Longitudinal and Project-Relationship Contract

Stage 0.11 compares two independently complete metadata snapshots. It never scans the source,
opens a recorded source path, reads file content, or modifies its input databases.

## Snapshot validation

Baseline analysis, current analysis, and the new output must be distinct sibling databases. Each
analysis and its recorded inventory are opened SQLite read-only/query-only and held in read
transactions. Stage 0.11 requires complete analysis stages, recomputes all structural analytical
table/output digests, and recomputes each inventory's logical digest.

The sessions must be distinct and must record the same source-root string and volume identity.
This proves analytical lineage; it does not prove that the source is currently mounted or
unchanged.

## Change semantics

Regular observed files are compared by normalized relative path, logical bytes, recorded
modification time, and attribute bits:

- `ADDED`: observed only in the current snapshot;
- `REMOVED`: observed only in the baseline snapshot;
- `METADATA_CHANGED`: observed in both with different compared metadata;
- `METADATA_UNCHANGED`: observed in both with equal compared metadata.

`METADATA_UNCHANGED` is not a content-equality claim. Renames are not inferred. If an added path
intersects a baseline scan-error region, or a removed path intersects a current scan-error region,
its confidence becomes `AMBIGUOUS_ERROR_REGION`.

Directory change features aggregate counts, byte deltas, ambiguity, and churn over the union of
observed file paths. Activity and churn are not treated as value or disposal evidence.

## Project graph semantics

Project nodes come from the deterministic structural-analysis project rules. Stage 0.11 records:

- validated `NESTED_PROJECT` relationships;
- undirected `SHARED_EXTENSION_PROFILE` contextual similarity when the configured Jaccard
  threshold is met.

Shared extensions do not establish imports, references, generation, or dependency. Every such
edge carries `dependency_claim: false`. Dependency in/out degrees and dependency-evidence coverage
remain zero until stronger evidence is implemented. Connected components and degree are navigation
features, not importance scores.

Stage 0.11 contains no content hashing, source-content reads, archive, copy, move, rename, delete,
network, shell, subprocess, approval, or execution capability.
