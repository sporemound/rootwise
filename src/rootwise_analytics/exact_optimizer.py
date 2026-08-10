"""Exact hierarchical enumeration with local Pareto pruning for small candidate trees."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .plan_models import Action, Candidate, PlanPolicy, ValidatedPlan
from .plan_validation import recompute_metrics, validate_plan


class ExactFrontierLimit(RuntimeError):
    """The measured frontier-state budget was exceeded."""


def _dominates(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(a <= b for a, b in zip(left, right, strict=True)) and any(
        a < b for a, b in zip(left, right, strict=True)
    )


def _descendants(root: str, children: Mapping[str, list[str]]) -> list[str]:
    result: list[str] = []
    pending = list(children[root])
    while pending:
        current = pending.pop()
        result.append(current)
        pending.extend(children[current])
    return result


def _prune(
    states: list[dict[str, Action]],
    candidates: Sequence[Candidate],
    max_frontier_states: int,
) -> list[dict[str, Action]]:
    unique: dict[tuple[tuple[str, int], ...], dict[str, Action]] = {}
    for state in states:
        unique[tuple(sorted((key, int(value)) for key, value in state.items()))] = state
    scored = [(state, recompute_metrics(candidates, state).values()) for state in unique.values()]
    front = [state for state, score in scored if not any(
        other is not state and _dominates(other_score, score)
        for other, other_score in scored
    )]
    front.sort(key=lambda state: tuple(sorted((key, int(value)) for key, value in state.items())))
    if len(front) > max_frontier_states:
        raise ExactFrontierLimit(
            f"exact frontier grew to {len(front)} states; limit is {max_frontier_states}"
        )
    return front


def exact_tree_frontier(
    candidates: Sequence[Candidate],
    policy: PlanPolicy,
    *,
    max_frontier_states: int = 5_000,
) -> list[ValidatedPlan]:
    if max_frontier_states < 1:
        raise ValueError("max_frontier_states must be positive")
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    children: dict[str, list[str]] = {candidate_id: [] for candidate_id in by_id}
    for candidate in candidates:
        if candidate.parent_id is not None:
            children[candidate.parent_id].append(candidate.candidate_id)
    for values in children.values():
        values.sort()

    def combine(
        left: list[dict[str, Action]], right: list[dict[str, Action]]
    ) -> list[dict[str, Action]]:
        combinations = len(left) * len(right)
        if combinations > max_frontier_states:
            raise ExactFrontierLimit(
                f"exact combination grew to {combinations} states; limit is {max_frontier_states}"
            )
        return [{**first, **second} for first in left for second in right]

    def solve(candidate_id: str) -> list[dict[str, Action]]:
        candidate = by_id[candidate_id]
        descendants = _descendants(candidate_id, children)

        def inactive_keep() -> dict[str, Action]:
            result: dict[str, Action] = {}

            def mark(current: str, protected_above: bool = False) -> None:
                current_protected = protected_above or by_id[current].protected
                result[current] = (
                    Action.PROTECTED if current_protected else Action.KEEP_UNPACKED
                )
                for child in children[current]:
                    mark(child, current_protected)

            mark(candidate_id)
            return result

        if candidate.protected:
            return [{candidate_id: Action.PROTECTED, **{
                child: Action.PROTECTED for child in descendants
            }}]
        states: list[dict[str, Action]] = [inactive_keep()]
        protected_below = any(by_id[child].protected for child in descendants)
        if (
            candidate.eligible
            and not protected_below
            and candidate.recursive_bytes <= policy.maximum_archive_bytes
            and candidate.recursive_bytes <= policy.usable_destination_bytes
        ):
            states.append({candidate_id: Action.ARCHIVE_AS_UNIT, **{
                child: Action.KEEP_UNPACKED for child in descendants
            }})
        if children[candidate_id]:
            combinations: list[dict[str, Action]] = [{candidate_id: Action.DEFER_TO_CHILDREN}]
            for child_id in children[candidate_id]:
                combinations = combine(combinations, solve(child_id))
                combinations = _prune(combinations, candidates, max_frontier_states)
            states.extend(combinations)
        return _prune(states, candidates, max_frontier_states)

    roots = sorted(candidate.candidate_id for candidate in candidates if candidate.parent_id is None)
    combined: list[dict[str, Action]] = [{}]
    for root in roots:
        combined = combine(combined, solve(root))
        combined = _prune(combined, candidates, max_frontier_states)
    return [validate_plan(candidates, policy, actions) for actions in combined]
