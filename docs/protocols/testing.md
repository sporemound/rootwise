# Test Protocol

## Local mandatory gates

Run `python tools/smoke.py` after bootstrap to verify the installed root command and all six domain
help routes before invoking a workflow.

1. Static AST inspection rejects destructive, archive, network, link-creation, and process APIs.
2. Volume and write-guard unit tests exercise fail-closed identity decisions.
3. Synthetic traversal verifies metadata capture without content reads.
4. Cancellation yields `STOPPED`; resume reaches `COMPLETE` without duplicate observations.
5. Resource tests verify configured batch/frontier limits and approximately bounded process memory.
6. Two canonical exports of equivalent completed synthetic scans have the expected same digest.
7. Pre/post synthetic corpus manifests match.

Tests use only temporary synthetic data. Tooling launches child processes with a timeout, clean
environment, `PYTHONHASHSEED=0`, `TZ=UTC`, fixed locale where supported, captured streams, duration,
and dependency versions. Unexpected stderr, timeout, interruption, skipped mandatory tests,
missing output, or nonzero status fails the gate.

## Platform gates not satisfied locally by unit tests

- Fresh Linux test and extracted-package retest.
- Independent Windows build.
- Disposable exFAT VHDX source on a different destination volume.
- OS-enforced read-only source with matching before/after manifests.
- Observed thermal/resource beta.

No release package or real-drive scan may proceed until all applicable gates are recorded.
