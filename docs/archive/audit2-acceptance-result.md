# Audit.2 Acceptance Contract

Audit.2 strengthens the source-facing scanner; it does not add analysis, hashing, archiving, or
file-management features.

## Implemented local gates

1. Resume validates SQLite integrity, foreign keys, source root, source volume, and frontier state.
2. Abrupt child-process termination cannot commit a partial SQLite transaction.
3. A configured RSS limit stops the session as `STOPPED` with a structured resource event.
4. A configured destination free-space floor stops before the next scanner batch.
5. Active-window cooldown pacing is bounded and interruptible.
6. Windows volume capability reporting distinguishes exFAT from NTFS-only capabilities.
7. VHDX tooling is plan-only by default and validates every target before an execution request.

## Platform acceptance gates

The following require a disposable Windows host and are not satisfied by unit tests:

- create a new bounded VHDX at an explicitly approved path;
- format only the VHDX disk as exFAT;
- populate it with the deterministic corpus;
- capture a pre-scan manifest;
- remount it OS-enforced read-only;
- scan to a distinct destination volume;
- test cancellation and resume;
- capture an identical post-scan manifest;
- verify the canonical digest and session/event state;
- detach and retain or remove the disposable VHDX by a separate operator decision.

No tool may infer or select a physical disk, the real source drive, or an existing VHD/VHDX.

### Recorded local result

These gates passed on 2026-08-09 using Windows 10 Home and rewritten source commit `2aeae1e`. The harness
used its `storage_diskpart` backend to create only a new workspace-contained 512 MiB VHDX, then
resolved the mounted disk from that exact image path. The exFAT fixture was OS-enforced read-only
during the scanner run. Cancellation and same-session resume produced lifecycle events `STARTED`,
`STOPPED`, `RESUMED`, and `COMPLETE`; the session recorded 30 observations and zero errors.
Content-hashed pre/post manifests were identical. The VHDX was then verified detached and retained.

This is a local platform acceptance result, not independent replication and not evidence from the
real 3.9+ TB source. Generated details are recorded in `artifacts/TEST-EXFAT-VHDX.json`.

## Thermal claim boundary

Audit.2 does not claim access to reliable cross-platform temperature sensors. Instead it provides
deterministic workload pacing: file-rate limiting, bounded batches, active-window limits, cooldown
periods, and an RSS ceiling. Actual temperature and shutdown resistance remain acceptance-test
observations, not inferred safety properties.
