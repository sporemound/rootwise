# Stage 0.22 Scale Acceptance Harness

`tools/run_scale_acceptance.py` produces external evidence for the `scanner_scale`,
`snapshot_pipeline_scale`, and `viewer_search_scale` gates. It is an operator tool, not part of the
capability-free `rootwise_acceptance` evaluator. It does not generate a corpus, delete a path,
overwrite an output, or treat a sub-million fixture as passing evidence.

Every measured command requires:

- a clean checkout whose full commit ID equals `--subject-revision`;
- explicit finite duration, peak-RSS, and output-space budgets;
- at least 1,000,000 observed entries;
- distinct new evidence and measurements files;
- the explicit `--execute` switch.

The non-executing plan command is:

```powershell
$Revision = (& git rev-parse HEAD).Trim()
python tools\run_scale_acceptance.py plan --subject-revision $Revision
```

## Scanner gate

The operator supplies an existing corpus. The corpus and new inventory must be on distinct OS
volumes. Pre/post manifests hash path, kind, size, and modification time without reading file
contents. The scanner retains all ordinary volume, write-guard, pacing, memory, and free-space
controls. Stage 0.23 can prepare a disposable synthetic corpus and canonical query suite; see
`docs/SCALE_CORPUS.md`. That preparation must complete before this measurement begins.

```powershell
python tools\run_scale_acceptance.py scanner `
    --subject-revision $Revision `
    --source "C:\Rootwise Scale Corpus" `
    --inventory "E:\Rootwise Scale\inventory.db" `
    --evidence "E:\Rootwise Scale\scanner-evidence.json" `
    --measurements "E:\Rootwise Scale\scanner-measurements.json" `
    --maximum-duration-seconds 14400 `
    --maximum-peak-rss-bytes 4294967296 `
    --maximum-temporary-bytes 68719476736 `
    --execute
```

## Viewer-search gate

The query file must be canonical compact JSON with one trailing newline and contain between 100 and
10,000 bounded strings. The inventory is opened in SQLite URI read-only mode with
`PRAGMA query_only=ON`; the harness records every query duration and reports nearest-rank p95.

```powershell
python tools\run_scale_acceptance.py viewer `
    --subject-revision $Revision `
    --inventory "E:\Rootwise Scale\inventory.db" `
    --query-file "E:\Rootwise Scale\queries.json" `
    --evidence "E:\Rootwise Scale\viewer-evidence.json" `
    --measurements "E:\Rootwise Scale\viewer-measurements.json" `
    --maximum-duration-seconds 1800 `
    --maximum-p95-query-seconds 2 `
    --maximum-peak-rss-bytes 2147483648 `
    --maximum-temporary-bytes 0 `
    --execute
```

## Snapshot-pipeline gate

The new analysis database must be a sibling of the inventory. The harness hashes the inventory
before and after, runs the existing snapshot-only structural pipeline, and conservatively counts
the final database and SQLite sidecars against the output-space budget.

```powershell
python tools\run_scale_acceptance.py snapshot `
    --subject-revision $Revision `
    --inventory "E:\Rootwise Scale\inventory.db" `
    --analysis "E:\Rootwise Scale\analysis.db" `
    --evidence "E:\Rootwise Scale\snapshot-evidence.json" `
    --measurements "E:\Rootwise Scale\snapshot-measurements.json" `
    --maximum-duration-seconds 14400 `
    --maximum-peak-rss-bytes 8589934592 `
    --maximum-temporary-bytes 137438953472 `
    --execute
```

The example budgets are illustrative, not endorsed limits. Operators must choose limits appropriate
for the target host. Evidence authenticity, thermal conditions, and independent replication remain
external responsibilities. A passing scale measurement grants no filesystem execution authority.
