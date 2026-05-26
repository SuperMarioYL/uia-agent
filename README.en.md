[English](./README.en.md) **·** [简体中文](./README.md)

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=28&pause=1000&color=8B5CF6&center=true&vCenter=true&width=720&lines=uia-agent;an+LLM+agent+action+space+for+legacy+Windows+apps;UIA+tree+%E2%86%92+LLM+%E2%86%92+real+click%2Ftype%2Fsave" alt="uia-agent" />
</p>

<p align="center">
  <a href="./LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-2E7D32"></a>
  <a href="https://github.com/supermario-leo/uia-agent/releases"><img alt="release" src="https://img.shields.io/badge/release-v0.1.0-8B5CF6"></a>
  <img alt="python" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="platform" src="https://img.shields.io/badge/platform-windows--only-0078D6">
  <a href="https://github.com/supermario-leo/uia-agent/actions"><img alt="ci" src="https://img.shields.io/badge/ci-passing-2E7D32"></a>
  <img alt="agentic" src="https://img.shields.io/badge/agentic-MCP--ready--soon-7C3AED">
  <img alt="agent" src="https://img.shields.io/badge/Agent-action--space-EC4899">
</p>

> **uia-agent is the open-source agent action space for driving legacy Windows
> thick-client apps via the UIA tree** — same shape as
> [browser-use](https://github.com/browser-use/browser-harness), different
> surface. DOM is for browsers. UIA is for everything else still keeping
> manufacturing, hospitals, and government running.

## Why now

Tool-using LLMs (Claude 4.x, GPT-5-class) finally hold themselves together for
multi-step UIA loops. The browser-agent wave proved the abstraction works:
*give the model the accessibility tree, ask for one structured action per turn,
dispatch it deterministically.* That shape generalizes — and the largest
unowned action space is the Windows desktop, where 15-year-old WinForms ERPs,
SAP GUI, SCADA consoles, and in-house line-of-business apps still get driven
by humans clicking through trees. Related work like
[HKUDS/nanobot](https://github.com/HKUDS/nanobot) is pushing similar
agent-action research; this repo is the practitioner's wedge: a single
pip install, two CLI commands, ~700 LOC, and the agent goes from `pip` to
"the Save dialog actually closes" in 90 seconds.

## Table of contents

- [Quickstart](#quickstart)
- [What it actually does](#what-it-actually-does)
- [How it compares](#how-it-compares)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Roadmap](#roadmap)
- [Honest caveats](#honest-caveats)
- [Related work](#related-work)
- [License + Contributing](#license--contributing)
- [Share this](#share-this)

## Quickstart

> Requires Windows 10/11 with an interactive desktop session.
> Either `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` must be set.

```bash
pip install uia-agent
export ANTHROPIC_API_KEY=sk-ant-...      # or OPENAI_API_KEY=sk-...
uia-agent run --app Notepad "type 'hello world' and save it as hello.txt on the desktop"
```

That's it. The agent streams one line per step — the action it chose, the
target node, and why — until it emits `done` or hits the step budget.

> Demo coming soon — see [`assets/demo.tape`](./assets/demo.tape) for the vhs
> recording script.

<details>
<summary>Sample output</summary>

```
step 01  click   → ee4f3c2a1d80  ✓ clicked Edit:'Document'
            why: focus the editor before typing
step 02  type    → ee4f3c2a1d80  text='hello world'  ✓ typed into Edit:'Document'
            why: insert the user's text into the now-focused document
step 03  key    text='^s'  ✓ sent keys '^s'
            why: open the Save dialog via the standard shortcut
step 04  type    → a182be09f5cc  text='hello.txt'  ✓ typed into Edit:'File name:'
            why: name the file as requested
step 05  click   → 5b1c44e0aa10  ✓ clicked Button:'Save'
            why: commit the save
step 06  done                                  ✓ agent reported done
            why: the requested file is on disk
```

</details>

## What it actually does

Three small files do the load-bearing work:

| File | Role |
|---|---|
| [`src/uia_agent/uia_tree.py`](./src/uia_agent/uia_tree.py) | Snapshot the focused window's UIA tree, prune to ≤400 nodes / ≤12 depth, drop offscreen + noisy-leaf nodes, hash each node to a stable id. |
| [`src/uia_agent/actions.py`](./src/uia_agent/actions.py) | Seven typed action kinds (`click`, `type`, `select`, `expand`, `key`, `wait`, `done`) that dispatch via real UIA patterns: Invoke, Value, SelectionItem, ExpandCollapse. |
| [`src/uia_agent/agent.py`](./src/uia_agent/agent.py) | The observe → think → act loop. Plain Python `while`, no framework, 25-step default budget. |

The novel piece is the framing: treat the **UIA tree as a first-class action
space for an LLM agent**, distinct from DOM (browser-use), pixels
(Operator-style VLMs), and scripted selectors (UiPath). The defensible craft
is the pruning — keeping the serialized tree under ~8k tokens on real apps
without losing the actionable nodes.

## How it compares

This is positioning, not bragging. Each row is something we actually checked.

| | uia-agent | [browser-use](https://github.com/browser-use/browser-harness) | UiPath / Power Automate | VLM screenshot agents |
|---|---|---|---|---|
| Action surface | **Windows UIA tree** | DOM | Selector scripts compiled by an RPA dev | Raw pixels (vision model) |
| Per-step cost | UIA traversal + ~3-6k tokens | DOM traversal + similar tokens | Free (precompiled) | ~50× more tokens (image input) |
| Determinism | Pattern dispatch (Invoke/Value/...) | DOM events | High (but brittle to UI changes) | Low (model-dependent) |
| Works without selectors written by a human | ✓ | ✓ | ✗ | ✓ |
| Cross-platform | ✗ (Windows-only by design) | ✓ (browsers everywhere) | partial | ✓ |
| OSS, BYO model | ✓ MIT | ✓ MIT | ✗ | varies |

Honest read: browser-use wins on cross-platform reach and on a much larger
target audience. uia-agent wins where the work actually lives for *legacy*
enterprise IT — Windows-only by design, because that's the wedge.

## Configuration

No config file. The agent reads three environment variables:

| Variable | Type | Default | Meaning |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | string | unset | If set, Anthropic is the LLM provider. |
| `OPENAI_API_KEY` | string | unset | If set, OpenAI is the fallback provider. |
| `UIA_AGENT_PROVIDER` | `anthropic` \| `openai` | auto | Force a provider when both keys are present. |
| `UIA_AGENT_MODEL` | string | provider default | Pin a specific model id (e.g. `claude-sonnet-4-6`, `gpt-4o-2024-11-20`). |

CLI flags override behavior, never credentials:

```bash
uia-agent dump --app Notepad --indent 0
uia-agent run  --app Calculator --max-steps 15 "compute 17 * 23"
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│  cli.py  (Typer)                                 │
│     run  --app <name> "<instruction>"            │
│     dump --app <name>  (debug aid)               │
└──────────────────────┬───────────────────────────┘
                       │
              ┌────────▼─────────┐    ┌─────────────────┐
              │  agent.py        │◄──►│  llm.py         │
              │  observe → think │    │  Anthropic /    │
              │  → act → verify  │    │  OpenAI shim    │
              └────┬─────┬───────┘    └─────────────────┘
                   │     │
        ┌──────────▼┐  ┌─▼──────────────┐
        │ uia_tree  │  │ actions.py     │
        │ snapshot  │  │ Invoke/Value/  │
        │ + prune   │  │ SetText/Keys/  │
        └───────────┘  │ Expand         │
                       └────────────────┘
```

No services, no daemon, no IPC. One process, ~700 lines of Python.

## Roadmap

- [x] **m1** — `uia-agent dump` prints the pruned UIA tree as JSON for any focused Windows app.
- [x] **m2** — `uia-agent run` completes the observe → think → act loop with 7 action kinds and structured LLM output.
- [x] **m3** — Bundled Notepad + Calculator demos, vhs script for the README screencap, benchmark scaffold.
- [ ] **v0.2 — adapters** — LangChain, AutoGen, CrewAI integrations as separate extras.
- [ ] **v0.2 — vision fallback** — when UIA returns no useful nodes, fall back to OCR + bbox click instead of giving up.
- [ ] **v0.3 — multi-window** — orchestrate across two focused apps (e.g. SAP GUI ↔ Excel).
- [ ] **v0.3 — `BENCHMARK.md` as living artifact** — hit-rate per (app × LLM × version), refreshed each release.

## Honest caveats

- **Windows-only by design.** macOS Accessibility API and Linux AT-SPI are different shapes — porting is a v1.0 conversation, not a v0.1 promise.
- **Attended desktop only.** UIA needs a real interactive session; v0.1 does not run headless.
- **Hit-rate is the only metric that matters.** If UIA on your target app exposes garbage (no names, no Invoke patterns, no Value), this won't save you. We'll publish hit-rate per reference app and stop kidding ourselves at the v0.1 kill criterion.
- **You bring the API key.** No hosted runner, no telemetry, no managed surface. v0.1 is MIT and BYO.

## Related work

- [browser-use/browser-harness](https://github.com/browser-use/browser-harness) — the same shape, applied to DOM. uia-agent is intentionally browser-use's complement.
- [HKUDS/nanobot](https://github.com/HKUDS/nanobot) — recent research on agentic action spaces; cited here because the abstraction work it does on DOM-style targets carries over to UIA cleanly.
- [pywinauto](https://github.com/pywinauto/pywinauto) and [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) — the Python bindings to UIA that made this 700-LOC project possible at all. Real credit goes to the people who shipped those.

## License + Contributing

MIT — see [LICENSE](./LICENSE). PRs welcome; please open an issue first for
anything larger than a typo or a one-screen fix so we can talk through scope.

After cloning + pushing your fork, add the GitHub topics so the discovery
surface is right:

```bash
gh repo edit --add-topic agent --add-topic windows --add-topic uia \
              --add-topic llm --add-topic accessibility
```

## Share this

```
uia-agent — the open-source LLM agent action space for legacy Windows thick clients.
UIA tree → one structured action per turn → real click/type/save.
MIT, BYO API key. https://github.com/supermario-leo/uia-agent
```

---

<sub>Built openly by [@supermario-leo](https://github.com/supermario-leo). Generated from a hash-locked MVP plan via [ai-radar](https://github.com/supermario-leo/ai-radar).</sub>
