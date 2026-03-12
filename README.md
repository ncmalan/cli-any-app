# cli-any-app

Transform mobile app network traffic into agent-usable CLI tools.

Captures API calls via mitmproxy while you drive a mobile app, lets you label the flows through a web UI, then uses Claude to analyze the API surface and generate an installable Python Click CLI with a SKILL.md for LLM consumption.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- mitmproxy (`brew install mitmproxy`)

### Setup

```bash
git clone <repo-url>
cd cli-any-app

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Set your Anthropic API key
export CLI_ANY_APP_ANTHROPIC_API_KEY=your-key-here

# Build the frontend
cd frontend
npm install
npm run build
cd ..

# Start the server
cli-any-app
```

The web UI is available at http://localhost:8000.

### Frontend Development

For hot-reloading during frontend development, run the Vite dev server alongside the backend:

```bash
# Terminal 1: backend
source .venv/bin/activate
cli-any-app

# Terminal 2: frontend dev server
cd frontend
npm run dev  # starts on :5173, proxies /api and /ws to :8000
```

## Usage

1. Open the web UI at http://localhost:8000
2. Create a new session (name it, specify the app name)
3. Configure your iOS device to use the proxy (the UI shows instructions and a QR code for the CA certificate)
4. Start recording, then open the target app on your device
5. Use the "Start Flow" / "Stop Flow" buttons to label actions as you navigate the app (e.g., "login", "search", "add to cart")
6. Use the domain filter to exclude irrelevant traffic
7. Stop recording, review the captured flows
8. Click "Generate CLI" to produce a Python Click CLI package

The generated CLI package will be in `data/generated/<app-name>/` and can be installed with:

```bash
pip install ./data/generated/<app-name>/
```

## Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

Tests use in-memory SQLite and mock the Claude API. No external services needed.

## Architecture

Three-layer service orchestrated by FastAPI:

1. **Capture Layer** (`cli_any_app/capture/`) -- mitmproxy addon runs as a subprocess, forwards intercepted traffic to FastAPI via HTTP POST
2. **Web UI** (`frontend/`) -- React SPA for recording sessions, labeling flows, filtering domains, reviewing traffic
3. **Generation Layer** (`cli_any_app/generation/`) -- 4-step pipeline: normalize, analyze (Claude), generate (Claude), validate

**Storage:** SQLite via async SQLAlchemy (`cli_any_app/models/`)
**API:** FastAPI REST endpoints (`cli_any_app/api/`)
**Real-time:** WebSocket for live traffic streaming

## Configuration

All settings can be overridden via environment variables with the `CLI_ANY_APP_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLI_ANY_APP_HOST` | `0.0.0.0` | Server bind address |
| `CLI_ANY_APP_PORT` | `8000` | Server port |
| `CLI_ANY_APP_PROXY_PORT` | `8080` | mitmproxy listen port |
| `CLI_ANY_APP_DEBUG` | `false` | Enable debug mode with auto-reload |
| `CLI_ANY_APP_ANTHROPIC_API_KEY` | (required) | Anthropic API key for Claude |
