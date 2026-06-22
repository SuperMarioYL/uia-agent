"""Drive the Windows 11 Calculator app via UIA — a tighter test surface.

Calculator exposes Invoke patterns on every digit + operator button, so the
agent should reach `done` in 6-10 steps. Useful when iterating on the prompt
or the action vocabulary because the tree is small and deterministic.

Prerequisite:
    - You are on Windows with a desktop session.
    - The Calculator app is open and focused (Standard mode).
    - Either ANTHROPIC_API_KEY or OPENAI_API_KEY is set.

Run:
    python examples/calculator_demo.py
"""

from __future__ import annotations

from uia_agent import run

INSTRUCTION = (
    "Compute 17 * 23 in the Calculator. When the display shows 391, emit `done`."
)


def main() -> None:
    for event in run(app="Calculator", instruction=INSTRUCTION, max_steps=15):
        marker = "✗" if event.error else "✓"
        detail = event.error or (event.result.detail if event.result else "")
        print(f"{marker} step {event.index:02d} {event.action.kind:<6} {detail}")
        if event.action.reason:
            print(f"     why: {event.action.reason}")


if __name__ == "__main__":
    main()
