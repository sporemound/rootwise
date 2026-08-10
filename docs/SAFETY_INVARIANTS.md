# Safety Invariants

The words **must** and **never** are testable requirements for production scanner modules.

1. Source files are never opened for writing.
2. Source-file contents are not read in audit mode.
3. Database and output artifacts are outside the source volume.
4. Production scanner modules contain no delete, move, rename, replace, copy, link, or archive APIs.
5. Symlinks, junctions, and reparse points are not followed.
6. Scanner concurrency is bounded; audit.2 uses one traversal worker.
7. Pending work is a persisted SQLite frontier, not an unbounded memory queue.
8. SQLite batch size is positive, configurable, and bounded by policy.
9. Scan rate is configurable.
10. Cancellation is explicit and tested.
11. Resume state is explicit and tested.
12. Partial scans cannot appear `COMPLETE`.
13. Errors are recorded structurally.
14. Observations never imply deletion safety.
15. Raw observations are separate from future analysis.
16. User decisions are outside this scanner and cannot be overwritten by it.
17. Scanner runtime contains no network client imports or calls.
18. Scanner runtime does not invoke subprocesses or shells.
19. Source and destination volume identities resolve before scanning.
20. Failure to resolve a safety boundary aborts.
21. A second process cannot open the same inventory database while the scanner lease is held.
22. A stale `RUNNING` session is recoverable only after acquiring that exclusive lease.
23. Resource-bound stops are recorded as `STOPPED`, never `COMPLETE`.

Output files other than SQLite are created exclusively and must not already exist. The write guard
verifies the opened final object before data is written. SQLite's opened path object and volume are
revalidated before schema/inventory writes, and its exact durable rollback-journal path is
authorized in advance. The approved destination directory is an operator-controlled trust boundary.

Allowed session transitions are `RUNNING -> COMPLETE`, `RUNNING -> STOPPED`, and
`RUNNING -> FAILED`. Resume transitions a selected `STOPPED` or `FAILED` session back to `RUNNING`;
it never resumes `COMPLETE`.

Static tests inspect the Python syntax tree for forbidden imports and calls. Static inspection is
one tested property, not proof that the operating system or filesystem enforces read-only access.
