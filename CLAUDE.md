# cli-any-app

## What This Is

A tool that captures mobile app network traffic via mitmproxy, lets users label API flows through a web UI, then uses Claude to analyze the API surface and generate installable Python Click CLI tools with SKILL.md for LLM consumption.

## Development

Always use the virtual environment. See README.md for full setup instructions.

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

Tests use in-memory SQLite and mock the Claude API. No external services needed.

## Architecture

Three-layer service:

1. **Capture Layer** (`cli_any_app/capture/`) — mitmproxy addon runs as subprocess, forwards intercepted traffic to FastAPI via HTTP POST
2. **Web UI** (`frontend/`) — React SPA for recording sessions, labeling flows, filtering domains, reviewing traffic
3. **Generation Layer** (`cli_any_app/generation/`) — 4-step pipeline: normalize → analyze (Claude) → generate (Claude) → validate

**Storage:** SQLite via async SQLAlchemy (`cli_any_app/models/`)
**API:** FastAPI REST endpoints (`cli_any_app/api/`)
**Real-time:** WebSocket for live traffic streaming

## Key Patterns

- Async SQLAlchemy with `aiosqlite` — all DB access via `async with get_session() as db:`
- mitmproxy addon communicates with FastAPI via local HTTP POST to `/api/internal/capture`
- WebSocket broadcast via `ConnectionManager` for live traffic feed
- Claude API called twice during generation: once for API analysis, once for code generation
- Domain filtering: noise domains auto-detected, togglable in UI
- Generated CLI packages: Python Click + SKILL.md, installable via pip
