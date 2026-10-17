# Rootwise for Android (`org.rootwise.android`)

Rootwise for Android is a native Kotlin port of [Rootwise](README.md) (`0.23.0-alpha`) — an **audit-first, metadata-only filesystem inventory and non-executing review tool** designed for both **rooted Android devices** and **non-rooted GrapheneOS / Scoped Storage devices**, distributable via **F-Droid**.

For the complete architecture mapping, verbatim SQLite schema compatibility table, and invariant verification matrix, see [`docs/PORTING-NOTES-ANDROID.md`](docs/PORTING-NOTES-ANDROID.md).

---

## 1. Core Safety Invariants

Every scan, browse, decision, and export operation in `org.rootwise.android` upholds the upstream Rootwise trust boundaries:

1. **Metadata-Only Scanning**: The scanner inspects `stat()`-level metadata only (`size_bytes`, `mtime_ns`, `ctime_ns`, `inode`, `device_id`, `mode`, `uid`, `gid`, `nlink`, `is_symlink`). It never reads file contents or computes content hashes during scanning.
2. **Bounded Inventory Outside the Scanned Tree**: All working databases (`inventory.db`, `decisions.db`) live inside the app's private internal database directory (`context.getDatabasePath(...)`) protected by `WriteGuard`. The scanner never creates or modifies files inside the scanned target.
3. **Verbatim Upstream SQLite Schemas**:
   - `inventory.db`: `PRAGMA application_id = 1346654806` (`0x5044494E` / `"PDIN"`), `PRAGMA user_version = 1`.
   - `decisions.db`: `PRAGMA application_id = 1346654807` (`0x50444443` / `"PDDC"`), `PRAGMA user_version = 1`.
   - Databases produced on Android can be inspected directly by the upstream Python CLI (`rootwise inspect`, `rootwise export`) and vice versa.
4. **Query-Only Review & Separate Decisions**: Browsing an inventory opens `inventory.db` in read-only mode (`SQLiteDatabase.OPEN_READONLY` / `PRAGMA query_only = ON`). Human review annotations (`KEEP`, `DELETE_CANDIDATE`, `ARCHIVE_CANDIDATE`, `NEEDS_REVIEW`) are written exclusively to `decisions.db`.
5. **No Executor**: The app contains zero file deletion, moving, or mutation logic. Its output is a non-executable planning proposal JSON (`"execution_Capability": "NONE"`) or canonical NDJSON snapshot (`rootwise-export/v1`).
6. **Zero Third-Party Dependencies in Core**: `org.rootwise.android.core.*` uses only the Kotlin standard library and platform SQLite/NIO primitives.

---

## 2. Permission Model & Network Isolation

- **Zero Install-Time Permissions**: `AndroidManifest.xml` declares **no** `<uses-permission>` grants.
- **No Network Capability**: `android.permission.INTERNET` is never requested and is explicitly stripped from merged manifests via `tools:node="remove"`. The app is 100% offline with zero telemetry or analytics.
- **No Broad Storage Permission**: `MANAGE_EXTERNAL_STORAGE` ("All files access") is never requested.
- **Explicit User-Initiated Grants Only**:
  - **SAF Document Tree Mode**: Uses `Intent.ACTION_OPEN_DOCUMENT_TREE` at runtime for the specific directory selected by the user. Works seamlessly with GrapheneOS **Storage Scopes** and degrades gracefully if access is narrowed or revoked.
  - **Rooted POSIX Mode**: Uses standard unprivileged `java.nio.file` (`LinkOption.NOFOLLOW_LINKS`) first; only when the user explicitly checks **"Use root (`su --mount-master`) fallback"** does the adapter invoke `su` to run read-only `toybox find -P` / `toybox stat` on protected paths.
  - **Outbound Export**: Writing outside app-private storage occurs **only** when the user explicitly clicks one of the three SAF `ACTION_CREATE_DOCUMENT` export buttons (`Export inventory.db`, `Export NDJSON`, or `Export Proposal JSON`).

---

## 3. Scan Adapters & Known Blind Spots

Honesty about coverage is part of the Rootwise audit model. Each adapter records its exact capability flags and blind spots both in the UI and inside `scan_sessions.configuration_json`:

