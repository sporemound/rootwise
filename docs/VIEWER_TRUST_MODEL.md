# 0.3 Viewer Trust Model

`rootwise-view` is a separate package and process from the source-facing scanner. It receives
an existing inventory database; it does not receive or traverse the source root.

## Boundaries

- Inventory SQLite files are opened with URI `mode=ro` and `PRAGMA query_only=ON`.
- Search is allowed only against a `COMPLETE` scan session.
- Search terms, session IDs, limits, and offsets are SQL parameters. Sort expressions are fixed.
- Result pages are bounded to at most 500 rows.
- Display paths are observations only. The viewer does not open them or test their current state.
- User decisions are written to a distinct SQLite database in the inventory database's
  already-approved external directory, never the inventory database or an arbitrary destination.
- Decision updates use an expected revision. A stale or missing revision cannot overwrite an
  existing decision.
- Every accepted decision revision is retained in an append-only event table.
- The viewer has no archive, move, rename, copy, link, delete, network, or subprocess capability.
- PySide6 is an optional viewer dependency and is not imported by scanner modules.

## Claims not made in 0.3

The initial search implementation is a bounded parameterized SQLite query over inventory paths.
It is functionally tested, but has not been benchmarked at tens of millions of rows and is not an
Everything-performance claim. The GUI is not a file manager and cannot execute a decision.
