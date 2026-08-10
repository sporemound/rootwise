"""Fixed-seed NSGA-III exploration and R-NSGA-III preference refinement."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
import warnings

import numpy as np
import numpy.typing as npt
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.algorithms.moo.rnsga3 import RNSGA3
from pymoo.core.problem import ElementwiseProblem
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.repair.rounding import RoundingRepair
from pymoo.optimize import minimize
from pymoo.util.ref_dirs import get_reference_directions

from .plan_models import Action, Candidate, PlanPolicy, ValidatedPlan
from .plan_validation import validate_plan


@dataclass(frozen=True)
class EvolutionaryProposal:
    source: str
    plan: ValidatedPlan


def _hierarchy(candidates: Sequence[Candidate]) -> tuple[dict[str, Candidate], dict[str, list[str]]]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    children: dict[str, list[str]] = {candidate_id: [] for candidate_id in by_id}
    for candidate in candidates:
        if candidate.parent_id is not None:
            children[candidate.parent_id].append(candidate.candidate_id)
    for values in children.values():
        values.sort()
    return by_id, children


def repair_actions(
    candidates: Sequence[Candidate],
    policy: PlanPolicy,
    order: Sequence[str],
    values: npt.ArrayLike,
) -> dict[str, Action]:
    by_id, children = _hierarchy(candidates)
    raw = np.rint(np.asarray(values, dtype=float)).clip(0, 3).astype(int)
    desired = {candidate_id: Action(int(raw[index])) for index, candidate_id in enumerate(order)}
    protected_below: dict[str, bool] = {}

    def has_protected(candidate_id: str) -> bool:
        child_values = [
            by_id[child].protected or has_protected(child) for child in children[candidate_id]
        ]
        value = any(child_values)
        protected_below[candidate_id] = value
        return value

    for root in (candidate.candidate_id for candidate in candidates if candidate.parent_id is None):
        has_protected(root)
    result: dict[str, Action] = {}

    def visit(candidate_id: str, forced: Action | None = None) -> None:
        candidate = by_id[candidate_id]
        if forced is Action.PROTECTED or candidate.protected:
            action = Action.PROTECTED
        elif forced is not None:
            action = forced
        else:
            action = desired[candidate_id]
            if action is Action.PROTECTED:
                action = Action.KEEP_UNPACKED
            if action is Action.DEFER_TO_CHILDREN and not children[candidate_id]:
                action = Action.KEEP_UNPACKED
            if action is Action.ARCHIVE_AS_UNIT and (
                not candidate.eligible
                or protected_below[candidate_id]
                or candidate.recursive_bytes > policy.maximum_archive_bytes
                or candidate.recursive_bytes > policy.usable_destination_bytes
            ):
                action = Action.KEEP_UNPACKED
        result[candidate_id] = action
        child_force = {
            Action.ARCHIVE_AS_UNIT: Action.KEEP_UNPACKED,
            Action.KEEP_UNPACKED: Action.KEEP_UNPACKED,
            Action.PROTECTED: Action.PROTECTED,
            Action.DEFER_TO_CHILDREN: None,
        }[action]
        for child in children[candidate_id]:
            visit(child, child_force)

    for root in sorted(candidate.candidate_id for candidate in candidates if candidate.parent_id is None):
        visit(root)
    return result


class _PlanProblem(ElementwiseProblem):  # type: ignore[misc]
    def __init__(self, candidates: Sequence[Candidate], policy: PlanPolicy, order: Sequence[str]) -> None:
        super().__init__(n_var=len(order), n_obj=6, n_ieq_constr=0, xl=0, xu=3, vtype=int)
        self.candidates = candidates
        self.policy = policy
        self.order = order

    def _evaluate(
        self, x: npt.NDArray[np.float64], out: dict[str, Any], *args: object, **kwargs: object
    ) -> None:
        del args, kwargs
        actions = repair_actions(self.candidates, self.policy, self.order, x)
        out["F"] = np.asarray(
            validate_plan(self.candidates, self.policy, actions).metrics.values(), dtype=float
        )


def _operators() -> dict[str, object]:
    repair = RoundingRepair()
    return {
        "crossover": SBX(prob=1.0, eta=15, vtype=float, repair=repair),
        "mutation": PM(eta=20, vtype=float, repair=repair),
    }


def _initial_population(
    candidates: Sequence[Candidate], order: Sequence[str], population: int, seed: int
) -> npt.NDArray[np.int64]:
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, 4, size=(population, len(order)), dtype=np.int64)
    samples[0, :] = int(Action.KEEP_UNPACKED)
    samples[1, :] = np.asarray([
        int(Action.ARCHIVE_AS_UNIT if candidate.eligible else Action.KEEP_UNPACKED)
        for candidate in sorted(candidates, key=lambda item: order.index(item.candidate_id))
    ])
    return samples


def _plans_from_result(
    source: str,
    candidates: Sequence[Candidate],
    policy: PlanPolicy,
    order: Sequence[str],
    values: object,
) -> list[EvolutionaryProposal]:
    matrix = np.atleast_2d(np.asarray(values, dtype=float))
    unique: dict[str, EvolutionaryProposal] = {}
    for row in matrix:
        plan = validate_plan(candidates, policy, repair_actions(candidates, policy, order, row))
        unique[plan.plan_id] = EvolutionaryProposal(source, plan)
    return list(unique.values())


def evolutionary_proposals(
    candidates: Sequence[Candidate],
    policy: PlanPolicy,
    *,
    generations: int = 20,
    seeds: Sequence[int] = (0, 1, 2),
) -> list[EvolutionaryProposal]:
    if generations < 1 or not seeds:
        raise ValueError("evolutionary search requires positive generations and at least one seed")
    order = tuple(candidate.candidate_id for candidate in candidates)
    problem = _PlanProblem(candidates, policy, order)
    ref_dirs = get_reference_directions("das-dennis", 6, n_partitions=2)
    population = len(ref_dirs)
    proposals: list[EvolutionaryProposal] = []
    for seed in seeds:
        algorithm = NSGA3(
            ref_dirs=ref_dirs,
            pop_size=population,
            sampling=_initial_population(candidates, order, population, seed),
            eliminate_duplicates=True,
            **_operators(),
        )
        result = minimize(problem, algorithm, ("n_gen", generations), seed=seed, verbose=False)
        proposals.extend(_plans_from_result(
            f"NSGA3-seed-{seed}", candidates, policy, order, result.X
        ))
    keep = validate_plan(candidates, policy, repair_actions(
        candidates, policy, order, np.zeros(len(order), dtype=int)
    ))
    preference = np.asarray([keep.metrics.values()], dtype=float)
    refinement = RNSGA3(
        ref_points=preference,
        pop_per_ref_point=6,
        mu=0.1,
        sampling=_initial_population(candidates, order, 12, 0),
        eliminate_duplicates=True,
        **_operators(),
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        refined = minimize(problem, refinement, ("n_gen", generations), seed=0, verbose=False)
    degenerate = any(
        "invalid value encountered in divide" in str(item.message) for item in caught
    )
    if degenerate or refined.X is None:
        proposals.append(EvolutionaryProposal("RNSGA3-degenerate-fallback", keep))
    else:
        proposals.extend(_plans_from_result(
            "RNSGA3-safest", candidates, policy, order, refined.X
        ))
    return proposals
