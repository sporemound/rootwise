"""Independent deterministic validation and objective recomputation for proposed plans."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence

from .plan_models import Action, Candidate, PlanMetrics, PlanPolicy, ValidatedPlan


class PlanValidationError(ValueError):
    """A proposal violates a hard constraint or does not reconcile."""


def _tree(candidates: Sequence[Candidate]) -> tuple[dict[str, Candidate], dict[str, list[str]]]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise PlanValidationError("candidate IDs must be unique")
    if len({candidate.relative_path for candidate in candidates}) != len(candidates):
        raise PlanValidationError("candidate paths must be unique")
    children: dict[str, list[str]] = {candidate_id: [] for candidate_id in by_id}
    for candidate in candidates:
        if candidate.parent_id is not None:
            if candidate.parent_id not in by_id:
                raise PlanValidationError("candidate parent is missing")
            children[candidate.parent_id].append(candidate.candidate_id)
    for values in children.values():
        values.sort()
    return by_id, children


def _archive_name(candidate: Candidate) -> str:
    leaf = candidate.relative_path.rsplit("/", 1)[-1] or "root"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", leaf).strip("-.") or "group"
    suffix = hashlib.sha256(candidate.relative_path.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:60]}-{suffix}.zip"


def recompute_metrics(
    candidates: Sequence[Candidate], actions: Mapping[str, Action]
) -> PlanMetrics:
    by_id, _ = _tree(candidates)
    roots = [candidate for candidate in candidates if candidate.parent_id is None]
    total_bytes = sum(candidate.recursive_bytes for candidate in roots)
    total_files = sum(candidate.file_count for candidate in roots)
    archived = [by_id[candidate_id] for candidate_id, action in actions.items()
                if action is Action.ARCHIVE_AS_UNIT]
    recoverable = sum(candidate.recursive_bytes for candidate in archived)
    archived_files = sum(candidate.file_count for candidate in archived)
    risk = sum(candidate.recursive_bytes * candidate.preservation_risk for candidate in archived)
    incoherence = sum(candidate.recursive_bytes * candidate.incoherence for candidate in archived)
    denominator = max(total_bytes, 1)
    return PlanMetrics(
        -float(recoverable),
        float(max(0, total_files - archived_files)),
        risk / denominator,
        float(max((candidate.recursive_bytes for candidate in archived), default=0)),
        float(len(archived)),
        incoherence / denominator,
    )


def validate_plan(
    candidates: Sequence[Candidate],
    policy: PlanPolicy,
    actions: Mapping[str, Action | int],
    *,
    expected_metrics: PlanMetrics | None = None,
) -> ValidatedPlan:
    if not candidates:
        raise PlanValidationError("at least one candidate is required")
    if policy.maximum_archive_bytes <= 0 or policy.destination_available_bytes < 0:
        raise PlanValidationError("plan capacity limits are invalid")
    if not 0.0 <= policy.destination_safety_margin < 1.0:
        raise PlanValidationError("destination safety margin must be in [0,1)")
    by_id, children = _tree(candidates)
    if set(actions) != set(by_id):
        raise PlanValidationError("plan actions must cover every candidate exactly once")
    normalized = {candidate_id: Action(action) for candidate_id, action in actions.items()}
    state: dict[str, int] = {}

    def visit(candidate_id: str, forced: Action | None = None) -> None:
        if state.get(candidate_id) == 1:
            raise PlanValidationError("candidate hierarchy contains a cycle")
        if state.get(candidate_id) == 2:
            return
        state[candidate_id] = 1
        candidate = by_id[candidate_id]
        action = normalized[candidate_id]
        if forced is not None:
            expected = Action.PROTECTED if (
                forced is Action.PROTECTED or candidate.protected
            ) else forced
            if action is not expected:
                raise PlanValidationError("inactive descendants have inconsistent actions")
        if forced is None:
            if candidate.protected and action is not Action.PROTECTED:
                raise PlanValidationError("protected candidate is not protected by the plan")
            if not candidate.protected and action is Action.PROTECTED:
                raise PlanValidationError("plan marks an unprotected candidate as protected")
            if action is Action.ARCHIVE_AS_UNIT:
                if not candidate.eligible or candidate.protected:
                    raise PlanValidationError("archive action lacks explicit eligibility")
                if candidate.recursive_bytes > policy.maximum_archive_bytes:
                    raise PlanValidationError("archive exceeds the maximum archive size")
                if candidate.recursive_bytes > policy.usable_destination_bytes:
                    raise PlanValidationError("archive exceeds safe destination capacity")
            if action is Action.DEFER_TO_CHILDREN and not children[candidate_id]:
                raise PlanValidationError("leaf candidate cannot defer to children")
        child_force = Action.PROTECTED if action is Action.PROTECTED else forced
        if forced is None:
            child_force = {
                Action.ARCHIVE_AS_UNIT: Action.KEEP_UNPACKED,
                Action.KEEP_UNPACKED: Action.KEEP_UNPACKED,
                Action.PROTECTED: Action.PROTECTED,
                Action.DEFER_TO_CHILDREN: None,
            }[action]
        for child in children[candidate_id]:
            visit(child, child_force)
        state[candidate_id] = 2

    roots = sorted(candidate.candidate_id for candidate in candidates if candidate.parent_id is None)
    for root in roots:
        visit(root)
    if len(state) != len(by_id):
        raise PlanValidationError("candidate hierarchy is disconnected or cyclic")
    metrics = recompute_metrics(candidates, normalized)
    if expected_metrics is not None and any(
        not math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9)
        for left, right in zip(metrics.values(), expected_metrics.values(), strict=True)
    ):
        raise PlanValidationError("reported objective values do not match recomputation")
    names = tuple(sorted(
        (candidate_id, _archive_name(by_id[candidate_id]))
        for candidate_id, action in normalized.items() if action is Action.ARCHIVE_AS_UNIT
    ))
    if len({name for _, name in names}) != len(names):
        raise PlanValidationError("archive names are not unique")
    canonical_actions = tuple(sorted(normalized.items()))
    plan_id = hashlib.sha256(json.dumps(
        [(candidate_id, int(action)) for candidate_id, action in canonical_actions],
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return ValidatedPlan(plan_id, canonical_actions, metrics, names)
