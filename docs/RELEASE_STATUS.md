# Release Status

Version: `0.2.0-audit.2` (unreleased source milestone)

- Designed: metadata-only scanner boundary and staged release gates.
- Implemented: volume identity, guarded outputs, handle-bound traversal, SQLite sessions,
  cancellation/resume, structured errors, and deterministic canonical export.
- Tested locally: 29 synthetic/unit/static tests pass on Windows 11 with CPython 3.12; generated
  evidence records exact versions and output.
- Windows acceptance: synthetic local-filesystem tests only; not an independent build.
- exFAT VHDX: not tested.
- OS-enforced read-only: not tested.
- Independent replication: not tested.
- Real 3.9+ TB source: prohibited until prior gates pass.

Expected Windows CPython 3.12 corpus digest:
`7a40e32dfa0ed16afab2ef42944db845daad3bf1477e07cd1061bbb8dbfec6b8`.
