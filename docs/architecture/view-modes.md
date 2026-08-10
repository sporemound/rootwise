# Stage 0.24 View Modes Contract

Status: **DESIGNED**, not implemented. All view modes consume the same bounded query result and
share selection and view state. Switching presentation must not query a live source path, change
the trust boundary, or silently change the active query.

## Required architecture

```text
InventoryReader (query-only, bounded SQL)
        ↓
ResultPage (immutable page rows + query identity)
        ↓
SelectionModel (session ID + relative path)
        ↓
View adapter
   ├── DetailsView
   ├── CompactListView
   └── TileView (Stage 0.28)
```

`ResultPage` must identify the completed session, normalized query, directory scope, kind filter,
sort specification, offset, limit, rows, and whether another page may exist. A selection identity
is `(scan_session_id, relative_path)`, never a row number. The page remains bounded to at most 500
rows; the initial GUI default remains 200.

## Details view

Details view is the information-dense default. Its first implementation provides:

- sortable headers backed by an allowlisted SQL expression, never arbitrary SQL or full-result
  Python sorting;
- resizable and movable columns;
- Column selection through a View menu and header Context menu;
- persistent width, order, visibility, and sort direction in a separate preferences store;
- human-readable Size values while preserving exact bytes in tooltips or the later inspector;
- explicit directory/file Type text in addition to any generic icon;
- one palette-safe selected row and a compact textual Decision state.

Recommended default columns are Name, Path, Type, Size, Modified, and Decision. Revision, Note,
observation status, and extension are optional. Role, Project, and Uncertainty may appear only when
a separately validated analytical artifact supplies them; the current `InventoryItem` contract
does not. Missing analytical fields display “Not available,” not zero or low importance.

## Compact list view

Compact list view maximizes visible names while retaining the same page and selection:

- generic icon plus Name as the primary line;
- optional one-line Path as secondary text;
- Decision badge/text that does not dominate the row;
- single-row keyboard and mouse selection initially;
- bounded rendering from `ResultPage`, with no separate database query.

Compact mode does not hide uncertainty by pretending advanced fields were evaluated. Those fields
belong in Details view or the later metadata inspector when an analytical artifact is attached.

## Tile view

Tile view is deferred to Stage 0.28. It uses generic folder/file-type icons, filename, optional
type or size, and textual badges. Default Tile view size is proposed as 128 logical pixels. It must
use a model/delegate or equivalent virtualized design rather than one heavy widget per result.
Source-derived thumbnails are `PERMISSIONED_CONTENT_READ` and remain outside this contract.

## Shared behavior

- View switching preserves query, directory, sort, page, and selection where the selected path is
  still present. Otherwise selection clears explicitly.
- Selection does not open content. No source path is opened by rendering, tooltips, icon lookup,
  sorting, or switching modes.
- File-type icons are packaged/generic and derived from observed kind/extension only.
- Details view, Compact list view, and Tile view are `METADATA_ONLY`.
- Decision display is `METADATA_ONLY`; recording a decision is `DECISIONS_ONLY`.
- Open/edit/move/rename/delete/archive/shell actions are `PROHIBITED_EXECUTION`.

## Persistent settings

Persistent settings may include window geometry, active view mode, visible columns, column order
and widths, compact secondary-line preference, tile size, and sort order. They must be stored in a
dedicated preferences file/database, not the immutable inventory or decisions database. Invalid or
unknown values fall back to documented defaults without rewriting inventory state.

## Smallest Stage 0.25 slice

The smallest acceptable implementation is:

1. introduce immutable `ResultPage`, `SelectionState`, and `ViewState` types;
2. make the existing table a Details adapter over that shared page;
3. add a Compact list adapter and explicit View menu switch;
4. preserve session, query, kind filter, offset, and relative-path selection across switches;
5. add allowlisted SQL sorting for name, path, type, size, and modified time only;
6. persist active mode plus Details column width/order/visibility and sort specification in a
   separate bounded preferences store;
7. retain one bounded current-decision lookup per page and query-only inventory access;
8. test deterministic sorting, settings validation, selection preservation, 500-row bounds, and
   decision synchronization in both adapters;
9. perform visible dark/light Windows review before merge.

Decision, role, project, and uncertainty sorting; directory navigation; bookmarks; tiles; and the
inspector remain later bounded slices. This avoids inventing joins that the current query model
does not support.
