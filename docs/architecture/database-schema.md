# Database Schema

The Core inventory's recommended basename is `inventory.db`; its SQLite application ID is
`1346654806`. Commands still require an explicit path and validate identity rather than filename.

`volumes` stores externally resolved volume facts. `scan_sessions` stores lifecycle state and
configuration. `directories` and `files` store raw observations only. `scan_errors` stores
structured failures. `scan_frontier` is the persistent bounded-work/resume mechanism.
`scan_events` records lifecycle, recovery, and resource-stop events. `canonical_exports` records
completed exports and `application_writes` records guarded outputs.
Each session stores an exact resolved `source_root`; resume requires both that root and the source
volume identity to match. SQLite uses its durable `DELETE` rollback-journal mode with `FULL`
synchronization. The exact `-journal` companion path is authorized by the write guard before the
connection opens; transaction size is bounded by scanner batch size.

A persistent `-scanlock` sidecar is held with an OS-exclusive byte-range/file lock while an
`InventoryDatabase` is open. The OS releases the lock after abrupt process termination, allowing an
explicit resume to distinguish a stale `RUNNING` session from a concurrently active scanner.

No importance, rebuildability, archive eligibility, duplicate confirmation, or deletion advice is
stored in raw observation tables.

Canonical export checks the application ID, SQLite integrity, foreign keys, exhausted frontier,
and recorded row/error counts inside one transaction before emitting a `COMPLETE` header.
