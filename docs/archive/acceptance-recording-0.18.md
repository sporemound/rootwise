# Stage 0.18 Immutable Gate Recording

Stage 0.18 replaces ad hoc acceptance-manifest editing with an immutable `record` workflow. It
hashes one external evidence artifact, validates one canonical gate-specific measurements object,
and writes a new manifest revision. It never overwrites the source manifest or replaces an already
recorded gate.

## Measurements file

Run `rootwise-acceptance guide` to obtain the exact field names for a gate. The measurements file
must be a canonical JSON object: UTF-8, sorted keys, compact separators, and one trailing newline.
Its keys must exactly equal the selected gate's required fields. Missing and unexpected fields are
rejected.

For a confirmed visible GUI review, the canonical measurements file is:

```json
{"no_critical_defects":true,"review_completed":true,"visible_session":true}
```

Boolean or numerical values are not presumed to pass. The Stage 0.16 evaluator recomputes the
gate's status, and Stage 0.18 records that computed `PASS` or `FAIL` in its command result.

## Command

```powershell
rootwise-acceptance record `
    --manifest "E:\acceptance\evidence-empty.json" `
    --evidence "E:\acceptance\visible-gui-review.json" `
    --measurements "E:\acceptance\visible-gui-measurements.json" `
    --output "E:\acceptance\evidence-with-gui.json" `
    --gate "visible_gui_review" `
    --notes "Confirmed visible review of the retained synthetic inventory."
```

The manifest, evidence, measurements, and output paths must be distinct. Evidence is hashed with
streaming SHA-256. The output must be a new file in an existing directory. Existing manifest gates
must already be canonical, sorted, unique, and valid; attempting to record the same gate again is
rejected rather than interpreted as replacement.

After recording, run `evaluate` and `inspect` on new paths. Recording a passing gate does not make
the overall report pass while other required gates remain absent.

Rootwise verifies the evidence bytes only while recording them. Later evaluation and inspection
bind and display the recorded digest but do not reopen the external evidence artifact. Evidence
authenticity, reviewer identity, and the operational suitability of declared resource budgets
remain external review responsibilities.

This command opens only the operator-selected manifest, evidence, and measurements files. It adds
no scanner, observed-source, GUI-launch, volume-management, network, archive, move, rename,
deletion, optimizer, approval, or execution capability.
