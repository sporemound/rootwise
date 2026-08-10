# 0.3 Viewer Trust Model

`rootwise view` dispatches lazily to the separate Viewer package without importing or constructing
the source-facing scanner implementation. The Viewer receives
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

## Stage 0.21a decision visibility

Each bounded result page receives one parameterized lookup of current decisions from the separate
decision database. Decision, revision, and note are displayed beside their inventory subject;
recorded rows use bold text and an explicit `RECORDED:` label without supplying custom foreground
or background colors, while undecided rows remain explicit. Selecting a row synchronizes the editor
with the displayed current revision, and a successful write refreshes that row immediately.
Functional File, View, Decisions, and Help menus expose only existing bounded review operations,
including current decision history and explicit safety information. These presentation changes do
not join the decision database into the inventory connection, make the inventory writable, open an
observed path, or add filesystem execution capability.

## Stage 0.24 product-experience contract

The proposed everyday browser preserves this boundary across details, compact-list, and generic
tile presentations; inventory-only directory navigation; preferences; saved searches; bookmarks;
and metadata inspection. Every interaction is classified in
`docs/architecture/viewer-experience.md`. Actual
source-derived previews remain a separately permissioned content-reading process, while live-path
opening and filesystem mutation remain prohibited viewer capabilities. Stage 0.24 is documentation
only and does not implement or test those proposed interactions.
