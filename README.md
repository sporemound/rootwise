# Rootwise

**Audit-first filesystem inventory and evidence-based storage planning for large, disorganized data collections.**

Rootwise is a local-first tool for understanding what is stored on a drive before making decisions about preservation, archival, reorganization, or space recovery.

It combines a bounded metadata scanner, an external SQLite inventory, a query-only review interface, structural analytics, uncertainty-aware Pareto ranking, and proposal-only archive planning.

> **Current status: `0.23.0-alpha`**
>
> Rootwise is an unreleased development milestone. It is not yet approved for use against irreplaceable production data or the original 3.9+ TB exFAT collection that motivated the project.

## Why Rootwise exists

Ordinary disk analyzers are good at showing which folders are large. They are much less helpful when the real questions are:

- Which files are unique or irreplaceable?
- Which folders contain complete projects?
- Which data can be rebuilt from source files or manifests?
- Which small configuration files are structurally important?
- Which apparent duplicates are only same-size candidates?
- Which inactive directories should be archived rather than deleted?
- Which areas are too uncertain to classify without human review?

Rootwise keeps these dimensions separate instead of reducing everything to one opaque “importance score.”

Typical analytical dimensions include:

```text
storage cost
uniqueness
rebuildability
project relevance
archival value
dependency risk
duplicate evidence
structural coherence
uncertainty
```

## What Rootwise currently does

### Metadata-only inventory

The core scanner can:

- record files and directories without opening source-file contents;
- store observations in an external SQLite database;
- persist its traversal frontier instead of holding the whole drive in memory;
- stop and resume a scan;
- record structured errors;
- enforce configurable pacing, batching, memory, cooldown, and destination-space limits;
- refuse to place its inventory database on the scanned source volume;
- avoid following symbolic links, junctions, and reparse points.

### Read-only review

The viewer can:

- open completed inventory sessions in SQLite query-only mode;
- search observed paths using bounded result pages;
- filter files and directories;
- record decisions in a separate revisioned database;
- display decision history without changing raw inventory observations.

### Structural analytics

Rootwise can derive:

- deterministic file and directory roles;
- recursive directory totals;
- project-marker boundaries;
- structural relationships;
- uncertainty intervals;
- cohort-local Pareto fronts;
- bounded human-review queues.

### Proposal-only planning

Rootwise can produce unapproved archive and storage proposals using:

- exact tree-based Pareto planning for small candidate sets;
- fixed-seed NSGA-III for larger candidate sets;
- preference-focused R-NSGA-III refinement;
- independent deterministic plan validation.

Optimization results do not create archives and do not authorize filesystem changes.

### Optional content enrichment

A separate permission boundary can read only explicitly selected files to produce:

- sampled BLAKE3 candidate evidence;
- full BLAKE3 byte-equality evidence;
- full SHA-256 verification evidence.

Same-size or sampled matches remain candidates. Confirmed byte equality still does not imply that either copy may be archived, moved, or removed.

## Architecture

```text
Source filesystem
        │
        ▼
Metadata-only scanner
        │
        ▼
External SQLite inventory
        │
        ├──────────────► Query-only viewer
        │                       │
        │                       ▼
        │              Revisioned user decisions
        │
        ▼
Structural analytics
        │
        ▼
Pareto review ranking
        │
        ▼
Proposal-only optimizer
        │
        ▼
Non-executable approval and preflight records
```

Optional enrichment is isolated from the default metadata-only path.

Rootwise currently has **no archive executor**.

## Safety boundary

The default scanner does not:

```text
read source-file contents
write to the source volume
create archives
move files
rename files
copy files
create links
delete files
invoke shell commands
access the network
```

A scan is a point-in-time metadata observation, not a stable authorization to act on a path later.

Creating an inventory, ranking, plan, approval receipt, or preflight manifest does not establish that any original file is safe to remove.

See [Safety Invariants](docs/SAFETY_INVARIANTS.md) and [Threat Model](docs/THREAT_MODEL.md) for the exact tested boundaries.

## Development setup

Rootwise requires Python 3.11 or newer.

