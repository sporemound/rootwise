# 0.9 Metadata-Only Executor-Preflight Contract

The original roadmap did not define a 0.9 milestone. This stage compiles the member observations a
future executor design would need to review, while remaining in a lower-privilege, non-executing
trust domain.

## Provenance chain

The preflight compiler consumes explicit sibling paths for a 0.6 plans database, 0.8 approval
receipt, and raw inventory database. It verifies the approval receipt's canonical SHA-256 and
requires all action authorizations to remain false. Every SQLite input is opened read-only,
query-only, and in a read transaction.

It then verifies this chain:

```text
approval receipt
  -> complete selected plan and exact candidate actions
  -> complete ranking run and plan-input digest
  -> complete analysis run and ranking-input digest
  -> complete inventory session and analysis-input digest
```

Recorded ranking, analysis, and inventory paths must remain within the same external database
directory. The explicitly supplied inventory must be the inventory recorded by the analysis run.

## Member compilation

Only `ARCHIVE_AS_UNIT` directory actions are compiled. Archive roots may not overlap. The compiler
streams the bounded inventory file table and includes only entries recorded as regular `FILE` and
`OBSERVED`. For each group, enumerated file count and logical bytes must exactly match the approved
candidate. Any selected region that intersects a recorded scan error is rejected.

Member fields are inventory observations only:

- normalized relative path;
- logical byte count;
- recorded creation and modification timestamps;
- recorded attribute bits.

They are not evidence that the source currently has the same identity, size, timestamps, or
contents. Stage 0.9 never resolves or opens the recorded source root.

The output is canonical UTF-8 JSON. Its `manifest_digest` is SHA-256 over the canonical manifest
before that digest field is inserted.

## Non-executable output

Every manifest has state `PREFLIGHT_ONLY_NON_EXECUTABLE` and explicitly records false for:

- source-content-read authorization;
- execution authorization;
- archive-creation authorization;
- original-removal authorization.

No destination capacity is observed and no archive is created. A future separately distributed
executor would require a new authorization contract, OS-level source and destination validation,
current member revalidation, bounded archive creation, verification, receipts, and a rule that
originals remain untouched. Stage 0.9 contains no archive, copy, move, rename, delete, network,
shell, subprocess, or source-content-read capability.
