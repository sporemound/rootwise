# Rootwise-Android Porting Notes & Schema Mapping

Status: Pre-implementation architecture and schema review for `feat/android-fdroid`.
Upstream baseline: `0.23.0-alpha` (`fe6247b`).

This document summarizes the ported SQLite schemas, canonical export formats, adapter interfaces, and safety-invariant preservation strategy for bringing Rootwise to Android (targeting a **rooted Android / GrapheneOS device** as a first-class POSIX target alongside non-root SAF and MediaStore adapters, packaged for F-Droid distribution).

---

## 1. Core Architectural Mapping

| Upstream Component | Upstream Python Module | Android Kotlin Package / Class | Boundary Preserved |
|---|---|---|---|
| **Core Models** | `src/rootwise/models.py` | `org.rootwise.android.core.model` (`SessionState`, `VolumeInfo`, `ScanConfig`, `Observation`) | Immutable data classes; identical validation bounds (`batchSize` 1..10,000, positive `maxFilesPerSecond`, etc.). |
| **Volume Identity** | `src/rootwise/volume.py` | `org.rootwise.android.core.volume.VolumeResolver` | Resolves `posix-device:<st_dev>` + `/proc/mounts` on POSIX/Rooted paths; explicit namespace identities for SAF/MediaStore. |
| **Write Guard** | `src/rootwise/write_guard.py` | `org.rootwise.android.core.guard.WriteGuard` | Centralizes all destination writes inside app-private storage (`context.getDatabasePath().parentFile`), authorizes `-journal` and `-scanlock`, rejects symlinks, and enforces volume/subtree separation. |
| **Inventory Database** | `src/rootwise/database.py` | `org.rootwise.android.core.db.InventoryDatabase` | Verbatim SQLite schema (`PRAGMA application_id = 1346654806`, `journal_mode = DELETE`, `synchronous = FULL`), exclusive `-scanlock` file lock, persistent `scan_frontier`. |
| **Metadata Scanner** | `src/rootwise/scanner.py` | `org.rootwise.android.core.scanner.MetadataScanner` | Single-worker, bounded-batch, rate-limited, resumable traversal over a pluggable `ScanSourceAdapter`. Never opens source file contents. |
| **Canonical Export** | `src/rootwise/canonicalize.py` | `org.rootwise.android.core.export.CanonicalExporter` | Streaming SHA-256 deterministic NDJSON export (`schema: 2`), verifying `application_id`, `integrity_check`, `foreign_key_check`, exhausted frontier, and row counts inside one transaction. |
| **Viewer Reader** | `src/rootwise/viewer/inventory.py` | `org.rootwise.android.viewer.InventoryReader` | Opens `inventory.db` in read-only mode (`OPEN_READONLY` + `PRAGMA query_only = ON`), validates `application_id = 1346654806`, exposes bounded NFC-normalized `LIKE ... ESCAPE '\'` search (max 500 rows) and local sorting. |
| **Decision Store** | `src/rootwise/viewer/decisions.py` | `org.rootwise.android.viewer.DecisionStore` | Verbatim `decisions.db` schema (`PRAGMA application_id = 1346654807`), revision-checked `current_decisions` + append-only `decision_events` in sibling external directory. |
| **Planning Proposal** | `src/rootwise_analytics/plan_models.py`, `src/rootwise_approval/receipt.py` | `org.rootwise.android.planning.ProposalExporter` | Generates non-executable planning proposal JSON with `execution_authorized: false`, `archive_creation_authorized: false`, `original_removal_authorized: false`, bound by SHA-256 digests of the completed inventory session and decision revisions. |

---

## 2. Verbatim SQLite Schema Mapping

### 2.1 Inventory Schema (`inventory.db`)

Ported verbatim from `src/rootwise/database.py` and `docs/architecture/database-schema.md`:

- **SQLite Application ID:** `1346654806` (`0x50445356`)
- **Pragmas enforced on open:**
  - `PRAGMA foreign_keys = ON;`
  - `PRAGMA journal_mode = DELETE;`
  - `PRAGMA synchronous = FULL;`
  - `PRAGMA temp_store = MEMORY;`
  - `PRAGMA application_id = 1346654806;`

