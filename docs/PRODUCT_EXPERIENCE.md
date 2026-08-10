# Stage 0.24 Product Experience Contract

Status: **DESIGNED**. This document defines ordinary-user behavior before implementation. Stage
0.24 changes no GUI, query, scanner, analytics, optimizer, enrichment, acceptance, or scale code.

Rootwise is an inventory browser, not a live file manager. Its primary surface presents one
completed, immutable scan session and lets a person search, browse, understand, and annotate those
observations. Every location shown is an inventory-relative observation. It is not proof that the
path currently exists.

## Capability classes

- `METADATA_ONLY`: reads bounded rows from the query-only inventory or attached immutable
  analytical artifacts; may write presentation preferences outside the inventory.
- `DECISIONS_ONLY`: writes revision-checked user decisions or notes to the separate decisions
  database already constrained to the external inventory directory.
- `PERMISSIONED_CONTENT_READ`: may open observed source-file contents only through a later,
  separately enabled and bounded preview process. It is not available in Stages 0.24–0.29.
- `PROHIBITED_EXECUTION`: archive, copy, move, rename, delete, link, launch, shell, live-path
  mutation, and any action that treats a decision as execution authority.

No source path is opened by the default viewer. Copying an observed path as text does not test or
open that path.

## Current ordinary-browser inventory

The 0.23 viewer is **IMPLEMENTED**, **UNIT TESTED**, **WINDOWS TESTED** with an offscreen PySide6
window, and previously **VISUALLY TESTED** for its corrected decision selection state. It has:

- one table with Type, Name, Path, Extension, Bytes, Status, Decision, Revision, and Note;
- one selected completed session at a time;
- global normalized path search and file/directory filtering;
- fixed deterministic path order and bounded 200-row pages (backend maximum 500);
- Previous/Next paging, single-row selection, and decision editor synchronization;
- revisioned decisions and history in a separate database;
- File, View, Decisions, and Help menus with the documented shortcuts;
- query-only inventory access and no observed-path opening.

It does not have a shared result-page/view-state model, compact or tile views, directory browsing,
breadcrumbs, Back/Forward/Up history, user sorting, column management, preferences, saved searches,
bookmarks, icons, an inspector, thumbnails, content previews, or an explicit accessibility test
matrix. Those behaviors are **NOT TESTED** because they are not implemented.

## Product decisions proposed for approval

These are recommendations, not silently accepted requirements:

1. **PENDING USER APPROVAL** — First view modes: implement Details view and Compact list view in
   Stage 0.25; retain Tile view for Stage 0.28.
2. **PENDING USER APPROVAL** — Default columns: Name, Path, Type, Size, Modified, and Decision.
   Role, Project, Uncertainty, Revision, Note, status, and technical identifiers are optional.
3. **PENDING USER APPROVAL** — Default tile size: 128 logical pixels, adjustable later without
   changing the result-page bound.
4. **PENDING USER APPROVAL** — Main interface: browse exactly one completed inventory session.
   Session comparison remains a separate analytical workflow, not a main-view mode.
5. **PENDING USER APPROVAL** — Familiar Explorer behavior: single-click selects; Enter or
   double-click enters an observed directory; Alt+Left/Right navigate history; Alt+Up and
   Backspace go to the parent; Ctrl+L focuses inventory breadcrumbs; Ctrl+F focuses search; F5
   reruns the inventory query. Opening live files/folders and all source mutations remain absent.

## Target interaction and safety matrix

| Interaction | Capability | Contract status |
|---|---|---|
| Details view and Compact list view | `METADATA_ONLY` | Stage 0.25 proposed |
| Tile view with generic File-type icons | `METADATA_ONLY` | Stage 0.28 proposed |
| Directory navigation, Breadcrumb, Back, Forward, Up | `METADATA_ONLY` | Stage 0.26 proposed |
| Sorting and Column selection | `METADATA_ONLY` | SQL allowlist and preferences required |
| Persistent settings and window geometry | `METADATA_ONLY` | Separate preferences store required |
| Selection behavior and keyboard navigation | `METADATA_ONLY` | One shared selection model required |
| Record a decision or note; show history | `DECISIONS_ONLY` | Existing capability retained |
| Context menu: copy observed text, inspect, bookmark | `METADATA_ONLY` | No live-path action |
| Context menu: record decision | `DECISIONS_ONLY` | Revision check required |
| Saved searches and Bookmarks | `METADATA_ONLY` | Inventory-relative and session-aware |
| Metadata inspector panel | `METADATA_ONLY` | Stage 0.29 proposed |
| Thumbnails and source-derived previews | `PERMISSIONED_CONTENT_READ` | Stage 0.30 only |
| Open, edit, copy, move, rename, delete, archive, execute | `PROHIBITED_EXECUTION` | Not a viewer capability |

## Ordinary states

- **Loading state:** keep navigation and location visible, disable conflicting commands, expose a
  textual busy state, and never imply results are complete until the bounded query returns.
- **Empty state:** distinguish “empty directory,” “no matches,” and “no completed session.” Show a
  useful next action that remains inside the inventory.
- **Error state:** preserve the previous stable page, show a concise error with expandable detail,
  and never convert query, preference, or decision errors into success.
- **Stale observation state:** always label the view as an inventory snapshot. Rootwise does not
  check the current filesystem merely because a row is selected or navigated.

## Scope and claims

The product contract is **DESIGNED** and its documentation completeness is **STATICALLY CHECKED**.
The proposed interactions are not yet **UNIT TESTED**, **INTEGRATION TESTED**, **VISUALLY TESTED**,
**SCALE TESTED**, **EXFAT TESTED**, or approved for the real drive. The real 3.9+ TB source remains
out of scope.
