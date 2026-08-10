# Admission-chain verification

Stage 0.20 independently verifies a Stage 0.19 release-admission receipt against every artifact it
claims to bind. Verification is read-only and deterministic. It does not create a replacement
receipt, sign or publish anything, execute an archive, or authorize access to inventoried source
contents.

## Command

```powershell
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "E:\Python Scripts\rootwise\src"
python -m rootwise_acceptance.cli verify-admission `
    --receipt "E:\acceptance\rootwise-0.20-admission.json" `
    --report "E:\acceptance\report.json" `
    --archive "E:\Python Scripts\rootwise\artifacts\rootwise-0.20.0-alpha-source.zip" `
    --provenance "E:\Python Scripts\rootwise\artifacts\BUILD_PROVENANCE.json" `
    --verification "E:\Python Scripts\rootwise\artifacts\VERIFY-RELEASE.json"
```

A successful command emits JSON with `status: VERIFIED` and exits `0`. A malformed, noncanonical,
tampered, incomplete, mismatched, reused-path, or changing input is rejected with exit code `1`.
The command never writes an output file.

## Checks

The verifier:

- requires the canonical admission schema and exact receipt fields;
- recomputes the receipt's semantic digest;
- re-inspects the complete acceptance report and requires all nine gates to remain `PASS`;
- revalidates build provenance and report/provenance revision lineage;
- stream-hashes the supplied source archive and detects metadata-visible concurrent mutation;
- requires fresh-extraction verification to name and hash that exact archive;
- recomputes the report, provenance, verification, and archive bindings; and
- requires the receipt to keep filesystem execution authorization explicitly false.

`receipt_digest` covers the canonical receipt body without the digest field. The separately
reported `receipt_file_sha256` covers the complete receipt file including its newline and digest.

## Trust boundary

`VERIFIED` means the supplied artifact chain remains internally consistent under Rootwise's
deterministic rules. It does not authenticate evidence producers, establish a trusted timestamp,
provide a digital signature, prove independent replication, or make an `INCOMPLETE` real-world
acceptance report pass. Rootwise currently has no real admission receipt because the external
acceptance gates are not complete.