```sql
CREATE TABLE IF NOT EXISTS volumes (
  volume_id INTEGER PRIMARY KEY,
  identity TEXT NOT NULL UNIQUE,
  mount_path TEXT NOT NULL,
  filesystem_type TEXT,
  device TEXT
);
CREATE TABLE IF NOT EXISTS scan_sessions (
  scan_session_id TEXT PRIMARY KEY,
  volume_id INTEGER NOT NULL REFERENCES volumes(volume_id),
  state TEXT NOT NULL CHECK(state IN ('RUNNING','COMPLETE','STOPPED','FAILED')),
  source_root TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  configuration_json TEXT NOT NULL,
  observed_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS directories (
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  comparison_path TEXT NOT NULL,
  parent_path TEXT,
  name TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  logical_bytes INTEGER NOT NULL,
  created_ns INTEGER,
  modified_ns INTEGER,
  accessed_ns INTEGER,
  attributes INTEGER NOT NULL,
  depth INTEGER NOT NULL,
  display_path TEXT NOT NULL,
  observation_status TEXT NOT NULL,
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE TABLE IF NOT EXISTS files (
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  comparison_path TEXT NOT NULL,
  parent_path TEXT,
  name TEXT NOT NULL,
  extension TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  logical_bytes INTEGER NOT NULL,
  created_ns INTEGER,
  modified_ns INTEGER,
  accessed_ns INTEGER,
  attributes INTEGER NOT NULL,
  depth INTEGER NOT NULL,
  display_path TEXT NOT NULL,
  observation_status TEXT NOT NULL,
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE TABLE IF NOT EXISTS scan_errors (
  error_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  operation TEXT NOT NULL,
  error_type TEXT NOT NULL,
  error_code INTEGER,
  message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_frontier (
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('PENDING','SCANNING','DONE')),
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE INDEX IF NOT EXISTS frontier_next ON scan_frontier(scan_session_id, state, relative_path);
CREATE TABLE IF NOT EXISTS scan_events (
  event_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  event_type TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canonical_exports (
  export_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  output_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  completed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_writes (
  write_id INTEGER PRIMARY KEY,
  scan_session_id TEXT,
  path TEXT NOT NULL,
  purpose TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
```

### 2.2 User Decision Schema (`decisions.db`)

Ported verbatim from `src/rootwise/viewer/decisions.py` and `docs/architecture/decision-schema.md`:

- **SQLite Application ID:** `1346654807` (`0x50445357`)
- **Supported Decisions:** `KEEP`, `PROTECT`, `ARCHIVE_ELIGIBLE`, `REBUILDABLE`, `NOT_REBUILDABLE`, `PROJECT_BOUNDARY`, `NOT_A_PROJECT`, `EXCLUDE_FROM_ANALYSIS`, `UNKNOWN`.
- **Rules:**
  - Separate file in the same external artifact directory as `inventory.db`.
  - Creating a `(scan_session_id, relative_path)` subject sets `revision = 1` (requiring `expectedRevision == null` or `0`).
  - Updating requires exact `expectedRevision == current.revision`, increments `revision`, updates `current_decisions`, and appends to `decision_events` inside a `BEGIN IMMEDIATE` transaction.
  - No delete API exists.

```sql
PRAGMA application_id=1346654807;
CREATE TABLE IF NOT EXISTS current_decisions (
  scan_session_id TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  decision TEXT NOT NULL,
  note TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE TABLE IF NOT EXISTS decision_events (
  event_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  previous_decision TEXT,
  decision TEXT NOT NULL,
  note TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  recorded_at TEXT NOT NULL,
  UNIQUE(scan_session_id, relative_path, revision)
);
CREATE INDEX IF NOT EXISTS decision_events_subject
ON decision_events(scan_session_id, relative_path, revision);
```

---

## 3. Scan Adapter Architecture (Rooted POSIX + SAF + MediaStore)

To serve both a **rooted Android phone** (full POSIX filesystem visibility with strict `O_NOFOLLOW` / `lstat` / `st_dev` guarantees) and non-root scoped-storage surfaces behind a single dependency-free scanner core:

1. **`ScanSourceAdapter` (Core Interface in pure Kotlin):**
   - `resolveVolume(): VolumeInfo`
   - `openDirectory(relativeDir: String): DirectoryListing` (non-following, volume-verified)
   - `observeEntry(parentRelativeDir: String, entry: RawDirectoryEntry): Pair<Observation, Boolean>` (fresh non-following metadata check at the observation boundary)
   - `capabilities(): AdapterCapabilities` (explicitly reports whether `O_NOFOLLOW`, `st_dev` boundary verification, and uncached `lstat` are enforced by the underlying surface, and lists known blind spots)

