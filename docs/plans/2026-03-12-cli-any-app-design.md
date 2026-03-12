# cli-any-app Design Document

**Date:** 2026-03-12
**Status:** Approved

## Overview

cli-any-app transforms mobile app network traffic into agent-usable CLI tools. It captures API calls via mitmproxy while a human drives a mobile app, then uses Claude to analyze the API surface and generate an installable Python Click CLI with a `SKILL.md` for LLM consumption.

Inspired by [CLI-Anything](https://github.com/HKUDS/CLI-Anything), which generates CLIs from desktop app source code. cli-any-app differs fundamentally: it works with closed-source mobile apps by reverse-engineering the API surface from network traces rather than analyzing source code.

## Architecture

Three-layer service orchestrated by a central FastAPI server:

```
┌─────────────────────────────────────────────────────┐
│                   cli-any-app                        │
│                                                      │
│  ┌──────────────┐   ┌──────────────┐                │
│  │  FastAPI      │◄──│  Web UI      │                │
│  │  Server       │──►│  (React SPA) │                │
│  │  :8000        │   │  :8000/ui    │                │
│  └──────┬───────┘   └──────────────┘                │
│         │                                            │
│    ┌────┴────┐                                       │
│    │         │                                       │
│  ┌─▼──────┐ ┌▼───────────┐                          │
│  │Capture │ │ Generation  │                          │
│  │Layer   │ │ Layer       │                          │
│  │        │ │             │                          │
│  │mitm    │ │ Claude API  │                          │
│  │proxy   │ │ Analysis →  │                          │
│  │addon   │ │ Click CLI + │                          │
│  │:8080   │ │ SKILL.md    │                          │
│  └────────┘ └─────────────┘                          │
│                                                      │
│  ┌──────────────────────────────┐                    │
│  │  Storage (SQLite)            │                    │
│  │  - Sessions & labeled flows  │                    │
│  │  - Captured request/response │                    │
│  └──────────────────────────────┘                    │
└─────────────────────────────────────────────────────┘
         ▲
         │ proxy traffic
    ┌────┴─────┐
    │ iOS      │
    │ Device   │
    └──────────┘
```

### Capture Layer
- mitmproxy addon (`capture_addon.py`) hooks into request/response events
- Filters noise: static assets, known analytics/tracking domains, system services
- Forwards captured request/response pairs to FastAPI via local REST call
- Runs as subprocess managed by FastAPI
- Smart `is_api` detection based on content types

### Web UI Layer
- React SPA with Tailwind CSS, served as static files from FastAPI
- WebSocket for live traffic streaming
- Pages: Dashboard, Session Setup, Recording View, Session Review, Generation Progress
- Device setup: QR code for cert install, step-by-step proxy configuration guide
- Domain filter panel: live-updating domain list with toggles, auto-detection of noise domains

### Generation Layer
- 4-step pipeline: Normalize → Analyze (Claude) → Generate (Claude) → Validate
- Analysis and code generation are separate Claude calls for better results
- API Spec (analysis output) is persisted as a reusable artifact
- PII/secrets redacted before sending to Claude

### Storage
- SQLite via SQLAlchemy
- Stores sessions, labeled flows, raw request/response data
- Large response bodies stored as file references

## Data Model

```
Session
├── id (uuid)
├── name ("Uber Eats ordering flow")
├── app_name ("uber-eats")
├── status (recording | stopped | generating | complete)
├── created_at
├── proxy_port
│
├── Flows[] (labeled groups of requests)
│   ├── id (uuid)
│   ├── label ("login", "search restaurants", "add to cart")
│   ├── order (sequence within session)
│   ├── started_at / ended_at
│   │
│   └── Requests[]
│       ├── id (uuid)
│       ├── timestamp
│       ├── method (GET/POST/PUT/DELETE)
│       ├── url
│       ├── request_headers (JSON)
│       ├── request_body (JSON/binary reference)
│       ├── status_code
│       ├── response_headers (JSON)
│       ├── response_body (JSON/binary reference)
│       ├── content_type
│       └── is_api (bool)
│
└── GeneratedCLI (one per session)
    ├── id (uuid)
    ├── api_spec (intermediate JSON)
    ├── package_path (filesystem path)
    ├── skill_md (generated SKILL.md content)
    └── created_at
```

## Domain Filtering

All device traffic flows through the proxy, not just the target app. Filtering is critical.

**During recording:**
- Collapsible "Domains" sidebar with live-updating domain list
- Toggle switch per domain, request count per domain
- Auto-untick known noise: `*.apple.com`, `*.icloud.com`, `firebaselogging.googleapis.com`, `app-measurement.com`, `*.facebook.com`, `*.crashlytics.com`, etc.
- Auto-detected categories: "Apple system", "Analytics", "Target app API"

**Session review (before generation):**
- Full domain breakdown with request counts and data volume
- Bulk actions: "Select only these domains"
- Preview of filtered data that will be sent to generation pipeline

## Device Setup

- Cert served at `http://<host>:8000/cert` — navigable from Safari on iOS device
- QR code on dashboard pointing to cert URL
- First-run setup wizard: configure proxy → install cert → trust CA → verify connection
- Green "Connected" indicator when first proxied request comes through

## Generation Pipeline

**Step 1: Trace Normalization**
- Extract API requests grouped by flow labels
- Strip volatile data (timestamps, request IDs, device-specific headers)
- Identify URL patterns (`/items/123` → `/items/{id}`)
- Output: clean intermediate JSON format

**Step 2: AI Analysis (Claude API)**
- Auth pattern detection (bearer, cookie, API key, refresh mechanism)
- Endpoint catalog with purpose, required/optional params, response shape
- Command grouping into CLI command groups
- State dependencies (which commands must precede others)
- Parameter inference (user-provided vs. derived from previous responses)

**Step 3: Code Generation (Claude API)**
- `cli.py` — Click entry point & command groups
- `api_client.py` — HTTP client with auth management
- `config.py` — Config file management
- `commands/*.py` — Individual command modules
- `setup.py` + `pyproject.toml` — Installable package
- `SKILL.md` — LLM-readable guide
- `models.py` — Response dataclasses (optional)
- `tests/` — Test stubs

**Step 4: Validation**
- `py_compile` syntax check on all generated files
- Verify Click CLI structure loads without errors
- Optional dry-run command validation

## Generated CLI Conventions

- JSON output by default (agent-friendly), `--format table` for humans
- `--verbose` flag shows raw HTTP request/response
- Auth token stored in config file, auto-refreshed if refresh mechanism detected
- Exit codes: 0 success, 1 API error, 2 auth error, 3 config error

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, FastAPI, SQLAlchemy |
| Proxy | mitmproxy (addon API) |
| Frontend | React, TypeScript, Tailwind CSS |
| AI | Claude API (Anthropic SDK) |
| Database | SQLite |
| Generated CLIs | Python, Click |
| Real-time | WebSocket |

## Project Structure

```
cli-any-app/
├── pyproject.toml
├── requirements.txt
├── cli_any_app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, entry point
│   ├── config.py                # App settings, paths, defaults
│   │
│   ├── capture/
│   │   ├── __init__.py
│   │   ├── addon.py             # mitmproxy addon
│   │   ├── proxy_manager.py     # Start/stop/health-check mitmproxy subprocess
│   │   ├── filters.py           # Domain filtering, is_api heuristics
│   │   └── noise_domains.py     # Known noise domain list
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── sessions.py          # Session CRUD
│   │   ├── flows.py             # Flow labeling
│   │   ├── capture.py           # Internal endpoint receiving from addon
│   │   ├── domains.py           # Domain listing/filtering
│   │   ├── cert.py              # Certificate serving
│   │   └── websocket.py         # Live traffic streaming
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py          # SQLAlchemy setup
│   │   ├── session.py
│   │   ├── flow.py
│   │   └── request.py
│   │
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── pipeline.py          # Orchestrates generation steps
│   │   ├── normalizer.py        # Trace normalization
│   │   ├── analyzer.py          # Claude API analysis
│   │   ├── generator.py         # Claude API code generation
│   │   ├── validator.py         # Syntax/structure validation
│   │   ├── redactor.py          # PII/secret stripping
│   │   └── templates/           # Jinja templates for boilerplate
│   │
│   └── ui/
│       └── static/              # Built React SPA assets
│
├── frontend/                    # React SPA source
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── SessionSetup.tsx
│   │   │   ├── Recording.tsx
│   │   │   ├── SessionReview.tsx
│   │   │   └── GenerationProgress.tsx
│   │   └── components/
│   │       ├── TrafficFeed.tsx
│   │       ├── FlowControls.tsx
│   │       ├── DomainFilter.tsx
│   │       ├── DeviceSetup.tsx
│   │       └── QRCode.tsx
│
├── tests/
│   ├── test_capture/
│   ├── test_generation/
│   └── test_api/
│
└── data/
    ├── cli_any_app.db
    └── generated/
```

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Platform | iOS first | Device is mostly irrelevant; capture is platform-agnostic |
| Capture UX | Semi-automated (labeled recording) | Human drives app, labels flows for better AI context |
| Recording UI | Web-based | Most flexible, mitmproxy already has web paradigm |
| Generated CLI | Python Click + SKILL.md | Agent-friendly, installable, LLM-readable docs |
| AI analysis depth | Semantic understanding | Smart grouping of observed traffic, no hallucinated endpoints |
| Auth handling | Smart detection from trace | AI infers auth pattern from labeled auth flow |
| Tool tech stack | All Python (backend) + React (frontend) | mitmproxy is Python-native, simplifies integration |
| Architecture | Three-layer service | Clean separation, independently testable, room to grow |
