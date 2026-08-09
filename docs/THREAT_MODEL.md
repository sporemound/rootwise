# Threat Model

## Scope and assets

The audit scanner observes an untrusted filesystem tree and writes inventory state only to an
approved destination on a distinct volume. Protected assets are source names, metadata, directory
structure, source availability, destination capacity, scan integrity, and the truthfulness of
session/evidence records. Source-file contents are explicitly outside the scanner's authority.

## Trust boundaries

1. Untrusted source directory entries cross into metadata parsing.
2. Resolved OS volume identity crosses into the source/destination authorization decision.
3. Scanner observations cross into the external SQLite database.
4. A completed database snapshot crosses into canonical export and the read-only reporter.
5. Operator cancellation crosses into the scan-session state machine.

The database destination and export destination are trusted only after volume identity and path
authorization succeed. Filesystem metadata, names, timestamps, reparse points, and errors are not
trusted. SQLite files are not accepted as immutable merely because a session says `COMPLETE`.

## Plausible failures and controls

- A crafted name attempts path escape: comparison paths reject absolute paths and unresolved `..`.
- A symlink, junction, or reparse point escapes the tree: link-like entries are recorded and never
  traversed; queued directories are reopened through non-following handles and their authorized
  volume identity is revalidated while path components are held against substitution.
- Source and destination aliases identify one volume: OS volume identity, not prefix comparison,
  decides the boundary; unresolved identity aborts.
- Cancellation or power loss makes a partial scan look complete: work frontier and session state
  are committed transactionally; only an exhausted frontier transitions to `COMPLETE`.
- Very large trees exhaust memory or thermally stress the host: one worker, bounded batches,
  persisted frontier, rate limiting, and batch sleeps bound active work.
- Metadata races cause missing entries or errors: failures are structured observations; they do
  not become evidence that an item is absent or disposable.
- Destination paths escape authorization: all writes are checked by the centralized guard and
  recorded after the database becomes available. Non-database outputs use exclusive creation;
  pre-existing final components are rejected.
- Malicious database contents affect a viewer: reporting uses parameterized queries and read-only
  SQLite URI mode; no values are evaluated as code.

## Attacker capabilities and non-goals

An attacker may control source names, nesting, metadata races, inaccessible entries, and link
targets. They may cause denial of service within configured limits. Audit.1 does not defend against
a compromised OS, storage firmware, Python runtime, administrator, or maliciously replaced source
code. It provides no archival/deletion safety conclusion and no content authenticity.

## Residual risk

The approved destination directory is assumed to be operator-controlled; hostile principals with
permission to mutate that directory can still deny service. Filesystem identity APIs vary by OS
and mount topology. exFAT behavior, read-only enforcement,
thermal behavior, and crash recovery require platform acceptance tests. Until those gates pass,
real-drive operation is prohibited by project policy rather than technically impossible.
