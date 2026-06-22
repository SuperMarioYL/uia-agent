"""Living-benchmark machinery for the (app × LLM × version) hit-rate scorecard.

The headline metric is **hit-rate**: of the UI actions the agent attempted that
targeted a node, what fraction actually dispatched against a live, actionable
control. A leaky UIA tree (unnamed / pattern-less nodes) drags this down — so
the scorecard is the honest signal for whether the primitive works on a given
app, and the v0.2 kill-criterion reads straight off it.

This module is the machinery that turns a list of agent step results into a
:class:`HitRateRow` and renders the Markdown table that lands in ``BENCHMARK.md``.
It is pure-Python and dependency-free so it can score recorded traces in CI as
well as live runs on a Windows box.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Action kinds that target a UIA node (and therefore count toward hit-rate).
# `key`, `wait`, and `done` don't address a node, so they're excluded.
_TARGETING_KINDS = frozenset({"click", "type", "select", "expand"})


@dataclass(frozen=True)
class StepOutcome:
    """The minimal record the scorer needs from one agent step."""

    kind: str
    ok: bool


@dataclass(frozen=True)
class HitRateRow:
    """One row of the scorecard: a single (app × LLM × version) measurement."""

    app: str
    llm: str
    version: str
    attempted: int
    hits: int
    run_date: str

    @property
    def hit_rate(self) -> float:
        """Fraction of node-targeting actions that dispatched successfully."""
        return self.hits / self.attempted if self.attempted else 0.0


def score_run(
    *,
    app: str,
    llm: str,
    version: str,
    run_date: str,
    steps: Iterable[StepOutcome],
) -> HitRateRow:
    """Compute a :class:`HitRateRow` from one agent run's step outcomes.

    Only node-targeting actions (`click`/`type`/`select`/`expand`) count toward
    the denominator; a "hit" is such an action that dispatched successfully.
    """
    attempted = 0
    hits = 0
    for step in steps:
        if step.kind not in _TARGETING_KINDS:
            continue
        attempted += 1
        if step.ok:
            hits += 1
    return HitRateRow(
        app=app,
        llm=llm,
        version=version,
        attempted=attempted,
        hits=hits,
        run_date=run_date,
    )


def render_scorecard(rows: Sequence[HitRateRow]) -> str:
    """Render the hit-rate rows as a GitHub-flavoured Markdown table."""
    header = (
        "| App | LLM | Version | Actions attempted | Hits | Hit-rate | Run date |\n"
        "|---|---|---|---:|---:|---:|---|"
    )
    body = "\n".join(
        f"| {r.app} | {r.llm} | {r.version} | {r.attempted} | {r.hits} "
        f"| {r.hit_rate * 100:.0f}% | {r.run_date} |"
        for r in rows
    )
    return f"{header}\n{body}" if body else header


def average_hit_rate(rows: Sequence[HitRateRow]) -> float:
    """Macro-average hit-rate across rows (the v0.2 kill-criterion metric)."""
    if not rows:
        return 0.0
    return sum(r.hit_rate for r in rows) / len(rows)
