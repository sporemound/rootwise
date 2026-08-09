# Changelog

## 0.3.0-alpha - unreleased

- Added a separate `paretodrive_view` package with query-only inventory access.
- Added bounded path search and exact item lookup for completed scan sessions.
- Added a distinct user-decision database with optimistic revisions and append-only history.
- Added headless search/decision commands and a minimal optional PySide6 table viewer.
- Added a hash-locked Windows PySide6 6.10.2 dependency set.
- Added viewer trust-boundary, decision-schema, backend, CLI, static-safety, and offscreen GUI tests.

## 0.2.0-audit.2 - unreleased

- Added explicit Windows/exFAT acceptance contracts and plan-only VHDX tooling.
- Added a bounded Windows Home VHDX backend that does not accept physical-disk identifiers.
- Passed the local disposable exFAT, OS-read-only, cancellation/resume, unchanged-source, and
  detach/retain acceptance gates for source commit `018435d`.
- Added destination-capacity, process-memory, active-window, and cooldown controls.
- Added durable scan events and crash/recovery validation.
- Hardened resume with database integrity and frontier consistency checks.

## 0.2.0-audit.1 - unreleased

- Restarted from an empty, source-first repository.
- Added the audit scanner trust model, safety invariants, and replication/test protocols.
- Added a standard-library metadata scanner with external SQLite state and canonical export.
