# Rootwise 0.22.0-alpha

Rootwise contains a deliberately narrow, metadata-only filesystem inventory scanner, a
separate read-only review interface, structural analytics, robust Pareto review ranking, a
proposal-only hierarchical optimizer, and explicitly permissioned content enrichment.
Stage 0.8 also records an explicit plan selection as a non-executable canonical approval receipt.
Stage 0.9 compiles a bounded metadata-only executor-preflight manifest from that receipt.
Stage 0.10 imports completed enrichment evidence into a new immutable analytical snapshot.

Stage 0.15 completes the Rootwise namespace migration. Commands, Python packages, manifest
schemas, release artifacts, GUI labels, and documentation now use only the Rootwise name. See
`docs/NAMESPACE_MIGRATION.md` for the alpha compatibility boundary.
Stage 0.16 turns scale, recovery, edge-case, visible-GUI, distinct-volume enrichment, and
independent-replication evidence into one canonical fail-closed acceptance report. It evaluates
external evidence but does not perform scans or authenticate evidence producers.
Stage 0.17 adds deterministic empty-manifest initialization, machine-readable gate guidance, and
tamper-detecting report inspection while retaining the Stage 0.16 evaluation syntax. Guided
initialization never pre-populates a passing evidence claim. See `docs/ACCEPTANCE_WORKFLOW.md`.
Stage 0.18 adds immutable gate recording: it hashes external evidence, requires exact canonical
gate-specific measurements, and writes a new manifest revision without replacement or overwrite.
See `docs/ACCEPTANCE_RECORDING.md`.
Stage 0.19 adds fail-closed release-candidate admission. It binds a complete passing acceptance
report to the verified source revision, exact source-archive SHA-256, build provenance, and a
successful fresh-extraction verification result. It does not build, publish, execute, or grant
filesystem authority. See `docs/RELEASE_ADMISSION.md`.
Stage 0.20 adds independent, read-only admission-chain verification. It recomputes the receipt
digest and every report, provenance, archive, and fresh-extraction binding without creating a new
artifact or granting execution authority. See `docs/ADMISSION_VERIFICATION.md`.
Stage 0.21 replaces cached directory-entry metadata with a fresh non-following stat at observation
time. Entries deleted after enumeration become structured errors instead of stale observations;
stable siblings remain observable. See `docs/CONCURRENT_MUTATION_BOUNDARY.md`.
Stage 0.22 adds an explicit, fail-closed operator harness for the million-entry scanner,
snapshot-pipeline, and query-only viewer-search gates. It binds measurements to a clean exact Git
revision, requires declared budgets and new output paths, and never creates a source corpus. See
`docs/SCALE_ACCEPTANCE.md`.




Stage 0.11 compares two immutable snapshots and builds a conservative project relationship graph.
The core scanner records directory entries and metadata in an external SQLite database and can
stream a canonical NDJSON representation. Only the separate Stage 0.7 enrichment command reads
selected source-file contents, and only with an explicit acknowledgement and immutable selection
manifest. No component creates archives, reorganizes files, or deletes anything.

This source tree remains an alpha milestone, not a claim of safety for a real drive. The disposable
exFAT and OS-enforced read-only gates passed locally, but independent replication and real-scale
testing have not.

Audit.2 adds fail-closed resource controls and disposable Windows exFAT acceptance tooling. The
VHDX tool is plan-only unless an operator supplies its explicit execution switch; ordinary scanner
commands never create, mount, format, or modify volumes.

The viewer opens inventory SQLite files in query-only mode. User decisions go to a separate
revisioned database and cannot modify inventory observations or execute filesystem actions.

## Development

Use Python 3.11 or newer. The scanner, viewer backend, and 0.4 structural analysis use only the
standard library. Stage 0.5 analytics, Stage 0.6 optimizer, and Stage 0.7 enrichment dependencies
are optional and separately locked.

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pytest
```

Expected validation condition: pytest exits with code `0`; any stderr, timeout, interruption,
or skipped mandatory test remains a failed gate in the release evidence.

The optional Windows viewer dependency is separately hash-locked:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-viewer.lock
```

Install the optional Windows analytics dependencies in the same way:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-analytics.lock
```

The proposal optimizer has its own complete Windows lock:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-optimizer.lock
```

