# Rootwise

**Audit-first filesystem inventory and evidence-based storage planning for large, disorganized
data collections.**

Rootwise is a local-first tool for understanding what is stored on a drive before making decisions
about preservation, archival, reorganization, or space recovery. It records a bounded metadata
inventory outside the source volume, supports query-only review and separate human decisions,
derives explainable analysis, and produces non-executable planning proposals.

> **Current status: `0.23.0-alpha`**
>
> Rootwise is unreleased and not approved for irreplaceable production data or the original 3.9+
> TB collection that motivated it. The current acceptance state is `INCOMPLETE`.

## Core capabilities

- **Metadata inventory:** bounded, resumable traversal without reading source-file contents.
- **Read-only review:** query-only inventory search and an optional PySide6 interface.
- **Separate decisions:** revision-checked human decisions and notes outside the raw inventory.
- **Explainable analysis:** structural roles, relationships, uncertainty, and Pareto review ranking.
- **Proposal-only planning:** independently validated storage proposals with no execution ability.
- **Permissioned evidence:** explicit, bounded content hashing isolated from ordinary review.

## Architecture

```text
Source filesystem
        |
        | metadata only
        v
Core scanner --> inventory.db --> Viewer --------> decisions.db
                         |
                         +-----> Analysis --------> derived evidence
                                                    |
decisions.db ---------------------------------------+
                                                    v
                                                 Planning
                                                    |
                                                    v
                                         non-executable proposal
```

Optional content-reading evidence crosses a separate permission boundary. Validation evaluates
artifacts and external evidence but grants no filesystem authority. Rootwise has no archive
executor.

See [ARCHITECTURE.md](ARCHITECTURE.md) for component responsibilities, artifact lifecycles, and
trust boundaries.

## Quick development setup

The locked reference environment uses CPython 3.12 on Windows x86-64 or manylinux x86-64. From a
PowerShell prompt in a clone:

```powershell
$ErrorActionPreference = "Stop"
py -3.12 tools\bootstrap.py
$Python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
& $Python -m pip install --no-deps --editable .
& $Python -m rootwise.cli --help
```

The core runtime has no third-party dependencies. Viewer, analytics, optimizer, and enrichment
dependencies are separately hash-locked. Follow [DEVELOPMENT.md](DEVELOPMENT.md) for the complete
environment, tests, and synthetic end-to-end workflow.

## Current commands

The consolidated `rootwise scan|view|analyze|plan|evidence|verify` hierarchy is the architectural
target. Until that interface is implemented, the installed alpha commands are:

| Task | Current command |
|---|---|
| Scan, export, report, capabilities | `rootwise` |
| Search, decisions, GUI | `rootwise-view` |
| Structural analysis and ranking | `rootwise-analyze`, `rootwise-rank` |
| Proposal generation | `rootwise-optimize` |
| Permissioned content evidence | `rootwise-enrich` |
| Proposal review records | `rootwise-approve`, `rootwise-preflight` |
| Derived evidence workflows | `rootwise-fuse-evidence`, `rootwise-longitudinal`, `rootwise-dependency-graph`, `rootwise-history`, `rootwise-synthesize-evidence` |
| Acceptance and release admission | `rootwise-acceptance` |

Run any command with `--help` before supplying paths. Existing commands remain compatibility
surfaces until a reviewed CLI migration is complete.

## Safety boundary

The default scanner does not read source-file contents, write to the source volume, create
archives, move, rename, copy, link, or delete files, invoke subprocesses, or access the network.
Symlinks, junctions, and reparse points are recorded rather than followed.

Viewer and analysis components consume recorded snapshots instead of opening observed live paths.
A decision, ranking, plan, approval receipt, or preflight manifest never establishes that an
original file is safe to remove.

Read [SECURITY.md](SECURITY.md), the
[safety invariants](docs/safety/safety-invariants.md), and the
[threat model](docs/safety/threat-model.md) before changing a source-facing boundary.

## Major limitations

- The complete million-entry scanner, viewer, and analysis campaign has not run.
- Independent-host replication is incomplete.
- The ordinary viewer is functional but not a complete daily-use file browser.
- Optimizer, enrichment, and derived-evidence scale behavior is not accepted for real data.
- Supplied acceptance evidence is digest-bound but not authenticated.
- No Rust scanner, content-preview service, archive executor, or filesystem action component exists.
- Real-drive use remains prohibited until the required evidence and operator review are complete.

## Documentation

The primary developer reading path is intentionally limited to three documents:

1. This product overview.
2. [ARCHITECTURE.md](ARCHITECTURE.md) for the system model and boundaries.
3. [DEVELOPMENT.md](DEVELOPMENT.md) for installation, testing, and contribution workflows.

After those, use the [documentation index](docs/README.md) to find a specific schema, contract, or
protocol. Historical implementation records are retained under `docs/archive/`, not mixed into the
primary path. Release chronology remains in [CHANGELOG.md](CHANGELOG.md).

## License

Rootwise is licensed under the terms in [LICENSE](LICENSE).
