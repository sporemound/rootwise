# Acceptance and Readiness Validation

Rootwise converts external readiness evidence into canonical, fail-closed manifests and reports.
The acceptance component evaluates evidence created by separate procedures; it does not perform
scans, launch the GUI, create volumes, authenticate evidence producers, or grant filesystem
authority.

The current real-world acceptance state is `INCOMPLETE` until every required gate is recorded and
passes for the exact subject revision.

## Required gates

| Gate | Required claim |
|---|---|
| `scanner_scale` | At least one million observed entries, completed scan, unchanged inputs, and measured duration, RSS, and temporary space within operator budgets |
| `viewer_search_scale` | Scale requirements plus at least 100 queries, bounded p95 latency, and query-only operation |
| `snapshot_pipeline_scale` | At least one million input entries processed within declared resource budgets with unchanged inputs |
| `enrichment_distinct_volume` | Permissioned enrichment across distinct OS volumes, immutable selection, unchanged contents, and acknowledged access-time risk |
| `forced_interruption_recovery` | Observed interruption, durable `STOPPED` state, completed resume, and unchanged contents |
| `database_corruption` | Corruption detected and processing failed closed |
| `metadata_edge_cases` | Long paths, invalid metadata, permission errors, and concurrent mutation tested with required fail-closed results |
| `visible_gui_review` | A real visible desktop session reviewed with no critical defect |
| `independent_replication` | A separate host used a fresh clone of the exact revision, passed mandatory tests, and left contents unchanged |

Resource budgets are operator-declared because acceptable limits depend on the target hardware.
Passing a generously chosen threshold does not prove that the threshold is operationally suitable;
budgets and raw evidence remain review material.

## Discover the schema

```powershell
rootwise verify acceptance guide
```

The command prints every gate and its exact required measurement fields. It does not suggest
passing values.

## Initialize a manifest

Initialization requires explicit identity and time values so Rootwise neither invents claims nor
silently discloses host/account data:

```powershell
rootwise verify acceptance init `
    --output "E:\acceptance\acceptance-evidence.empty.json" `
    --subject-revision "0123456789abcdef0123456789abcdef01234567" `
    --producer "manual-review" `
    --created-at "2026-08-09T00:00:00Z" `
    --host-id "review-host" `
    --os "Windows 10" `
    --python "3.14.3"
```

The output must be new and its parent must exist. An initialized manifest has no gates, so its
first evaluation is necessarily `INCOMPLETE`.

## Record one gate immutably

Create a canonical JSON measurements object with exactly the fields reported by `guide`: UTF-8,
sorted keys, compact separators, and one trailing newline. For a confirmed visible GUI review:

```json
{"no_critical_defects":true,"review_completed":true,"visible_session":true}
```

Record the external evidence, measurements, and notes into a new manifest revision:

```powershell
rootwise verify acceptance record `
    --manifest "E:\acceptance\acceptance-evidence.empty.json" `
    --evidence "E:\acceptance\visible-gui-review.json" `
    --measurements "E:\acceptance\visible-gui-measurements.json" `
    --output "E:\acceptance\acceptance-evidence.gui.json" `
    --gate "visible_gui_review" `
    --notes "Visible review of the retained synthetic inventory."
```

All four paths must be distinct. Evidence is stream-hashed with SHA-256. Existing gates must be
canonical, sorted, unique, and valid; a duplicate gate is rejected rather than replaced. Rootwise
computes whether the supplied measurements pass the gate rule, so recording negative evidence
preserves an explicit `FAIL`.

## Evaluate and inspect

```powershell
rootwise verify acceptance evaluate `
    --manifest "E:\acceptance\acceptance-evidence.json" `
    --report "E:\acceptance\acceptance-report.json"

rootwise verify acceptance inspect `
    --report "E:\acceptance\acceptance-report.json"
```

The manifest and report must be distinct sibling files, and the report path must be new. Evaluation
checks schema, canonical encoding, bounds, gate rules, and the complete gate set. Inspection
recomputes the report digest, every gate status and reason, the sorted complete gate set, and the
aggregate status.

Exit codes are:

- `0`: every required gate passed (`PASS`);
- `2`: a valid report was written or inspected with `FAIL` or `INCOMPLETE`; and
- `1`: malformed, tampered, inconsistent, or invalid input/output was rejected.

A supplied failing gate takes precedence over missing evidence. Missing gates with no supplied
failure produce `INCOMPLETE`.

## Trust boundary

Rootwise verifies external evidence bytes while recording and stores their SHA-256 digests. Later
evaluation and inspection bind those digests but do not reopen the evidence. A digest cannot prove
that bytes are truthful, independently produced, or operationally adequate. Producer names, host
identifiers, reviewer identities, and timestamps are not authenticated.

Acceptance adds no source traversal, content read, GUI launch, volume management, network, archive,
move, rename, copy, deletion, optimization, approval, or execution capability. A `PASS` report is a
readiness record, not authority over inventoried files.

The original component-era documents are preserved as
[contract](../archive/acceptance-contract-0.16.md),
[guided workflow](../archive/acceptance-workflow-0.17.md), and
[immutable recording](../archive/acceptance-recording-0.18.md) records.
