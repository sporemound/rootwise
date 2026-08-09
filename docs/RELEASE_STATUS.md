# Release Status

Version: `0.5.0-alpha` (unreleased source milestone)

- Designed: metadata-only scanner boundary and staged release gates.
- Implemented: volume identity, guarded outputs, handle-bound traversal, SQLite sessions,
  cancellation/resume, structured errors, and deterministic canonical export.
- Viewer implemented: query-only inventory reader, bounded search, separate revisioned decisions,
  headless CLI, and optional PySide6 table interface.
- Structural analytics implemented: snapshot-only deterministic roles, recursive directory totals,
  project-marker boundaries, structural relationships, and per-stage provenance.
- Pareto review implemented: DuckDB/Polars feature materialization, independent confidence
  intervals, cohort-local robust fronts, and a bounded human-review queue in a third database.
- Tested locally: 44 synthetic/unit/static tests pass on CPython 3.14.3, including construction of
  the real PySide6 6.10.2 window using the offscreen Qt platform. Ruff and strict mypy pass across
  26 source files under the hash-locked CPython 3.12 development environment.
- GUI interaction and visual layout: constructed and event-processed offscreen; not yet manually
  reviewed in a visible desktop session.
- Search scale: functionally tested with bounded pages; not benchmarked at millions of rows and
  not an Everything-performance claim.
- Analytics scale: deterministic fixture behavior is tested; multi-million-row memory, latency,
  and temporary-space behavior are not benchmarked or accepted for the real source.
- Ranking scale: deterministic fixture behavior is tested; cohort calibration, ranking stability
  under alternative uncertainty assumptions, and multi-million-row resource use are not accepted
  for the real source.
- Installed analytics integration: passed against the retained 30-observation synthetic exFAT
  inventory after VHDX detachment, producing 15 roles, 16 aggregate nodes, one project, six
  relationships, and four `COMPLETE` stages while leaving the inventory byte-identical. Output
  digest: `7f600018bf172c3d7f2da2b39ea0af97749868fa8da6fa3232a2b8e444f935d1`.
- Installed ranking integration: passed against that retained 0.4 analysis using DuckDB 1.5.5,
  Polars 1.43.2, and PyArrow 25.0.0, producing 15 candidates, 60 objective intervals, six cohorts,
  and four `COMPLETE` stages. The analysis remained SHA-256
  `c1481ef4af56c1c0baa1d5c2e75193c0e944650db708c9712cf04ee80e6591fe`; ranking output digest:
  `cd1c173b8ecb6131775dcc2426f3cc14e0291b3217957bfa3343c744b02ffb7b`.
- Windows acceptance: passed locally on Windows 10 Home for source commit `018435d`; this was not
  an independent build or replication.
- exFAT VHDX: passed using a new 512 MiB disposable VHDX resolved only from its exact workspace
  image path. The retained VHDX was verified detached after the test.
- OS-enforced read-only: passed on the disposable exFAT volume. Cancellation produced `STOPPED`,
  resume reached `COMPLETE` in the same session, and pre/post content manifests were identical.
- Independent replication: not tested.
- Real 3.9+ TB source: not tested and remains prohibited pending an explicit minimum-evidence
  review and operator decision.

Expected Windows CPython 3.12 corpus digest:
`7a40e32dfa0ed16afab2ef42944db845daad3bf1477e07cd1061bbb8dbfec6b8`.

The platform-specific exFAT acceptance export contained 35 records with SHA-256
`c4cf55664a0c1e995b113daf18f5f6cac879c08473c0770602913bd582a87d49`. Its pre/post source
manifest SHA-256 was
`897f58e93e0f8645728da03c39fe61df5f05c8b4b9f375a731a25cf0b8ad0cb4`.
