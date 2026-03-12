# cli-any-app

## What This Is

A tool that captures mobile app network traffic via mitmproxy, lets users label API flows through a web UI, then uses Claude to analyze the API surface and generate installable Python Click CLI tools with SKILL.md for LLM consumption.

## Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- mitmproxy (`brew install mitmproxy` or `pip install mitmproxy`)

### Backend

```bash
pip install -e ".[dev]"
cli-any-app  # starts FastAPI on :8000
```

### Frontend (dev mode)

```bash
cd frontend
npm install
npm run dev  # starts Vite dev server on :5173, proxies /api to :8000
```

### Build frontend for production

```bash
cd frontend && npm run build  # outputs to cli_any_app/ui/static/
```

## Testing

```bash
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
