# 0.10 Enrichment-Evidence Fusion Contract

Stage 0.10 imports completed 0.7 enrichment evidence into a new immutable analytical artifact. It
does not reopen the raw inventory or any source path and does not modify the existing analysis or
evidence databases.

## Input validation

The analysis and enrichment databases are opened SQLite read-only/query-only and held in read
transactions. They and the new fusion destination must be distinct siblings in the external
inventory directory.

The selected analysis run must be `COMPLETE` with exactly the roles, directory-aggregates,
projects, and relationships stages. Stage 0.10 recomputes every analytical table digest and the
analysis output digest.

The enrichment run must be `COMPLETE`, have equal selected/completed counts, contain no recorded
errors, and have complete selection, read, and duplicates stages. Stage 0.10 recomputes file
evidence, group, stage, and run output digests; validates algorithms and 64-character lowercase
digests; and reconciles each group with its file evidence and member count.

Both inputs must record the same inventory path, complete scan session, and logical inventory
digest. Stopped, failed, partial, mismatched, or tampered inputs are rejected before output is
created.

## Evidence semantics

- D2 uses `BLAKE3-SAMPLED-V1` and remains `CANDIDATE` evidence.
- D3 uses full BLAKE3 and remains `CONFIRMED` byte-equality evidence.
- D4 uses full SHA-256 and remains `CONFIRMED` byte-equality evidence.

No level establishes semantic interchangeability, archive eligibility, or deletion safety.

For every analytical directory, the fusion database records observed and selected counts/bytes,
D2 candidate member counts/bytes, and D3/D4 confirmed member counts/bytes. The two ratios have
explicit denominators:

```text
evidence_coverage = selected_file_count / observed_file_count
confirmed_member_ratio_of_selected = confirmed_member_count / selected_file_count
```

A high confirmed-member ratio over a small selection is not high directory coverage. Downstream
analytics must preserve both values and must not silently extrapolate evidence to unselected files.

Stage 0.10 contains no source-content read, archive, copy, move, rename, delete, network, shell,
subprocess, approval, or execution capability.
