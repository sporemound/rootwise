# Release Status

Version: `0.2.0-audit.2` (unreleased source milestone)

- Designed: metadata-only scanner boundary and staged release gates.
- Implemented: volume identity, guarded outputs, handle-bound traversal, SQLite sessions,
  cancellation/resume, structured errors, and deterministic canonical export.
- Tested locally: 29 synthetic/unit/static tests pass; generated evidence records exact versions
  and output.
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
