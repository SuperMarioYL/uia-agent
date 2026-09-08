[简体中文](./README.md) · [Website](https://uia-agent.lei6393.com) · [GitHub](https://github.com/SuperMarioYL/uia-agent)

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/hero-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/hero-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/hero-dark.svg">
  <img src="./assets/presentation/hero-light.svg" width="960" alt="Hero diagram">
</picture>

# uia-agent

**Give desktop automation an inspectable action tree.**

uia-agent snapshots a Windows accessibility tree, prunes it into a compact action frame, and dispatches typed actions through supported UIA patterns.

## Why use it

Legacy desktop applications often expose accessible controls even when no application API is available. A tree of named controls gives a model a structured place to choose its next action.

- **Structured control context** — Names, values and supported patterns stay visible.
- **Bounded snapshots** — Depth and node budgets limit the traversed tree.
- **Typed action dispatch** — Actions target UIA patterns through one dispatcher.

## Architecture

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/architecture-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/architecture-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/architecture-dark.svg">
  <img src="./assets/presentation/architecture-light.svg" width="960" alt="Architecture diagram">
</picture>

uia_tree walks controls under depth and node budgets and assigns stable IDs. The model adapter returns one Action; actions dispatches it through control patterns. The agent repeats observation and action within its step budget. Optional adapters expose the same workflow to MCP or LangChain.

| Component | Responsibility |
| --- | --- |
| `UIA snapshot` | src/uia_agent/uia_tree.py |
| `Action frame` | Pruned control tree |
| `Model action` | src/uia_agent/llm.py |
| `UIA dispatch` | src/uia_agent/actions.py |

## Install and quickstart

Build with the version declared in the repository manifest. Run the example from the repository root.

```bash
git clone https://github.com/SuperMarioYL/uia-agent.git
cd uia-agent
uv venv .venv
uv pip install --python .venv/bin/python pydantic
uv pip install --python .venv/bin/python --no-deps -e .
```

The portable example provides three fake controls to the production snapshot walker and checks which two remain.

```bash
.venv/bin/python examples/presentation-demo.py
```

## Recorded demo

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/process-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/process-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/process-dark.svg">
  <img src="./assets/presentation/process-light.svg" width="960" alt="Process diagram">
</picture>

The three-node fake tree becomes a two-node frame containing the named Save button.

```text
input nodes: 3
retained nodes: 2
retained: Button Save ['Invoke']
stable snapshot IDs: True
```

The complete command and output are recorded in [docs/demo-results.json](./docs/demo-results.json). Inputs and reproduction code are included in the repository.

![Existing terminal recording](./assets/demo.gif)

The existing recording is retained for context; the text example above documents the reproducible scenario.

## Usage

The CLI exposes the following operations. Commands after the example use your own paths or identifiers.

```bash
# On Windows, in a fully installed environment:
uia-agent dump --app Notepad --indent 0
uia-agent run --app Calculator --max-steps 15 "Compute 17 * 23"
```

## Configuration

For the portable tree example, only pydantic and the source package are needed; the setup below intentionally uses --no-deps. For native Windows automation, install the full package with python -m pip install -e . in a Windows environment. ANTHROPIC_API_KEY or OPENAI_API_KEY provides credentials; UIA_AGENT_PROVIDER and UIA_AGENT_MODEL select the provider/model. Windows venv Python is .venv\Scripts\python.exe.

## Integrations and responsibilities

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/integrations-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/integrations-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/integrations-dark.svg">
  <img src="./assets/presentation/integrations-light.svg" width="960" alt="Integrations diagram">
</picture>

The following routes are implemented in the source. Choose the input that matches your task and keep the resulting artifact with your project.

| Route | Implemented role |
| --- | --- |
| Windows UIA | Native accessibility control patterns |
| Anthropic / OpenAI | Configured model action providers |
| MCP / LangChain | Optional framework adapters |
| OCR fallback | Optional vision extra and Tesseract |

## Limits and next steps

- Native automation requires an interactive Windows desktop and applications with useful UIA controls. The offline example cannot validate that environment.
- The demonstration uses a fake control tree and tests pruning only; it does not click, type, call a model or automate a real app.
- Model-driven actions can change application data. A model-reported done action is not independent proof that the user’s goal succeeded.

Broader application coverage requires live Windows fixtures and outcome verification. OCR and framework adapters have additional dependencies and separate acceptance criteria.

## License and contributions

See [LICENSE](./LICENSE). When reporting an issue, include a minimal input, the command, and the observed output.
