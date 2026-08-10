from __future__ import annotations

import pytest

from rootwise_analytics.exact_optimizer import ExactFrontierLimit, exact_tree_frontier
from rootwise_analytics.plan_models import Action, Candidate, PlanMetrics, PlanPolicy
from rootwise_analytics.plan_validation import PlanValidationError, validate_plan


def fixture_candidates() -> list[Candidate]:
    return [
        Candidate("root", "root", None, 300, 30, False, False, 0.2, 0.3),
        Candidate("safe", "root/safe", "root", 200, 20, True, False, 0.05, 0.1),
        Candidate("protected", "root/protected", "root", 100, 10, False, True, 0.9, 0.2),
    ]


def test_validator_recomputes_and_rejects_hierarchical_violations() -> None:
    candidates = fixture_candidates()
    policy = PlanPolicy(250, 1_000, 0.1)
    valid = validate_plan(candidates, policy, {
        "root": Action.DEFER_TO_CHILDREN,
        "safe": Action.ARCHIVE_AS_UNIT,
        "protected": Action.PROTECTED,
    })
    assert valid.metrics.negative_recoverable_bytes == -200.0
    assert valid.metrics.remaining_loose_files == 10.0
    assert len(valid.archive_names) == 1
    with pytest.raises(PlanValidationError, match="eligibility"):
        validate_plan(candidates, policy, {
            "root": Action.ARCHIVE_AS_UNIT,
            "safe": Action.KEEP_UNPACKED,
            "protected": Action.KEEP_UNPACKED,
        })
    with pytest.raises(PlanValidationError, match="recomputation"):
        validate_plan(candidates, policy, dict(valid.actions), expected_metrics=PlanMetrics(
            -1.0, 10.0, 0.0, 200.0, 1.0, 0.0,
        ))


def test_exact_tree_frontier_is_valid_and_contains_keep_and_archive_choices() -> None:
    candidates = fixture_candidates()
    plans = exact_tree_frontier(candidates, PlanPolicy(250, 1_000, 0.1))
    archived = {tuple(item for item, action in plan.actions if action is Action.ARCHIVE_AS_UNIT)
                for plan in plans}
    assert () in archived
    assert ("safe",) in archived
    assert all(dict(plan.actions)["protected"] is Action.PROTECTED for plan in plans)
    with pytest.raises(ExactFrontierLimit):
        exact_tree_frontier(candidates, PlanPolicy(250, 1_000, 0.1), max_frontier_states=1)
