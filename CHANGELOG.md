# Changelog

All notable changes to **uia-agent** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-07-17

Exposes the uia-agent action space over MCP (the committed `v0.3 — MCP server`
roadmap item) and hardens two genuine bugs found in the v0.2.0-shipped source.
The UIA-first happy path and the dependency-free core are unchanged — the MCP
surface is an opt-in extra, and the two fixes touch only the vision fallback
and an error message.

### Added

- **m7 — MCP server.** `uia_agent.adapters.mcp_server` exposes the `uia_dump` +
  `uia_run` tools over MCP stdio, so any MCP client (Claude Desktop, etc.) can
  drive a Windows app the same way the CLI does. Installable via
  `pip install uia-agent[mcp]`; started with `uia-agent mcp`. The module mirrors
  the v0.2.0 LangChain adapter pattern — the `mcp` SDK is imported lazily, the
  core stays dependency-free, and without the extra `build_server()` raises a
  clear typed `MCPUnavailable` error. The tool specs reuse the same
  framework-neutral `UiaToolSpec` as the LangChain / AutoGen / CrewAI bindings,
  so the run/dump schema is identical across every framework surface.

### Fixed

- **Vision OCR spin.** The `--vision` fallback no longer re-clicks the same
  OCR coordinate every step until the step budget is exhausted. When a click
  exposes nothing new in the UIA tree, the next dead step used to re-snapshot,
  re-OCR, and `max(regions, key=confidence)` returned the same region again —
  burning the whole budget on one point with no LLM consultation. The loop now
  records each clicked coordinate, drops already-clicked regions (±5px) from
  the candidate set before picking, and falls through to the normal LLM step
  when nothing fresh remains. The UIA-first path and the first-step OCR click
  are unchanged.
- **LLM provider install hint.** The `anthropic` / `openai` `ImportError`
  message no longer points at `pip install uia-agent[dev]` (whose `[dev]` extra
  only carries pytest/ruff/mypy and does not contain either SDK). It now names
  `pip install uia-agent` — the command that actually reinstalls these core
  dependencies — plus the bare-package fallback.

[0.3.0]: https://github.com/supermario-leo/uia-agent/releases/tag/v0.3.0

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