### A. Rooted / POSIX Path Adapter (`PosixRootScanAdapter`)
- **Best for**: Rooted Android phones auditing external mounts (`/mnt/media_rw/<UUID>`, USB OTG, SD card) or internal partitions (`/data/media/0`, `/data/local/tmp`, `/data`).
- **Capabilities**:
  - `nofollow_enforced = true` (`LinkOption.NOFOLLOW_LINKS` / `lstat` / `find -P`).
  - `kernel_st_dev_enforced = true` (captures real kernel `st_dev` and `st_ino` via `android.system.Os.lstat` or `toybox stat`).
  - `fresh_stat_enforced = true`.
- **Internal `userdata` Self-Exclusion Guard**:
  - When scanning `/data` or `/data/media/0` (which share the `userdata` filesystem `st_dev` with `/data/user/0/org.rootwise.android/databases`), enabling **Same-volume disjoint-subtree guard** enforces:
    1. `source_root` must not be equal to or inside the artifact directory `allowed_root`.
    2. The scanner hard-excludes `/data/data/org.rootwise.android`, `/data/user/0/org.rootwise.android`, `/sdcard/Android/data/org.rootwise.android`, and `allowed_root` before descending into any directory, logging an explicit `SELF_ARTIFACT_ROOT_EXCLUDED` audit event in `scan_events`.
    3. Records `"volume_separation_mode": "SAME_VOLUME_DISJOINT_SUBTREE"` in `scan_sessions.configuration_json`.
- **Blind Spots**:
  - Without `su` enabled, SELinux and UNIX DAC permissions block `/data` and `/storage/emulated/0/Android/data` (recorded as `PERMISSION_DENIED` events in `scan_events`, resulting in final session status `PARTIAL`).

### B. SAF Document Tree Adapter (`SafScanAdapter`)
- **Best for**: Non-rooted GrapheneOS / Pixel devices scanning a user-chosen folder or USB OTG drive via Scoped Storage.
- **Capabilities**:
  - Synthetic volume identity: `android-saf:<authority>:<treeDocumentId>`.
  - `nofollow_enforced = false`, `kernel_st_dev_enforced = false`, `fresh_stat_enforced = false` (persisted in `scan_sessions.configuration_json`).
- **Known Blind Spots (Android 11+ / API 30–36)**:
  - The system DocumentsUI picker blocks selecting root `/storage/emulated/0`, `Download/`, `Android/data/`, and `Android/obb/` directly.
  - App-specific sandboxes under `Android/data/<pkg>` and `Android/obb/<pkg>` are invisible to `com.android.externalstorage.documents`.
  - `DocumentsContract` does not expose POSIX `st_ino`, `st_dev`, `uid`, `gid`, or symlink flags.

### C. MediaStore Adapter (`MediaStoreScanAdapter`)
- **Best for**: Auditing indexed media files across `external_primary` or secondary storage volumes.
- **Capabilities**:
  - Synthetic volume identity: `android-mediastore:<volumeName>`.
  - `nofollow_enforced = false`, `kernel_st_dev_enforced = false`, `fresh_stat_enforced = false`.
- **Known Blind Spots**:
  - Directories containing a `.nomedia` file, hidden dotfiles, `Android/data`, `Android/obb`, and non-indexed app files are omitted by Android's media indexer.
  - Reflects the MediaStore SQLite index at query time rather than live kernel `lstat()` calls.

---

## 4. Building, Testing, and F-Droid Reproducibility

### Prerequisites
- JDK 17+
- Android SDK with `platforms;android-36` and `build-tools;35.0.0`

### Run Unit Tests, Coverage Verification (>85%), and Dependency Audit
```bash
./gradlew testDebugUnitTest jacocoTestReport jacocoCoverageVerification dependencyGuard
```

### Build Reproducible Release APK
```bash
./gradlew assembleRelease
```

The build uses fixed dependency versions, disables PNG crunching and build-metadata block injection (`includeInApk = false`), checks in zero binary blobs (no `gradle-wrapper.jar` in git), and pulls exclusively Apache-2.0 / MIT dependencies from Maven Central and Google Maven.
