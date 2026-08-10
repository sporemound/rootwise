from __future__ import annotations

from rootwise_analytics.optimizer_moea import evolutionary_proposals, repair_actions
from rootwise_analytics.plan_models import Action, PlanPolicy
from rootwise_analytics.plan_validation import validate_plan

from .test_exact_optimizer import fixture_candidates


def test_hierarchical_repair_and_fixed_seed_proposals_validate() -> None:
    candidates = fixture_candidates()
    policy = PlanPolicy(250, 1_000, 0.1)
    order = [candidate.candidate_id for candidate in candidates]
    repaired = repair_actions(candidates, policy, order, [1, 1, 1])
    assert repaired == {
        "root": Action.KEEP_UNPACKED,
        "safe": Action.KEEP_UNPACKED,
        "protected": Action.PROTECTED,
    }
    validate_plan(candidates, policy, repaired)
    proposals = evolutionary_proposals(candidates, policy, generations=3)
    assert proposals
    sources = {proposal.source for proposal in proposals}
    assert sources >= {"NSGA3-seed-0", "NSGA3-seed-1", "NSGA3-seed-2"}
    assert any(source.startswith("RNSGA3-") for source in sources)
    assert all(validate_plan(candidates, policy, dict(item.plan.actions)) for item in proposals)
