# Developing Rootwise

This is the cold-start guide for contributors. Read [README.md](README.md) first for the product
scope and [ARCHITECTURE.md](ARCHITECTURE.md) for component authority. Historical implementation
stages are not required to install, test, or change the project.

Rootwise is an alpha filesystem-observation system. Use synthetic or disposable inputs while
developing. Do not point a development checkout at irreplaceable data or weaken a fail-closed check
to make a fixture easier to run.

## Prerequisites

- Python 3.11 or newer.
- CPython 3.12 on Windows x86-64 or manylinux x86-64 for the checked-in reference locks.
- Git.
- Two distinct OS volumes for a successful scanner run. The scanner rejects a database on the
  source volume; a different directory on the same volume is not sufficient.
- Optional administrator access only for the disposable Windows VHDX protocol.

The Core runtime has no third-party dependencies. Optional GUI, analytics, optimizer, and content-
evidence dependencies remain separately locked so they do not expand the scanner's dependency
surface.

## Install a contributor environment

Clone the repository, enter its root, and create the hash-locked development environment. On
Windows PowerShell:

```powershell
$ErrorActionPreference = "Stop"
$Repo = "C:\path\to\rootwise"
Set-Location -LiteralPath $Repo

py -3.12 tools\bootstrap.py
$Python = (Resolve-Path ".\.venv\Scripts\python.exe").Path

& $Python -m pip install --no-deps --editable .
```

On a supported Linux host, use `python3.12 tools/bootstrap.py` and
`./.venv/bin/python -m pip install --no-deps --editable .`. The checked-in Viewer lock is currently
Windows-specific, so a complete GUI environment on Linux requires a separately reviewed platform
lock.

Install only the optional domains needed for a narrow change. On the Windows reference platform,
install all four for the full test and repository-verification workflow:

```powershell
$Locks = @(
    "requirements-viewer.lock",
    "requirements-analytics.lock",
    "requirements-optimizer.lock",
    "requirements-enrichment.lock"
)

foreach ($Lock in $Locks) {
    & $Python -m pip install --require-hashes --requirement $Lock
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed: $Lock" }
}

& $Python -m pip install --no-deps --editable .
```

The final editable install is deliberately `--no-deps`: dependencies come from reviewed lock files,
not an unconstrained resolver. Re-run it after changing entry points or package metadata.

## Run the checks

The normal local change loop is:

```powershell
& $Python -m pytest
& ".\.venv\Scripts\ruff.exe" check .
& $Python -m mypy src
```

The repository verification workflow reruns mandatory tests and installed synthetic pipelines,
writes evidence under `artifacts/`, and confirms that the source tree did not change during the
run:

```powershell
& $Python tools\verify.py
```

