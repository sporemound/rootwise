# ParetoDrive 0.12.0-alpha

ParetoDrive contains a deliberately narrow, metadata-only filesystem inventory scanner, a
separate read-only review interface, structural analytics, robust Pareto review ranking, a
proposal-only hierarchical optimizer, and explicitly permissioned content enrichment.
Stage 0.8 also records an explicit plan selection as a non-executable canonical approval receipt.
Stage 0.9 compiles a bounded metadata-only executor-preflight manifest from that receipt.
Stage 0.10 imports completed enrichment evidence into a new immutable analytical snapshot.
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
$Repo = "E:\Python Scripts\paretodrive"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pytest
```

Expected validation condition: pytest exits with code `0`; any stderr, timeout, interruption,
or skipped mandatory test remains a failed gate in the release evidence.

The optional Windows viewer dependency is separately hash-locked:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\paretodrive"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-viewer.lock
```

Install the optional Windows analytics dependencies in the same way:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\paretodrive"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-analytics.lock
```

The proposal optimizer has its own complete Windows lock:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\paretodrive"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-optimizer.lock
```

The permissioned enrichment component uses the official BLAKE3 Python binding and has its own
complete Windows lock:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\paretodrive"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pip install --require-hashes -r requirements-enrichment.lock
```

## CLI

`paretodrive scan --source SOURCE --database EXTERNAL_DB` validates that the database volume is
different from the source volume before scanning. `paretodrive export` produces canonical NDJSON.
Run `paretodrive report --database DB` for a read-only session summary.

## Read-only viewer

Headless search works without PySide6:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_view.cli search `
    --inventory "E:\inventories\inventory.db" `
    --query "project" `
    --limit 200
```

Launch the GUI with a distinct decisions database:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_view.cli gui `
    --inventory "E:\inventories\inventory.db" `
    --decisions "E:\inventories\decisions.db"
```

Search pages are capped at 500 rows. The current SQLite path search is functionally tested on the
deterministic corpus but is not yet benchmarked at tens of millions of observations.

## Structural analytics

Run deterministic metadata-only analysis against a completed inventory. The analysis database must
be a new file beside the inventory database:

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_analytics.cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_analytics.ranking_cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_analytics.optimizer_cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_enrich.cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_approval.cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_preflight.cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_fusion.cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_longitudinal.cli `
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
$env:PYTHONPATH = "E:\Python Scripts\paretodrive\src"
python -m paretodrive_dependency.cli `
    --longitudinal "E:\inventories\longitudinal.db" `
    --evidence-manifest "E:\inventories\dependency-evidence.json" `
    --output "E:\inventories\dependency-graph.db"
```

Only projects listed as evaluated contribute to evidence coverage. Missing evidence remains
unknown, and only explicit `DEPENDS_ON` records contribute to dependency degrees. This stage does
not parse project files or open source content. See `docs/DEPENDENCY_EVIDENCE_CONTRACT.md`.