The permissioned enrichment component uses the official BLAKE3 Python binding and has its own
complete Windows lock:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-enrichment.lock
```

## CLI

`rootwise scan --source SOURCE --database EXTERNAL_DB` validates that the database volume is
different from the source volume before scanning. `rootwise export` produces canonical NDJSON.
Run `rootwise report --database DB` for a read-only session summary.

## Read-only viewer

Headless search works without PySide6:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_view.cli search `
    --inventory "E:\inventories\inventory.db" `
    --query "project" `
    --limit 200
```

Launch the GUI with a distinct decisions database:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_view.cli gui `
    --inventory "E:\inventories\inventory.db" `
    --decisions "E:\inventories\decisions.db"
```

Stage 0.21a displays the current Decision, Revision, and Note beside every result. Undecided rows
are labeled `UNDECIDED`; decided rows use an explicit bold `RECORDED:` label without overriding
the operating-system palette. Selecting a decided row restores its current decision and note in the
editor, and a successful record updates the row immediately. The File, View, Decisions, and Help
menus expose session details, refresh/search, type filters, page navigation, decision values and
history, keyboard shortcuts, and safety information. Page loading uses one bounded parameterized
decision query and does not weaken the inventory database's query-only boundary.


Search pages are capped at 500 rows. The current SQLite path search is functionally tested on the
deterministic corpus but is not yet benchmarked at tens of millions of observations.

## Structural analytics

Run deterministic metadata-only analysis against a completed inventory. The analysis database must
be a new file beside the inventory database:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_analytics.cli `
    --inventory "E:\inventories\inventory.db" `
    --analysis "E:\inventories\analysis.db"
```

The output contains explainable file roles, recursive directory totals, project-marker boundaries,
structural relationship evidence, and per-stage provenance. It does not read observed source paths
or produce archive/delete instructions.

## Pareto review ranking

Rank a completed analysis into a third, new database beside it:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_analytics.ranking_cli `
    --analysis "E:\inventories\analysis.db" `
    --ranking "E:\inventories\ranking.db" `
    --review-limit 100
```

The ranking retains four independent uncertainty intervals, computes robust Pareto fronts only
within explicit cohorts, and emits a bounded human-review queue. It does not modify the analysis
database, inspect the source filesystem, combine the objectives into a single importance score,
or imply any filesystem action.

## Proposal-only optimization

Optimization requires prior explicit `ARCHIVE_ELIGIBLE` decisions and capacity values supplied by
the operator. All three inputs/outputs must be distinct sibling databases:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_analytics.optimizer_cli `
    --ranking "E:\inventories\ranking.db" `
    --decisions "E:\inventories\decisions.db" `
    --plans "E:\inventories\plans.db" `
    --maximum-archive-bytes 107374182400 `
    --destination-available-bytes 1099511627776 `
    --destination-safety-margin 0.15 `
    --generations 20
```

Capacity values are planning constraints, not detected free-space claims. Every result remains
`UNAPPROVED`; proposed names and potential recoverable bytes do not create archives or recover
space. See `docs/OPTIMIZATION_CONTRACT.md` before interpreting any plan.

## Permissioned content enrichment

Stage 0.7 is a separate content-reading boundary. It requires a manifest that pins one complete
inventory session, that snapshot's logical digest, one evidence level, and an explicit sorted list
of relative file paths. The evidence database must be new, beside the inventory database, and on a
different OS volume from the source:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_enrich.cli `
    --inventory "E:\inventories\inventory.db" `
    --source "D:\disposable-source" `
    --selection "E:\inventories\selection.json" `
    --evidence "E:\inventories\evidence.db" `
    --allow-content-read
```

D2 is sampled candidate evidence only. D3 and D4 confirm identical bytes for the selected files,
but no evidence level implies that a file may be moved, archived, or deleted. Content reads can
update access-time metadata depending on the filesystem and mount policy. See
`docs/ENRICHMENT_CONTRACT.md` before using this command.

## Non-executing plan approval

Stage 0.8 accepts a strict declaration that identifies one complete plan run and one validated
proposal by their recorded digests. It independently recomputes the selected plan before writing a
new canonical receipt. The declaration, plans database, and receipt must be distinct siblings.

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_approval.cli `
    --plans "E:\inventories\plans.db" `
    --declaration "E:\inventories\approval-declaration.json" `
    --receipt "E:\inventories\approval-receipt.json"
