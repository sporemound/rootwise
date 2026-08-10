# User Decision Schema

The decision database has application ID `1346654807`, distinct from the inventory application ID.
For the fail-closed 0.3 boundary, it must be a separate file in the inventory database's external
directory.
It stores two representations:

- `current_decisions`: the latest revision for one `(scan_session_id, relative_path)` subject;
- `decision_events`: every accepted revision in insertion order.

Supported values are `KEEP`, `PROTECT`, `ARCHIVE_ELIGIBLE`, `REBUILDABLE`, `NOT_REBUILDABLE`,
`PROJECT_BOUNDARY`, `NOT_A_PROJECT`, `EXCLUDE_FROM_ANALYSIS`, and `UNKNOWN`.

Creating a subject produces revision 1. Updating it requires the caller's exact current revision.
Concurrent or stale edits fail with a conflict and do not append an event. There is no delete API,
and decisions do not alter scanner observations or imply permission to execute filesystem actions.

Stage 0.21a can read the current decisions for one visible page in a single parameterized query.
The supplied page is limited to 500 normalized relative paths, matching the viewer's existing
result bound. This presentation query reads only `current_decisions`; it does not alter inventory
observations or the append-only event history.
