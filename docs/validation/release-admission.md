# Release Verification and Admission

Rootwise separates local verification, deterministic source packaging, fresh-extraction
verification, release admission, and admission-chain verification. Each step binds existing
artifacts; none signs, publishes, executes, or grants authority over an inventoried filesystem.

No real release admission can be issued while the exact revision's acceptance report is not a
complete `PASS`.

## Local verification and source archive

From the repository root in the full locked contributor environment:

```powershell
$ErrorActionPreference = "Stop"
$Python = (Resolve-Path ".\.venv\Scripts\python.exe").Path

& $Python tools\verify.py
& $Python tools\build_release.py
& $Python tools\verify_release.py
```

`tools/verify.py` runs mandatory tests and synthetic installed workflows, records dependency and
revision evidence under `artifacts/`, and verifies that source files are unchanged. The source
builder refuses missing or failed verification and refuses any source that differs from the
verified manifest. Fresh-extraction verification unpacks the deterministic archive into a new
temporary directory and reruns verification there.

Checksums establish artifact identity, not correctness or producer authenticity.

## Admission inputs

Admission consumes four existing regular files:

- a canonical acceptance report whose recomputed status is `PASS` with all nine gates;
- the exact source archive proposed for admission;
- `BUILD_PROVENANCE.json` from the verified source tree; and
- `VERIFY-RELEASE.json` from a successful fresh-extraction verification.

The report subject revision must equal the verified provenance revision. Provenance revision
checking and fresh-extraction verification must have passed. Malformed, incomplete, failed,
inconsistent, reused, changing, or oversized inputs are rejected before output is written.

## Create an admission receipt

```powershell
rootwise-acceptance admit `
    --report "E:\acceptance\report.json" `
    --archive "E:\rootwise-release\rootwise-0.23.0-alpha-source.zip" `
    --provenance "E:\rootwise-release\BUILD_PROVENANCE.json" `
    --verification "E:\rootwise-release\VERIFY-RELEASE.json" `
    --output "E:\acceptance\rootwise-admission.json"
```

The output must be new and distinct from every input. A successful canonical receipt binds the
source revision, source-manifest digest, acceptance semantic digest, archive name and streaming
SHA-256, provenance, and extraction verification. Its semantic `receipt_digest` covers the receipt
body before that field is inserted; the SHA-256 of the complete file is a separate transport hash.
The receipt explicitly records `filesystem_execution_authorized: false`.

## Verify the complete chain

```powershell
rootwise-acceptance verify-admission `
    --receipt "E:\acceptance\rootwise-admission.json" `
    --report "E:\acceptance\report.json" `
    --archive "E:\rootwise-release\rootwise-0.23.0-alpha-source.zip" `
    --provenance "E:\rootwise-release\BUILD_PROVENANCE.json" `
    --verification "E:\rootwise-release\VERIFY-RELEASE.json"
```

The verifier writes no output file. It recomputes canonical receipt semantics, all-nine-gate
acceptance status, revision lineage, archive identity, build provenance, extraction evidence, and
every binding digest. It detects metadata-visible archive mutation during streaming hashing and
requires the false filesystem-authorization flag. Success emits `status: VERIFIED` and exits `0`;
rejected input exits `1`.

## Trust boundary

`VERIFIED` means that the supplied chain remains internally consistent under Rootwise's
deterministic rules. It does not authenticate evidence producers, establish a trusted timestamp,
provide a digital signature, prove independent replication, publish an archive, read inventoried
source contents, or authorize archive creation/removal. An `INCOMPLETE` report cannot be promoted
through admission or verification.

The original component-era admission and verification documents are preserved as
[release admission](../archive/release-admission-0.19.md) and
[admission verification](../archive/admission-verification-0.20.md) records.