```

The receipt selects a directory-level proposal for future executor review. It is not an archive
member manifest and explicitly records `false` for execution, archive creation, and original
removal authorization. See `docs/APPROVAL_CONTRACT.md` for the exact declaration schema.

## Metadata-only executor preflight

Stage 0.9 traces the selected plan through its ranking and analysis provenance to one complete
inventory snapshot, then enumerates the observed regular-file members of each selected archive
group. All artifacts must be distinct siblings in the external inventory directory:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_preflight.cli `
    --plans "E:\inventories\plans.db" `
    --approval-receipt "E:\inventories\approval-receipt.json" `
    --inventory "E:\inventories\inventory.db" `
    --manifest "E:\inventories\preflight-manifest.json"
```

The preflight manifest contains inventory observations, not current source validation. It records
`false` for source-content reads, execution, archive creation, and original removal. No archive is
created. See `docs/PREFLIGHT_CONTRACT.md`.

## Enrichment evidence fusion

Stage 0.10 reads one complete structural analysis and one complete enrichment run bound to the
same inventory session and logical digest. It writes a new sibling fusion database without opening
the inventory or any recorded source path:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_fusion.cli `
    --analysis "E:\inventories\analysis.db" `
    --evidence "E:\inventories\evidence.db" `
    --fusion "E:\inventories\fusion.db"
```

D2 remains candidate evidence. Only D3/D4 populate confirmed-member features. Coverage is selected
files divided by observed files; confirmed-member ratio is confirmed members divided by selected
files. Neither metric implies deletion or archive eligibility. See `docs/FUSION_CONTRACT.md`.

## Longitudinal and project-relationship analytics

Stage 0.11 compares two complete analysis runs bound to two complete inventory sessions describing
the same source root and volume. It opens only external databases:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_longitudinal.cli `
    --baseline-analysis "E:\inventories\baseline-analysis.db" `
    --current-analysis "E:\inventories\current-analysis.db" `
    --output "E:\inventories\longitudinal.db"
```

Results distinguish `ADDED`, `REMOVED`, `METADATA_CHANGED`, and `METADATA_UNCHANGED`. The last term
does not mean content equality. Scan-error intersections make additions/removals ambiguous.
Project edges record nested-project or shared-extension-profile evidence; shared extensions
explicitly do not constitute a dependency claim. See `docs/LONGITUDINAL_CONTRACT.md`.

## Explicit project-dependency evidence

Stage 0.12 imports a strict evidence manifest bound to one complete longitudinal run. The
longitudinal database, manifest, and new output database must be distinct siblings:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_dependency.cli `
    --longitudinal "E:\inventories\longitudinal.db" `
    --evidence-manifest "E:\inventories\dependency-evidence.json" `
    --output "E:\inventories\dependency-graph.db"
```

Only projects listed as evaluated contribute to evidence coverage. Missing evidence remains
unknown, and only explicit `DEPENDS_ON` records contribute to dependency degrees. This stage does
not parse project files or open source content. See `docs/DEPENDENCY_EVIDENCE_CONTRACT.md`.

## Multi-snapshot temporal history

Stage 0.13 consumes a canonical manifest containing at least two contiguous Stage 0.11 transition
databases, representing at least three snapshots:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_history.cli `
    --chain-manifest "E:\inventories\history-chain.json" `
    --output "E:\inventories\history.db"
```

The result describes file observation/stability, directory churn, and project activity by snapshot
ordinal. It does not infer renames, content equality, value, or action safety. See
`docs/HISTORY_CONTRACT.md`.

## Multi-evidence review synthesis

Stage 0.14 requires ranking, fusion, dependency, and history artifacts that all resolve to the
same latest analysis and inventory session:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_synthesis.cli `
    --ranking "E:\inventories\ranking.db" `
    --fusion "E:\inventories\fusion.db" `
    --dependency "E:\inventories\dependency.db" `
    --history "E:\inventories\history.db" `
    --output "E:\inventories\synthesis.db"
```

The output joins separate enrichment, dependency, and temporal dimensions to ranking candidate
directories and emits named review signals. It does not create a combined score, alter Pareto
ranks, or authorize action. See `docs/SYNTHESIS_CONTRACT.md`.

## Acceptance and scale evidence

Stage 0.16 evaluates a canonical manifest containing all required readiness gates. The manifest
and new report must be distinct sibling files:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_acceptance.cli `
    --manifest "E:\acceptance\evidence.json" `
    --report "E:\acceptance\report.json"
```

The command exits `0` only for a complete `PASS`, `2` for a valid `FAIL` or `INCOMPLETE` report,
and `1` for a rejected contract. Missing evidence is never treated as passing. See
`docs/ACCEPTANCE_CONTRACT.md`.

