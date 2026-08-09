# Replication Protocol

1. Clone the exact commit into a clean path.
2. Verify Python and dependency versions; runtime dependencies must be empty.
3. Run `python tools/verify.py` from the repository root.
4. Confirm the subprocess exits zero, emits no stderr, and produces all required evidence JSON.
5. Compare `SOURCE_MANIFEST.json`, test results, safety audit, and canonical fixture digest.
6. Build only after verification succeeds; extract into a fresh environment and rerun verification.
7. On Windows, repeat with a disposable exFAT VHDX and an external database destination.
8. Capture source pre/post manifests and demonstrate byte identity of the synthetic/read-only source.

SQLite bytes are not a cross-platform replication target. Canonical NDJSON uses UTF-8, LF line
endings, stable key order, normalized comparison paths, deterministic record ordering, UTC
timestamps, and excludes volatile session identifiers and wall-clock scan times.

Every result records source revision, platform, interpreter, command, timeout, duration, stdout,
stderr, exit status, and artifact digests. An interrupted or incomplete run is never success.

