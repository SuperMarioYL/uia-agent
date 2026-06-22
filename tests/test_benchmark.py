"""Living-benchmark scorecard machinery (m6)."""

from __future__ import annotations

from uia_agent.benchmark import (
    StepOutcome,
    average_hit_rate,
    render_scorecard,
    score_run,
)


def test_hit_rate_counts_only_node_targeting_actions() -> None:
    steps = [
        StepOutcome(kind="click", ok=True),
        StepOutcome(kind="type", ok=True),
        StepOutcome(kind="key", ok=True),  # not node-targeting → excluded
        StepOutcome(kind="wait", ok=True),  # excluded
        StepOutcome(kind="done", ok=True),  # excluded
        StepOutcome(kind="select", ok=False),  # attempted miss
    ]
    row = score_run(
        app="Notepad",
        llm="claude-sonnet-4-6",
        version="0.2.0",
        run_date="2026-06-22",
        steps=steps,
    )
    assert row.attempted == 3  # click + type + select
    assert row.hits == 2
    assert abs(row.hit_rate - (2 / 3)) < 1e-9


def test_empty_run_has_zero_hit_rate_not_division_error() -> None:
    row = score_run(
        app="Empty", llm="x", version="0.2.0", run_date="2026-06-22", steps=[]
    )
    assert row.attempted == 0
    assert row.hit_rate == 0.0


def test_render_scorecard_has_header_and_one_row_per_input() -> None:
    rows = [
        score_run(
            app="Notepad",
            llm="claude-sonnet-4-6",
            version="0.2.0",
            run_date="2026-06-22",
            steps=[StepOutcome(kind="click", ok=True)],
        ),
        score_run(
            app="Calculator",
            llm="gpt-4o-2024-11-20",
            version="0.2.0",
            run_date="2026-06-22",
            steps=[StepOutcome(kind="click", ok=False)],
        ),
    ]
    table = render_scorecard(rows)
    assert "| App | LLM | Version |" in table
    assert "| Notepad | claude-sonnet-4-6 | 0.2.0 |" in table
    assert "100%" in table
    assert "0%" in table
    # One data row per input run.
    assert table.count("0.2.0") == 2
    data_rows = [ln for ln in table.splitlines() if ln.startswith("| ") and "---" not in ln]
    # header + 2 data rows
    assert len(data_rows) == 3


def test_average_hit_rate_is_macro_average() -> None:
    rows = [
        score_run(
            app="a",
            llm="m",
            version="0.2.0",
            run_date="d",
            steps=[StepOutcome(kind="click", ok=True)],
        ),
        score_run(
            app="b",
            llm="m",
            version="0.2.0",
            run_date="d",
            steps=[StepOutcome(kind="click", ok=False)],
        ),
    ]
    assert abs(average_hit_rate(rows) - 0.5) < 1e-9
    assert average_hit_rate([]) == 0.0
