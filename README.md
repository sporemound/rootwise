# ParetoDrive 0.6.0-alpha

ParetoDrive contains a deliberately narrow, metadata-only filesystem inventory scanner, a
separate read-only review interface, structural analytics, robust Pareto review ranking, and a
proposal-only hierarchical optimizer.
It records directory entries and metadata in an external SQLite database and can stream a
canonical NDJSON representation. It does not read source-file contents, hash source files,
classify data, create archives, reorganize files, or delete anything.

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
standard library. Stage 0.5 analytics and Stage 0.6 optimizer dependencies are optional and
separately locked.

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