2. **`PosixRootScanAdapter` (Primary for Rooted Phone & Local JVM/POSIX Tests):**
   - Operates directly on POSIX mount paths (`/data`, `/data/media/0`, `/mnt/media_rw/<UUID>`, `/storage/<UUID>`) either in-process (when running with root/test permissions via `java.nio.file.LinkOption.NOFOLLOW_LINKS` / Android `Os.lstat` / `Os.open`) or via a minimal root helper protocol (`su --mount-master -c ...` streaming JSONL metadata records obtained with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` and `lstat`).
   - Preserves symlink/mount-escape detection (`st_dev` comparison against resolved `posix-device:<st_dev>` and `/proc/mounts`) and Stage 0.21 fresh `lstat` revalidation.

3. **`SafScanAdapter` (Storage Access Framework `DocumentsContract`):**
   - Queries `DocumentsContract.buildChildDocumentsUriUsingTree` projecting metadata columns only (`COLUMN_DOCUMENT_ID`, `COLUMN_DISPLAY_NAME`, `COLUMN_MIME_TYPE`, `COLUMN_SIZE`, `COLUMN_LAST_MODIFIED`, `COLUMN_FLAGS`). Never calls `openInputStream` or `openFileDescriptor`.
   - Reports blind spots (`Android/data`, `Android/obb`, root partitions) and capability limitations (`nofollow_enforced = false`, `fresh_stat_enforced = false`) in session configuration and UI.

4. **`MediaStoreScanAdapter` (Scoped MediaStore Query Adapter):**
   - Queries `MediaStore.Files.getContentUri(volumeName)` metadata projections (`RELATIVE_PATH`, `DISPLAY_NAME`, `SIZE`, `DATE_MODIFIED`, `DATE_ADDED`) without opening file streams.
   - Explicitly documents that non-media files outside app-contributed rows are omitted by Android scoped storage unless read permissions or root POSIX mode are used.

---

## 4. Safety Invariants Audit & Blocking Questions for Human Review

Per `docs/safety/safety-invariants.md`, all 24 invariants were audited against the Android target:

| Invariant | Status on Rooted POSIX Adapter | Status on SAF / MediaStore Adapter |
|---|---|---|
| 1. Source files never opened for writing | **Preserved** | **Preserved** |
| 2. Source contents not read in audit mode | **Preserved** (`lstat` / `readdir` only) | **Preserved** (cursor metadata columns only) |
| 3. DB & outputs outside source volume | **Requires Policy Decision on `userdata` (see Q1)** | **Preserved logically** (app-private internal DB vs SAF tree) |
| 4. No delete/move/rename/copy/link/archive APIs | **Preserved** (enforced by static test) | **Preserved** |
| 5. Symlinks/reparse points not followed | **Preserved** (`NOFOLLOW_LINKS` / `O_NOFOLLOW` / `lstat`) | **Limitation (see Q2)**: SAF `DocumentsProvider` does not expose `O_NOFOLLOW` |
| 6–18. Single worker, SQLite frontier, batching, rate limit, cancel, resume, `COMPLETE` rules, structured errors, separate decisions, no network/shell in core | **Preserved 1:1** | **Preserved 1:1** |
| 19. Source & destination volume identities resolve before scanning | **Requires Policy Decision on `userdata` (see Q1)** | **Limitation (see Q2)**: SAF exposes authority+tree URI, not kernel `st_dev` |
| 20–23. Fail closed, `-scanlock` exclusive lease, stale `RUNNING` recovery, resource-bound `STOPPED` | **Preserved 1:1** (`FileChannel.tryLock()` on `-scanlock`) | **Preserved 1:1** |
| 24. Fresh non-following `lstat` before observation | **Preserved 1:1** | **Limitation (see Q2)**: re-querying single document metadata via SAF cursor |

### Resolved Android Invariant Decisions (Approved by Repo Owner)

1. **Q1 — Invariant #3 & #19 on Android Internal Storage (`userdata` shared `st_dev`) — APPROVED:**
   - When scanning an external SD card or USB OTG volume (`/mnt/media_rw/<UUID>`) into app-private storage (`/data/user/0/org.rootwise.android/databases`), strict `source.identity != destination.identity` (`st_dev` inequality) is enforced unchanged.
   - When scanning internal storage (`/data` or `/data/media/0`) while storing `inventory.db` in `/data/user/0/org.rootwise.android/databases` (which share the Android `userdata` block device `st_dev`), an explicit `allowSameVolumeDisjointSubtree` guard is required and recorded in `scan_sessions.configuration_json` (`"volume_separation_mode": "SAME_VOLUME_DISJOINT_SUBTREE"`):
     1. Rejects any scan where `source_root` is inside or equal to `allowed_root` (the app-private artifact directory).
     2. When `allowed_root` is a descendant of `source_root` (e.g., scanning `/data`), **hard-excludes** the app's own private directories (`/data/data/org.rootwise.android`, `/data/user/0/org.rootwise.android`, `/sdcard/Android/data/org.rootwise.android`, and the active `allowed_root`) before directory descent and records a `SELF_ARTIFACT_ROOT_EXCLUDED` event in `scan_events` so the scanner never observes or re-scans its own `inventory.db`.
2. **Q2 — Invariants #5, #19, #24 on Non-Root SAF / MediaStore Adapters — APPROVED:**
   - `PosixRootScanAdapter` is the primary audit-grade scanner on rooted devices, strictly enforcing `O_NOFOLLOW` / `NOFOLLOW_LINKS`, `posix-device:<st_dev>` + `/proc/mounts` volume identity, and Stage 0.21 fresh `lstat` revalidation at the observation boundary (`nofollow_enforced = true`, `kernel_st_dev_enforced = true`, `fresh_stat_enforced = true`).
   - On SAF and MediaStore adapters, `volumes.identity` is recorded as `android-saf:<authority>:<treeId>` or `android-mediastore:<volume>`, per-document metadata re-query is performed at the observation boundary, and `"adapter_capabilities": {"nofollow_enforced": false, "kernel_st_dev_enforced": false, "fresh_stat_enforced": false}` is persisted in `scan_sessions.configuration_json` and surfaced in the UI.
3. **Q3 — F-Droid License & Application ID — APPROVED:**
   - License: `MIT` (matching upstream `LICENSE` and `pyproject.toml`).
   - Application ID / Namespace: `org.rootwise.android`.
