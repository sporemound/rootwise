# Release-candidate admission

Stage 0.19 adds a fail-closed admission decision for an already-built source archive. Admission
is a binding receipt, not a build, test runner, signature, publication, or authorization to act on
the inventoried filesystem.

## Required inputs

The command consumes four existing regular files:

- a canonical Rootwise acceptance report whose recomputed status is `PASS` with every required
  gate present;
- the exact source archive proposed for admission;
- `BUILD_PROVENANCE.json` from the verified source tree; and
- `VERIFY-RELEASE.json` from a successful verification run in a fresh archive extraction.

The acceptance report's subject revision must equal the verified build provenance revision. The
provenance revision check must have passed, and fresh-extraction verification must report `PASS`
with unchanged source. Any malformed, incomplete, failed, inconsistent, reused, or oversized input
is rejected before an output is written.

## Command

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_acceptance.cli admit `
    --report "E:\acceptance\report.json" `
    --archive "E:\Python Scripts\rootwise\artifacts\rootwise-0.22.0-alpha-source.zip" `
    --provenance "E:\Python Scripts\rootwise\artifacts\BUILD_PROVENANCE.json" `
    --verification "E:\Python Scripts\rootwise\artifacts\VERIFY-RELEASE.json" `
    --output "E:\acceptance\rootwise-0.22-admission.json"
```

The output path must be new and distinct from every input. A successful result is canonical JSON
that binds the source revision, source-manifest digest, acceptance report and its semantic digest,
archive filename and streaming SHA-256, provenance, and extraction-verification evidence. Its
`receipt_digest` covers the receipt semantics before that field is added; the SHA-256 of the whole
receipt file is a separate transport hash.

## Safety and trust boundary

An admitted receipt records that the supplied evidence satisfies Rootwise's current deterministic
rules. It does not authenticate the evidence producers, sign the archive, upload or execute it,
create archives, read inventoried source contents, or grant filesystem execution authority. The
receipt explicitly records `filesystem_execution_authorized: false`.

Rootwise's current real acceptance report is still `INCOMPLETE`. Stage 0.19 tests the successful
path with synthetic complete evidence, but does not issue a real release admission until all nine
external acceptance gates have genuinely passed.
