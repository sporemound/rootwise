# Concurrent metadata mutation boundary

Stage 0.21 closes a Windows enumeration-cache gap in the metadata-only scanner. A directory entry
can disappear after `os.scandir` enumerates it but before Rootwise observes it. Windows may satisfy
`DirEntry.stat()` from cached enumeration data, which previously allowed a deleted entry to be
recorded as observed.

Rootwise now performs a fresh `os.stat(entry.path, follow_symlinks=False)` at the observation
boundary. If the entry disappeared, the existing per-entry `OSError` path records a structured
`stat` error and does not commit an observation or queue a directory. Stable files and directories
continue through the same metadata-only classification path, and symlinks are not followed.

## Tested properties

- Deterministic deletion of a file after enumeration produces `FileNotFoundError` evidence and no
  file observation.
- Deterministic deletion of a directory after enumeration produces the same fail-closed result and
  does not queue that directory.
- A stable sibling remains observed in both cases.
- The complete disposable metadata-edge campaign also exercises a real 371-character Windows path,
  a real temporary `LIST_DIRECTORY` ACL denial with verified restoration, and injected `EINVAL` at
  the fresh metadata boundary.

## Remaining boundary

Inventory observations remain point-in-time metadata facts. A path may change after the fresh stat
and before or after the database transaction, so later action-oriented components must independently
revalidate their own source observations. Stage 0.21 does not open file contents, create stable
source handles for future execution, or authorize archive, move, rename, or deletion operations.
