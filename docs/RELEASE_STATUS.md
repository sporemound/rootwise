# Release Status

Version: `0.2.0-audit.1` (unreleased source milestone)

- Designed: metadata-only scanner boundary and staged release gates.
- Implemented: volume identity, guarded outputs, handle-bound traversal, SQLite sessions,
  cancellation/resume, structured errors, and deterministic canonical export.
- Tested locally: 20 synthetic/unit/static tests pass on Windows 11 with CPython 3.12; generated
  evidence records exact versions and output.
- Windows acceptance: synthetic local-filesystem tests only; not an independent build.
- exFAT VHDX: not tested.
- OS-enforced read-only: not tested.
- Independent replication: not tested.
- Real 3.9+ TB source: prohibited until prior gates pass.

Expected Windows CPython 3.12 corpus digest:
`57f2aa24aa89bb0c490edf77e12027e2b42160b70f43bdc06c30c177260a6d74`.

