# ParetoDrive 0.2.0-audit.2

ParetoDrive audit.2 is a deliberately narrow, metadata-only filesystem inventory scanner.
It records directory entries and metadata in an external SQLite database and can stream a
canonical NDJSON representation. It does not read source-file contents, hash source files,
classify data, create archives, reorganize files, or delete anything.

This source tree is an audit milestone, not a claim of safety for a real drive. Do not point it
at valuable media until the release gates in `docs/TEST_PROTOCOL.md` have been independently
completed, including disposable exFAT and OS-enforced read-only tests.

Audit.2 adds fail-closed resource controls and disposable Windows exFAT acceptance tooling. The
VHDX tool is plan-only unless an operator supplies its explicit execution switch; ordinary scanner
commands never create, mount, format, or modify volumes.

## Development

Use Python 3.11 or newer. Runtime dependencies are standard-library only.

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\paretodrive"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
python -m pytest
```

Expected validation condition: pytest exits with code `0`; any stderr, timeout, interruption,
or skipped mandatory test remains a failed gate in the release evidence.

## CLI

`paretodrive scan --source SOURCE --database EXTERNAL_DB` validates that the database volume is
different from the source volume before scanning. `paretodrive export` produces canonical NDJSON.
Run `paretodrive report --database DB` for a read-only session summary.
