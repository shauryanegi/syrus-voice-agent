# Project guidance

Syrus is a LiveKit voice agent. The entrypoint is `src/agent.py`, callable tools are in
`src/tools.py`, behavior scenarios are in `scenarios.yaml`, and tool tests are in `tests/`.

## Changes and checks

- Use `uv` for Python dependencies and commands. Keep `uv.lock` in sync with `pyproject.toml`.
- Format and lint with `uv run ruff format` and `uv run ruff check`.
- Run unit tests with `uv run pytest` after changing application code.
- When changing the persona, tool descriptions, or tool behavior, update the relevant
  scenario or test. Simulation tool responses must remain fixture-backed; do not let
  simulations call real external services.
- LiveKit APIs change quickly. Check the installed CLI help and current LiveKit docs
  before using unfamiliar APIs.
- Never read, print, commit, or copy values from `.env.local`. Add variable names only
  to `.env.example` and configure secrets through the environment.

## Assistant behavior

Keep Syrus voice-first: brief plain-spoken answers, one question at a time, with warmth
and restrained humor. Preserve the exact response rule and safety limits in the agent
instructions. The supported capabilities are web search, weather, dictionary lookup,
and session camera vision; do not add browser-control behavior without an explicit request.