## Guided acceptance workflow

Discover the exact gate measurement fields without suggested passing values:

```powershell
python -m rootwise_acceptance.cli guide
```

Create a deterministic evidence-empty manifest with explicit, non-discovered identity fields:

```powershell
python -m rootwise_acceptance.cli init `
    --output "E:\acceptance\evidence-empty.json" `
    --subject-revision "0123456789abcdef0123456789abcdef01234567" `
    --producer "manual-review" `
    --created-at "2026-08-09T00:00:00Z" `
    --host-id "review-host" `
    --os "Windows 10" `
    --python "3.14.3"
```

Use `evaluate` to produce a report and `inspect` to recompute its digest, gate semantics, and
aggregate status. See `docs/ACCEPTANCE_WORKFLOW.md` for the full workflow and exit codes.

## Immutable acceptance gate recording

Create a canonical measurements file containing exactly the fields reported by `guide`, then add
one externally evidenced gate to a new manifest revision:

```powershell
python -m rootwise_acceptance.cli record `
    --manifest "E:\acceptance\evidence-empty.json" `
    --evidence "E:\acceptance\visible-gui-review.json" `
    --measurements "E:\acceptance\visible-gui-measurements.json" `
    --output "E:\acceptance\evidence-with-gui.json" `
    --gate "visible_gui_review" `
    --notes "Confirmed visible review of the retained synthetic inventory."
```

The command computes the evidence SHA-256 itself and reports the selected gate's recomputed
`PASS` or `FAIL`. It refuses output overwrite, path reuse, noncanonical measurements, missing or
extra measurement fields, and replacement of an already recorded gate. It does not open evidence
during later evaluation or authenticate its producer. See `docs/ACCEPTANCE_RECORDING.md`.

## Release-candidate admission

After every acceptance gate genuinely passes and the source archive has passed fresh-extraction
verification, bind those artifacts into a new immutable admission receipt:

```powershell
python -m rootwise_acceptance.cli admit `
    --report "E:\acceptance\report.json" `
    --archive "E:\Python Scripts\rootwise\artifacts\rootwise-0.22.0-alpha-source.zip" `
    --provenance "E:\Python Scripts\rootwise\artifacts\BUILD_PROVENANCE.json" `
    --verification "E:\Python Scripts\rootwise\artifacts\VERIFY-RELEASE.json" `
    --output "E:\acceptance\rootwise-0.22-admission.json"
```

Admission requires a canonical complete `PASS`, matching report/provenance revisions, verified
build lineage, a successful unchanged-source extraction verification, and a new distinct output
path. The receipt binds hashes of every supplied artifact and explicitly grants no filesystem
execution authority. Rootwise's current real acceptance status remains `INCOMPLETE`; synthetic
success-path tests are not a substitute for the nine external gates. See `docs/RELEASE_ADMISSION.md`.

## Admission-chain verification

Independently re-check a receipt and every artifact it binds:

```powershell
python -m rootwise_acceptance.cli verify-admission `
    --receipt "E:\acceptance\rootwise-0.22-admission.json" `
    --report "E:\acceptance\report.json" `
    --archive "E:\Python Scripts\rootwise\artifacts\rootwise-0.22.0-alpha-source.zip" `
    --provenance "E:\Python Scripts\rootwise\artifacts\BUILD_PROVENANCE.json" `
    --verification "E:\Python Scripts\rootwise\artifacts\VERIFY-RELEASE.json"
```

A successful verification emits `status: VERIFIED`. The command requires canonical receipt
semantics, a complete nine-gate acceptance `PASS`, matching revision lineage, unchanged bound
artifact hashes, exact archive/extraction binding, and explicit false filesystem-execution
authorization. It writes no output file and does not authenticate or sign evidence. Rootwise's
real external acceptance remains `INCOMPLETE`, so this workflow currently has no real admission
receipt to verify. See `docs/ADMISSION_VERIFICATION.md`.

## Concurrent metadata mutation

The scanner performs a fresh `os.stat(..., follow_symlinks=False)` for each enumerated entry.
A file or directory deleted between enumeration and observation is omitted and produces a
structured `stat` error. Stable sibling entries continue to be recorded.

This is a point-in-time metadata boundary, not a stable execution handle. Every future component
that could act on a path must independently revalidate its own source observations. No Stage 0.21
component reads source-file contents or authorizes archive, move, rename, or deletion operations.
See `docs/CONCURRENT_MUTATION_BOUNDARY.md`.
