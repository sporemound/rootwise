# Stage 0.16 Acceptance and Scale Evidence Contract

Stage 0.16 converts previously narrative readiness gaps into a canonical, fail-closed acceptance
report. It evaluates evidence produced by separate test procedures; it does not perform scans,
open observed source paths, launch the GUI, create volumes, or claim that supplied evidence is
authentic.

## Command

```powershell
rootwise-acceptance --manifest "E:\acceptance\evidence.json" `
    --report "E:\acceptance\report.json"
```

The manifest and new report must be distinct sibling files. The report is written only after the
complete manifest has passed schema, canonical-encoding, bound, and gate validation. Exit code `0`
means every required gate passed; exit code `2` means a valid report was created with `FAIL` or
`INCOMPLETE`; exit code `1` means the input or output contract was rejected.

## Required gates

- `scanner_scale`: at least one million observed entries, completed scan, unchanged inputs, and
  measured duration, peak RSS, and temporary-space use within declared operator budgets.
- `viewer_search_scale`: the scale requirements plus at least 100 queries, bounded p95 latency,
  and query-only operation.
- `snapshot_pipeline_scale`: at least one million input entries through the snapshot-only
  analytical pipeline within declared resource budgets, with unchanged inputs.
- `enrichment_distinct_volume`: successful explicitly permissioned enrichment across distinct OS
  volumes, immutable selection, unchanged source contents, and acknowledged access-time risk.
- `forced_interruption_recovery`: observed interruption, durable `STOPPED` state, completed resume,
  and unchanged source contents.
- `database_corruption`: corruption detected and processing failed closed.
- `metadata_edge_cases`: long paths, invalid metadata, permission errors, and concurrent mutation
  were tested and failed closed where required.
- `visible_gui_review`: a real visible desktop session was reviewed with no critical defect.
- `independent_replication`: a separate host used a fresh clone of the exact revision, passed all
  mandatory tests, and left source contents unchanged.

Each supplied gate includes a SHA-256 digest of its external evidence. Stage 0.16 records that
digest but cannot prove that the external bytes are truthful or independently produced. Operator
labels and host identifiers are not authenticated.

## Status semantics

- `PASS`: every required gate was supplied and independently satisfied its structural rule.
- `FAIL`: at least one supplied gate failed its rule. A failure takes precedence over missing
  evidence.
- `INCOMPLETE`: no supplied gate failed, but one or more required gates were absent.

Resource budgets are declared by the operator because acceptable limits depend on target hardware
and operating conditions. The evaluator prevents measurements from exceeding those budgets but
does not certify that generously chosen budgets are operationally appropriate. Budgets and raw
evidence therefore remain mandatory review material.

This stage adds no archive, move, rename, deletion, network, source-content, optimizer, approval,
or execution authority. A future executor remains out of scope and belongs in a separately
distributed package and repository.
