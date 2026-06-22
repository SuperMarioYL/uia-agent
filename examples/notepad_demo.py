"""Smallest end-to-end demo: drive Windows Notepad with one sentence.

Prerequisite:
    - You are on Windows with a desktop session.
    - Notepad is already open and focused.
    - Either ANTHROPIC_API_KEY or OPENAI_API_KEY is set.

Run:
    python examples/notepad_demo.py
"""

from __future__ import annotations

from uia_agent import run

INSTRUCTION = (
    "Type the following haiku into the editor, exactly three lines:\n"
    "    Old Windows still hums\n"
    "    accessibility trees breathe\n"
    "    new agents wake up\n"
    "Then save the file as poem.txt on the Desktop. When the file is saved, emit `done`."
)


def main() -> None:
    for event in run(app="Notepad", instruction=INSTRUCTION, max_steps=20):
        marker = "✗" if event.error else "✓"
        detail = event.error or (event.result.detail if event.result else "")
        print(f"{marker} step {event.index:02d} {event.action.kind:<6} {detail}")
        if event.action.reason:
            print(f"     why: {event.action.reason}")


if __name__ == "__main__":
    main()
