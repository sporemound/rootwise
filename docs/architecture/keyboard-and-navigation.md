# Stage 0.24 Keyboard and Navigation Contract

Status: **DESIGNED**, not implemented except where explicitly marked current. Navigation is over
inventory-relative observations in one completed session. It never changes into live filesystem
browsing and never assumes an observed path still exists.

## Current keyboard behavior

The following behavior is **IMPLEMENTED** and **UNIT TESTED** where covered by GUI tests:

| Command | Shortcut | Capability |
|---|---|---|
| Focus search | Ctrl+F | `METADATA_ONLY` |
| Refresh bounded query | F5 | `METADATA_ONLY` |
| Previous/next result page | Alt+Left / Alt+Right | `METADATA_ONLY` |
| Record selected decision | Ctrl+Return | `DECISIONS_ONLY` |
| Close window | Ctrl+W | presentation only |

Alt+Left and Alt+Right currently mean result-page movement, not navigation history. Stage 0.26
must resolve that conflict by giving those shortcuts to Back and Forward and assigning explicit
page commands (recommended: Page Up/Page Down or menu-only paging).

## Proposed inventory navigation

- **Home / inventory root:** normalized empty relative path for the selected completed session.
- **Open directory:** Enter or double-click on an observed directory changes inventory scope.
- **Breadcrumb:** shows “Inventory” plus each normalized ancestor; clicking an ancestor navigates
  to it. Ctrl+L focuses an accessible textual breadcrumb/location control.
- **Back:** returns to the prior `(directory, query, filter, sort, page)` state.
- **Forward:** reapplies a state removed by Back until a new navigation branch is created.
- **Up:** moves to the normalized observed parent and cannot escape the inventory root.
- **Return to previous query:** navigation history retains the complete query state rather than
  keeping a hidden global search active.

Root containment is syntactic and inventory-based. Absolute paths, NUL, unresolved `.` or `..`,
and separator-based escapes are rejected. Unicode paths remain NFC-normalized for comparison while
display strings retain the recorded spelling. Session changes clear navigation history and try to
restore only a compatible root state.

No source path is opened by Open directory, Breadcrumb, Back, Forward, Up, Home, search scoping,
selection, or refresh. “Open” means open an inventory location only.

## Proposed keyboard map

| Command | Proposed input | Capability |
|---|---|---|
| Back / Forward | Alt+Left / Alt+Right; mouse navigation buttons | `METADATA_ONLY` |
| Up | Alt+Up and Backspace when no editor owns the key | `METADATA_ONLY` |
| Home/root | Alt+Home | `METADATA_ONLY` |
| Focus Breadcrumb | Ctrl+L | `METADATA_ONLY` |
| Focus search | Ctrl+F | `METADATA_ONLY` |
| Activate observed directory | Enter | `METADATA_ONLY` |
| Move selection | Arrow keys, Home/End, Page Up/Page Down | `METADATA_ONLY` |
| Select all visible rows | Ctrl+A, only if multi-select is later approved | `METADATA_ONLY` |
| Copy observed path text | Ctrl+C | `METADATA_ONLY` |
| Record decision | Ctrl+Return | `DECISIONS_ONLY` |
| Escape transient UI | Escape | presentation only |

Keyboard commands must respect text-editor focus. Backspace never navigates while editing search or
notes, and Ctrl+C copies selected text when an editor owns focus.

## Context menu contract

The initial Context menu may show Inspect metadata, Copy observed relative path, Bookmark, Decision
history, and Record decision. Commands are keyboard reachable and use the same actions as menus.
Unavailable commands remain visible with an explanation where that improves discoverability.

- Inspect, copy text, and Bookmark are `METADATA_ONLY`.
- Record and history are `DECISIONS_ONLY` (history itself reads the decisions database).
- Open live location, launch, edit, copy files, move, rename, delete, archive, and shell are
  `PROHIBITED_EXECUTION` and must not be shown as disabled promises.

## Saved searches and bookmarks

Saved searches capture a validated query/filter/sort/directory specification. Bookmarks identify a
completed session plus normalized inventory-relative directory. Both use the future preferences
store and grant no source-drive authority. Missing sessions or paths produce a clear Error state;
they do not fall through to the current filesystem.

History must be bounded (recommended maximum 100 states per window). Empty state, Loading state,
and Error state transitions must preserve keyboard focus predictably and announce their text to
assistive technology.
