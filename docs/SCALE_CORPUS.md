# Stage 0.23 Disposable Scale Corpus Preparation

`tools/prepare_scale_corpus.py` prepares reproducible inputs for the Stage 0.22 scale harness. It
creates zero-byte synthetic files only beneath one explicitly selected disposable corpus root and
writes a canonical query suite and corpus manifest outside that root after full verification. It
does not scan a source, run analytics, collect acceptance evidence, or remove anything.

Creating one million filesystem entries can take hours, consume substantial filesystem metadata,
and create sustained storage and thermal load even though every generated data file is empty. Do
not point this tool at the real source drive, a directory containing user data, a repository, a
home directory, or a filesystem root.

## Safety contract

- Planning performs no writes and never authorizes execution.
- Preparation requires `--execute`, at least 1,000,000 requested files, and an existing parent.
- A first run requires that the corpus root not exist.
- The tool immediately installs an immutable `.rootwise-scale-corpus.json` ownership marker.
- Resume is allowed only when the marker exactly matches and every existing shard/file is a valid,
  contiguous, zero-byte prefix of the requested corpus.
- Foreign files, changed files, links, junctions, gaps, changed specifications, reused outputs,
  and outputs inside the corpus fail closed.
- File creation is single-process, rate-limited, batch-bounded, and optionally paused per batch.
- `--stop-after` and `Ctrl+C` leave a resumable partial corpus and return `STOPPED`; query and
  manifest outputs are not written for a partial corpus.
- No path is deleted, truncated, replaced, or overwritten. Cleanup is always a separate manual
  operator decision after exact-path inspection.

## Plan without writing

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
$Corpus = "D:\rootwise-disposable-scale-corpus"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
Set-Location -LiteralPath $Repo
& ".\.venv-gui\Scripts\python.exe" tools\prepare_scale_corpus.py plan `
    --corpus-root $Corpus `
    --entry-count 1000000 `
    --shard-count 256 `
    --query-count 256
if ($LASTEXITCODE -ne 0) { throw "Scale-corpus planning failed: $LASTEXITCODE" }
```

Expected condition: JSON reports `execution_authorized: false`, `entry_count: 1000000`, and
`automatic_cleanup: false`; `$Corpus` is not created.

## Explicit preparation or resume

Choose a disposable corpus location and an output directory on another OS volume. The following
example is intentionally rate-limited. Re-running the same block resumes only a valid owned
partial corpus; completed output paths must still be new.

```powershell
$ErrorActionPreference = "Stop"
$Repo = "E:\Python Scripts\rootwise"
$Corpus = "D:\rootwise-disposable-scale-corpus"
$Output = "E:\Rootwise Scale\0.23"
$Python = Join-Path $Repo ".venv-gui\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "Missing repo: $Repo" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Missing Python: $Python" }
if (-not (Test-Path -LiteralPath (Split-Path -Parent $Corpus) -PathType Container)) {
    throw "Missing disposable corpus parent"
}
if (-not (Test-Path -LiteralPath $Output -PathType Container)) {
    throw "Create and inspect the external output directory first: $Output"
}
Set-Location -LiteralPath $Repo
& $Python tools\prepare_scale_corpus.py prepare `
    --corpus-root $Corpus `
    --manifest (Join-Path $Output "corpus-manifest.json") `
    --queries (Join-Path $Output "queries.json") `
    --entry-count 1000000 `
    --shard-count 256 `
    --query-count 256 `
    --maximum-files-per-second 10000 `
    --batch-size 1000 `
    --sleep-ms-per-batch 50 `
    --execute
if ($LASTEXITCODE -ne 0) { throw "Scale-corpus preparation did not complete: $LASTEXITCODE" }
```

Expected condition: JSON reports `status: COMPLETE` and `verified_file_count: 1000000`; the two
new canonical output files exist. The scanner will observe the million generated files plus shard
directories and the ownership marker, so its observed count will be slightly larger.

Use the generated `queries.json` with the Stage 0.22 viewer gate after the scanner gate creates the
external inventory. The corpus manifest proves the deterministic path/size specification, not
performance, thermal safety, evidence authenticity, or fitness for the real drive.
