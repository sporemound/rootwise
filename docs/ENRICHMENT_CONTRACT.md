# 0.7 Permissioned Content-Enrichment Contract

Stage 0.7 is the first ParetoDrive component permitted to read source-file contents. It is a
separate `paretodrive_enrich` package and CLI, and it does not relax the metadata-only boundary of
the scanner, viewer, structural analytics, ranking, or optimizer.

## Required acknowledgement and selection

The command refuses to run without `--allow-content-read`. It accepts only a bounded, explicit
selection manifest whose canonical JSON fields are exactly:

```json
{
  "schema_version": "paretodrive-enrichment-selection-1",
  "scan_session_id": "the-complete-inventory-session-id",
  "inventory_digest": "64-lowercase-hex-characters",
  "evidence_level": "D3",
  "paths": ["Audio/render.wav", "Audio/render-copy.wav"]
}
```

Paths must be unique, normalized, relative, and bytewise sorted. The selected session must still
be `COMPLETE`; the source root, source-volume identity, and recomputed logical inventory digest
must match. Only selected entries recorded as observed regular files are opened.

## Evidence levels

- D2 reads bounded first, middle, and last samples and produces `BLAKE3-SAMPLED-V1`. Equal D2
  values form `CANDIDATE` groups only and do not prove full-file equality.
- D3 reads every byte and produces BLAKE3 with one worker thread. Equal D3 values and sizes form
  `CONFIRMED` duplicate-evidence groups.
- D4 reads every byte and produces SHA-256. Equal D4 values and sizes form `CONFIRMED`
  duplicate-evidence groups.

Even `CONFIRMED` means only that the selected byte streams matched under the recorded run. It is
not deletion eligibility, archive approval, proof of semantic interchangeability, or permission
for any filesystem action.

## Read and output boundaries

Reads are chunked and rate-limited. Each path component is checked against symbolic links and
reparse points, files are opened read-only with no-follow support where available, and identity,
size, and modification time are checked before and after reading. Metadata drift fails the run.

The inventory is opened SQLite read-only/query-only. Evidence is written to a new database beside
the inventory and must resolve to a different OS volume from the source. There is no resume mode:
an interrupted or bounded-stop run remains `STOPPED`, and a new run requires a new evidence path.

Reading may update access-time metadata depending on operating-system, filesystem, and mount
policy. The component never writes through its source file handles, but operators must not infer
that all source metadata remains byte-for-byte unchanged after a content read.

Stage 0.7 contains no delete, rename, move, copy, archive, network, shell, or subprocess facility.
It remains prohibited on the real multi-terabyte source until a separately documented operator
decision accepts the content-read and scale risks.