A passing unit suite does not satisfy platform, scale, visible-GUI, or independent-replication
gates. Those procedures are indexed under [docs/protocols](docs/README.md#protocols) and
[docs/validation](docs/README.md#validation).

Run a focused test during iteration, then the complete suite before publication:

```powershell
& $Python -m pytest tests\test_viewer_cli.py -q
& $Python -m pytest -q
```

## Run a synthetic scanner workflow

The following PowerShell example creates a new disposable source tree and new output directory. Set
`$SourceRoot` to a disposable volume that is distinct from the volume containing `$ArtifactRoot`.
The drive letters are examples, not targets Rootwise chooses for you.

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
$Python = (Resolve-Path (Join-Path $Repo ".venv\Scripts\python.exe")).Path
$SourceRoot = "D:\rootwise-dev-source"
$ArtifactRoot = Join-Path $Repo ".tool-tmp\dev-workflow-01"

if (Test-Path -LiteralPath $SourceRoot) {
    throw "Synthetic source already exists; choose a new explicit path: $SourceRoot"
}
if (Test-Path -LiteralPath $ArtifactRoot) {
    throw "Artifact directory already exists; choose a new run directory: $ArtifactRoot"
}

New-Item -ItemType Directory -Path (Join-Path $SourceRoot "project\src") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $SourceRoot "media") | Out-Null
Set-Content -LiteralPath (Join-Path $SourceRoot "project\pyproject.toml") `
    -Value '[project]' -NoNewline
Set-Content -LiteralPath (Join-Path $SourceRoot "project\src\main.py") `
    -Value 'print("synthetic")' -NoNewline
Set-Content -LiteralPath (Join-Path $SourceRoot "media\notes.txt") `
    -Value 'synthetic review material' -NoNewline
New-Item -ItemType Directory -Path $ArtifactRoot | Out-Null

$Inventory = Join-Path $ArtifactRoot "inventory.db"
$Export = Join-Path $ArtifactRoot "inventory.ndjson"

& $Python -m rootwise.cli capabilities --path $SourceRoot
& $Python -m rootwise.cli scan `
    --source $SourceRoot `
    --database $Inventory `
    --canonical-export $Export `
    --max-files-per-second 100 `
    --batch-size 25
& $Python -m rootwise.cli report --database $Inventory
```

Rootwise performs the authoritative OS-volume check. A successful scan ends with a `COMPLETE`
session. Output files are new-only; choose a new `$ArtifactRoot` for another run rather than
overwriting evidence.

If a second disposable volume is unavailable on Windows, follow the
[disposable VHDX protocol](docs/protocols/disposable-vhdx.md). It is plan-only by default and must
never be aimed at a physical disk or an existing image.

## Launch the viewer

Install `requirements-viewer.lock`, then use the completed synthetic inventory. The decisions
database must be a distinct sibling of the inventory database:

```powershell
$Decisions = Join-Path $ArtifactRoot "decisions.db"

& $Python -m rootwise_view.cli gui `
    --inventory $Inventory `
    --decisions $Decisions
```

For a headless query:

```powershell
& $Python -m rootwise_view.cli search `
    --inventory $Inventory `
    --query "project" `
    --limit 50
```

The Viewer displays inventory observations. It does not check whether an observed path still
exists and cannot open or mutate it.

## Run analysis and ranking

Install `requirements-analytics.lock`, then create new sibling artifacts:

```powershell
$Analysis = Join-Path $ArtifactRoot "analysis.db"
$Ranking = Join-Path $ArtifactRoot "ranking.db"

& $Python -m rootwise_analytics.cli `
    --inventory $Inventory `
    --analysis $Analysis

& $Python -m rootwise_analytics.ranking_cli `
    --analysis $Analysis `
    --ranking $Ranking `
    --review-limit 50
```

Both commands consume completed snapshots. They do not traverse the synthetic source or rewrite
the inventory.

## Produce and inspect a plan

Planning requires at least one directory with an explicit `ARCHIVE_ELIGIBLE` decision. This is
review input, not authorization to archive anything:

```powershell
& $Python -m rootwise_view.cli decide `
    --inventory $Inventory `
    --decisions $Decisions `
    --path "project/src" `
    --decision ARCHIVE_ELIGIBLE `
    --note "Synthetic planning exercise only"

$Plans = Join-Path $ArtifactRoot "plans.db"
& $Python -m rootwise_analytics.optimizer_cli `
    --ranking $Ranking `
    --decisions $Decisions `
    --plans $Plans `
    --maximum-archive-bytes 104857600 `
    --destination-available-bytes 1073741824
```

There is not yet a public plan-inspection command. The following developer-only snippet opens the
plans database in SQLite read-only/query-only mode and prints its validated, unapproved proposals:

```powershell
@'
import json
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve()
connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
connection.execute("PRAGMA query_only=ON")
if connection.execute("PRAGMA application_id").fetchone()[0] != 1346654810:
    raise SystemExit("not a Rootwise plans database")
run = connection.execute(
    "SELECT run_id FROM plan_runs WHERE state='COMPLETE' "
    "ORDER BY finished_at DESC LIMIT 1"
).fetchone()
if run is None:
    raise SystemExit("no complete planning run")
for row in connection.execute(
    "SELECT plan_id,labels_json,objectives_json,validated,approval_state "
    "FROM proposed_plans WHERE run_id=? ORDER BY plan_id",
    (run[0],),
):
    print(json.dumps({
        "plan_id": row[0],
        "labels": json.loads(row[1]),
        "objectives": json.loads(row[2]),
        "validated": bool(row[3]),
        "approval_state": row[4],
    }, sort_keys=True))
connection.close()
'@ | & $Python - $Plans
```

Expected proposals remain `UNAPPROVED`. Rootwise has no command that applies them.

## Branches, pull requests, and releases

- Start from the repository's current GitHub default branch and synchronize it before branching.
- Use one branch and one pull request per architectural concern. Descriptive names such as
  `docs/developer-onboarding`, `refactor/viewer-namespace`, or `fix/inventory-validation` are
  preferred over implementation-stage names.
- Keep structural and behavioral changes separate. State migration impact before changing imports,
  commands, schemas, or artifact identities.
- Preserve compatibility aliases where inexpensive and use deprecation notices before removals.
- Update the relevant active document and `CHANGELOG.md` with behavior changes.
- Run the complete suite and `tools/verify.py` before publishing a reviewable branch.

The distribution version is defined in `pyproject.toml`; component-era `CODE_VERSION` fields also
exist and must not be changed casually because they participate in recorded provenance. Release
chronology belongs in `CHANGELOG.md`, not in primary architecture or onboarding prose.

Release tooling is intentionally fail closed:

```powershell
& $Python tools\verify.py
& $Python tools\build_release.py
& $Python tools\verify_release.py
```

`build_release.py` refuses to package source that differs from its verified manifest, and
`verify_release.py` reruns verification in a fresh extraction. A source archive is not admitted
until the separate acceptance and admission workflow succeeds. See
[release validation](docs/validation/release-admission.md).

## Where a change belongs

| Change | Architectural home | Boundary to preserve |
|---|---|---|
| Traversal, volume identity, inventory, canonical export | Core | Metadata-only source access and guarded external writes |
| Search, presentation, navigation, decisions | Viewer | Query-only inventory; decisions remain separate |
| Structural, ranking, temporal, or fused derivation | Analysis | Completed snapshots only; missing evidence remains unknown |
| Optimization, proposal validation, approval, preflight | Planning | No filesystem execution capability |
| Content hashes or declared relationships | Evidence | Content reads require explicit bounded permission |
| Tests, scale protocols, acceptance, releases | Validation | Evidence evaluation cannot manufacture authority |

Add tests beside the behavior they protect. A source-facing change also requires review against
[SECURITY.md](SECURITY.md), the [safety invariants](docs/safety/safety-invariants.md), and the
[threat model](docs/safety/threat-model.md). Stop and split the work if a structural refactor begins
changing safety semantics.

## Troubleshooting

- **Editable command is missing:** activate the intended environment or invoke its Python by exact
  path, then rerun `python -m pip install --no-deps --editable .`.
- **`PySide6 is required`:** install `requirements-viewer.lock` into the same environment used to
  launch the command.
- **Optional import is missing:** install the matching analytics, optimizer, or enrichment lock;
  do not use an unconstrained upgrade to repair the reference environment.
- **Source and database are rejected as the same volume:** choose genuinely distinct mounted
  volumes. Directory names and drive aliases are not evidence of separation.
- **An output already exists:** choose a new explicit output path. Rootwise intentionally refuses
  many overwrites to preserve evidence.
- **An inventory path is not found:** CLI paths are inventory-relative observations such as
  `project/src`, not current absolute filesystem paths.
- **A test is platform-specific:** unit success does not substitute for the named Windows, exFAT,
  visible-GUI, scale, or independent-host protocol.
- **The real drive seems convenient for testing:** do not use it. Reproduce the behavior with a
  synthetic tree or disposable volume.

The [documentation index](docs/README.md) lists every active reference, protocol, archived record,
and consolidated source document.