```powershell
$ErrorActionPreference = "Stop"

$Repo = "C:\path\to\rootwise"

if (-not (Test-Path -LiteralPath $Repo -PathType Container)) {
    throw "Rootwise repository not found: $Repo"
}

Set-Location -LiteralPath $Repo

python -m pip install `
    --require-hashes `
    --requirement requirements-dev.lock

python -m pytest

if ($LASTEXITCODE -ne 0) {
    throw "Rootwise tests failed."
}
```

The core scanner has no third-party runtime dependencies. Optional viewer, analytics, optimizer, and enrichment dependencies are maintained in separate lock files.

To inspect the available commands:

```powershell
$ErrorActionPreference = "Stop"

$Repo = "C:\path\to\rootwise"

if (-not (Test-Path -LiteralPath $Repo -PathType Container)) {
    throw "Rootwise repository not found: $Repo"
}

Set-Location -LiteralPath $Repo

$env:PYTHONPATH = Join-Path $Repo "src"

python -m rootwise.cli --help
python -m rootwise_view.cli --help
python -m rootwise_analytics.cli --help
python -m rootwise_acceptance.cli --help
```

Do not point the current alpha at irreplaceable production data.

## Current validation status

Implemented and tested locally on synthetic or disposable inputs:

- bounded metadata scanning;
- cancellation and resume;
- structured error handling;
- source/output volume separation;
- disposable exFAT VHDX testing;
- OS-enforced read-only testing;
- query-only viewer behavior;
- structural analytics and Pareto ranking;
- proposal-only optimizer workflows;
- permissioned enrichment boundaries;
- canonical evidence and release-verification tooling.

Still incomplete or unaccepted:

- the million-entry scanner campaign;
- million-row analytics acceptance;
- million-entry viewer-search acceptance;
- large optimizer convergence and thermal testing;
- large enrichment workloads;
- independent external replication;
- use against the original 3.9+ TB drive;
- a complete everyday file-browser experience;
- Rust scanner or Rust runtime integration.

The project’s current real acceptance state remains:

```text
INCOMPLETE
```

## Everyday usability still in development

The current viewer is functional, but it is not yet a complete daily-use file browser.

Planned work includes:

- details and compact-list views;
- tile and icon views;
- Back, Forward, and Up navigation;
- breadcrumbs and directory browsing;
- sortable and configurable columns;
- saved searches and bookmarks;
- persistent view preferences;
- metadata inspector panels;
- permissioned thumbnails and previews;
- accessibility and high-DPI refinement.

## Rust direction

The current implementation is Python-first.

Rust has not yet been implemented as the scanner or runtime core. Any Rust migration will begin with a measured read-only probe and parity tests against the existing scanner contract.

The intended long-term boundary is:

```text
Rust
    volume identity
    high-volume metadata traversal
    future hashing and archive execution

Python
    analytics orchestration
    DuckDB and Polars transforms
    sparse graph analysis
    Pareto ranking
    NSGA-III optimization
    evidence and acceptance workflows
```

Rust will not replace the current scanner unless it preserves the same safety semantics and demonstrates a measured benefit.

## Documentation

Start here:

- [Release Status](docs/RELEASE_STATUS.md)
- [Safety Invariants](docs/SAFETY_INVARIANTS.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Viewer Trust Model](docs/VIEWER_TRUST_MODEL.md)
- [Analytics Schema](docs/ANALYTICS_SCHEMA.md)
- [Optimization Contract](docs/OPTIMIZATION_CONTRACT.md)
- [Enrichment Contract](docs/ENRICHMENT_CONTRACT.md)
- [Acceptance Workflow](docs/ACCEPTANCE_WORKFLOW.md)
- [Scale Acceptance](docs/SCALE_ACCEPTANCE.md)
- [Developer Review](docs/DEVELOPER_REVIEW.md)

For chronological implementation details, see [CHANGELOG.md](CHANGELOG.md).

## Near-term roadmap

1. Complete everyday viewer behaviors: list, details, tiles, navigation, sorting, and preferences.
2. Run the disposable million-entry scale campaign introduced in stages 0.22 and 0.23.
3. Add measured viewer and analytics scale evidence.
4. Prototype a contract-compatible Rust read-only scanner.
5. Complete independent replication.
6. Reassess the minimum evidence required before any real-drive scan.
7. Keep any future archive executor separate from inventory, analytics, and optimization.

## License

Rootwise is licensed under the terms in [LICENSE](LICENSE).
