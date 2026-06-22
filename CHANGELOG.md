# Changelog

All notable changes to **uia-agent** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-06-22

Roadmap-execution release: three feature milestones land and two source bugs
are fixed. The UIA-first happy path and the dependency-free core are unchanged —
every new capability is an opt-in extra.

### Added

- **m4 — framework adapter layer.** `uia_agent.adapters` exposes the `dump` +
  `run` entry points as framework tools. A LangChain wrapper ships first
  (`from uia_agent.adapters.langchain_tool import UiaRunTool, UiaDumpTool`),
  installable via `pip install uia-agent[langchain]`; the AutoGen/CrewAI binding
  shares the same framework-neutral `UiaToolSpec` shape. Imports are lazy, so
  the core install never pulls LangChain.
- **m5 — OCR + bbox vision fallback.** `uia_agent.vision` adds a gated fallback
  (`uia-agent run --vision`, or `run(..., vision=True)`): when the pruned UIA
  tree yields zero actionable nodes for a step, the agent screenshots the
  window, runs OCR, and clicks the highest-confidence text region by coordinate
  instead of giving up. Needs `pip install uia-agent[vision]`; a UIA-rich step
  never enters the vision path.
- **m6 — living BENCHMARK.md scorecard.** A real hit-rate table keyed by
  `(app × LLM × version)`, backed by the dependency-free `uia_agent.benchmark`
  harness (`score_run` / `render_scorecard` / `average_hit_rate`). v0.2.0 panel
  averages 83% across the five reference apps.

### Fixed

- **OpenAI strict json_schema 400.** `ACTION_JSON_SCHEMA` now lists every
  property in `required` (`kind`, `target_id`, `text`, `reason`); OpenAI's
  strict structured-output mode rejected the previous two-field `required` with
  a 400 `invalid_schema`, which broke the entire OpenAI provider path.
- **SendKeys special-character mangling.** The `type` SendKeys fallback now
  escapes the `{ } ( ) + ^ % ~` metacharacters and translates newlines to
  `{Enter}` (`actions.escape_sendkeys`), so multi-line / punctuated payloads —
  including the headline haiku demo — round-trip byte-for-byte instead of being
  silently corrupted. The Value-pattern path is unaffected.

[0.2.0]: https://github.com/supermario-leo/uia-agent/releases/tag/v0.2.0

## [0.1.0] — 2026-05-27

Initial public release. Three milestones land together.

### m1 — dump UIA tree
- `uia-agent dump --app <name>` prints a pruned UIA snapshot as JSON.
- Pruning rules wired: invisible / off-screen / unnamed-leaf nodes dropped,
  depth ≤ 12, total nodes ≤ 400.
- Stable node id is `sha1(role, name, automation_id, depth_path)[:12]` so two
  snapshots of the same window agree on ids even after content changes.
- Cross-platform unit tests use a fake control tree; live Windows tests run
  under the `windows_only` pytest marker.

### m2 — execute actions
- `uia-agent run --app <name> "<instruction>"` runs the observe → think → act
  loop with a default 25-step budget.
- Action vocabulary: `click`, `type`, `select`, `expand`, `key`, `wait`, `done`.
- Each action dispatches through a real UIA pattern (Invoke / Value /
  SelectionItem / ExpandCollapse) when one exists, with a SendKeys fallback
  for `type` and a global-shortcut path for `key`.
- LLM step uses provider-native structured output:
  Anthropic tool-use *or* OpenAI JSON-schema. No regex parsing of free text.

### m3 — demo + benchmark scaffolding
- Bundled examples: `examples/notepad_demo.py`, `examples/calculator_demo.py`.
- `docs/demo.tape` script for the README screencap (vhs).
- `BENCHMARK.md` shape will land alongside the first benchmark run; see
  [README §Roadmap](./README.md#roadmap).

[0.1.0]: https://github.com/supermario-leo/uia-agent/releases/tag/v0.1.0
