# Stage 0.17 Guided Acceptance Workflow

Stage 0.17 adds guided commands around the Stage 0.16 evidence evaluator. It does not collect,
invent, or authenticate evidence. In particular, initialization creates an empty gate list so the
first evaluation is necessarily `INCOMPLETE`.

## Discover required evidence

```powershell
rootwise-acceptance guide
```

The command prints canonicalizable JSON containing every required gate and its exact measurement
field names. It does not contain suggested passing values or hardware budgets.

## Initialize an evidence manifest

All identity and time fields are explicit to avoid silently disclosing the machine or account and
to keep initialization deterministic:

```powershell
rootwise-acceptance init `
    --output "E:\acceptance\evidence-empty.json" `
    --subject-revision "0123456789abcdef0123456789abcdef01234567" `
    --producer "manual-review" `
    --created-at "2026-08-09T00:00:00Z" `
    --host-id "review-host" `
    --os "Windows 10" `
    --python "3.14.3"
```

The output must be a new file in an existing directory. Rootwise never overwrites a manifest.
Evidence gates must be added only after their external artifacts exist and their SHA-256 digests
have been recorded.

## Evaluate and inspect

```powershell
rootwise-acceptance evaluate `
    --manifest "E:\acceptance\evidence.json" `
    --report "E:\acceptance\report.json"

rootwise-acceptance inspect --report "E:\acceptance\report.json"
```

Inspection requires canonical JSON, recomputes the report output digest, validates every gate and
reason, requires exactly the complete sorted gate set, and recomputes the aggregate status. It can
inspect valid Stage 0.16 reports as well as Stage 0.17 reports. It does not open the external
evidence referenced by each digest.

Both `evaluate` and `inspect` exit `0` for `PASS`, `2` for a valid `FAIL` or `INCOMPLETE`, and `1`
for rejected or tampered input. The Stage 0.16 invocation without an `evaluate` subcommand remains
supported during the alpha compatibility period.

These commands add no scanner, source-content, GUI-launch, volume-management, network, archive,
move, rename, deletion, optimizer, approval, or execution capability.
