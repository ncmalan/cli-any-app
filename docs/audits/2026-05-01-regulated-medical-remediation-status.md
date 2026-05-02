# Regulated Medical Remediation Status

Date: 2026-05-01
Branch: `nm-cx/compliance-audit-review`
Target posture: Local Regulated MVP

## Current Status

The first implementation pass for the eight-phase remediation roadmap is complete.
The app now defaults to a single-operator local posture, protects browser/API
surfaces with local authentication and CSRF controls, protects capture ingress with
per-recording tokens, stores capture data metadata-first by default, audits sensitive
operator actions, and gates generation on redaction/preflight/validation/approval.

This is not a hosted or multi-tenant compliance posture. Real PHI/ePHI use should
still wait for the residual hardening items below, operational SOPs, and a formal
security/compliance review.

## Implemented By Phase

### Phase 1: Stop Unauthenticated Exposure

- Server bind defaults to `127.0.0.1`.
- LAN exposure requires `CLI_ANY_APP_ALLOW_LAN=true`.
- Added single-operator local auth endpoints.
- Added signed `HttpOnly`, `SameSite=Lax` session cookie.
- Added generated first-run admin password with hashed secret storage under
  `data/secrets/`.
- Added CSRF checks for browser state changes.
- Added frontend API client CSRF handling.
- Added short-lived WebSocket auth token and origin validation.
- Replaced raw frontend error display with bounded safe messages.

### Phase 2: Protect Capture Ingress and Lifecycle

- Added per-recording capture tokens.
- mitmdump receives the plaintext capture token through subprocess environment.
- Capture addon sends `X-Capture-Token`.
- `/api/internal/capture` rejects missing/bad token, wrong session state, and
  non-owned sessions.
- Added explicit session states.
- Session delete stops owned proxy processes.
- Stop recording closes active flows.
- Enforced one active flow per session.
- Removed recording auto-start on route load.

### Phase 3: Minimize, Redact, Bound, and Encrypt Captures

- Raw body capture is disabled by default.
- Default persistence stores method, host, redacted URL, status, content type,
  body sizes, body hashes, and redaction status.
- Sensitive headers and query secrets are redacted before database write.
- Request/response size caps reject oversized capture payloads.
- Binary/protobuf/file bodies are skipped unless raw capture is explicitly enabled.
- Optional encrypted raw payload storage uses a local data key under `data/secrets/`.
- Raw reveal requires an authenticated reason and writes audit evidence.
- Added retention fields and purge foundation.

### Phase 4: Persistence, Audit, and Domain Decisions

- Added Alembic baseline migration.
- Added schema constraints and indexes for session status, flow order, and common
  foreign-key lookups.
- Added `audit_events`, `domain_filters`, `generation_attempts`, and encrypted
  payload persistence.
- Domain include/exclude decisions persist with audit events.
- Capture ingest keeps minimal metadata for all domains; filtering is applied at
  review/generation time.

### Phase 5: PHI-Aware Redaction and Generation Preflight

- Added recursive redaction across nested structures and string/URL-like values.
- Added PHI detectors for common medical/customer identifiers.
- Added deterministic placeholders that preserve shape.
- Added generation preflight checks for enabled API requests, selected domains,
  redaction status, and reviewer acknowledgement.

### Phase 6: LLM and Generated Artifact Governance

- Analyzer prompts treat captured traffic as hostile input.
- Analyzer output is schema-validated against observed hosts, methods, and paths.
- Added configurable LLM model/timeout/retry/backoff/token/temperature settings.
- Added immutable generation attempts with input, prompt, response, file, and
  validation hashes.
- Sandboxed generated output paths under a strict containment check.
- Added dependency allowlist, unsafe import/call checks, metadata validation, and
  optional isolated install/`--help` smoke test.
- Validation failures now move sessions to `validation_failed` or `needs_review`,
  not `complete`.
- Generated package install instructions remain hidden until approval.

### Phase 7: Frontend Safety, Accessibility, and Resilience

- Added explicit Start Capture/Stop Recording workflow.
- Review screens show metadata/redacted values by default.
- Added generation checklist and approval controls.
- Bounded live traffic buffer.
- Added WebSocket connection states.
- Converted key interactive controls to semantic buttons/switches.
- Added ARIA state, alert roles, keyboard-operable controls, and focused frontend
  accessibility tests.

### Phase 8: CI, Packaging, Supply Chain, and Docs

- Fixed Ruff failures.
- Added CI for backend tests with coverage, Ruff, frontend lint/test/build,
  wheel smoke install, dependency audit, and SBOM artifacts.
- Added Vitest, React Testing Library, MSW, and axe frontend test harness.
- Added Alembic and package-data configuration for migrations/static assets.
- Added `uv.lock` for reproducible dependency resolution.
- Updated README for local regulated mode, Node 20.19+, `npm ci`, migrations,
  retention, raw payload handling, generated-code approval, and non-local
  deployment boundaries.

## Verification Run

- `source .venv/bin/activate && pytest tests/ -q`: 62 passed.
- `source .venv/bin/activate && ruff check .`: passed.
- `cd frontend && npm run lint`: passed.
- `cd frontend && npm run test`: 3 test files passed.
- `cd frontend && npm run build`: passed.
- `source .venv/bin/activate && python -m compileall cli_any_app`: passed.
- `git diff --check`: passed.
- `cd frontend && npm audit --audit-level=high`: found 0 vulnerabilities.
- `uv run --isolated --all-extras --with pip-audit pip-audit`: no known
  project dependency vulnerabilities found.
- `CLI_ANY_APP_DB_URL=sqlite+aiosqlite:////private/tmp/cli-any-app-alembic-test.db uv run --with alembic alembic upgrade head`:
  passed against an empty SQLite database.

Note: direct `pip-audit` against this workstation's active `.venv` also sees a
pip-installed `mitmproxy` toolchain. That local tool install currently has an
upstream dependency conflict between the mitmproxy security fix and pyOpenSSL's
reported fixed version. The repository continues to treat mitmproxy as an external
system tool; for regulated use, keep mitmproxy outside the app venv and update it
through the system package manager as fixes are released.

## Residual Hardening Required

- Formal HIPAA/security/compliance review remains required before real PHI/ePHI use.
- Local file encryption keys are acceptable only for MVP; hosted use needs managed
  key storage, key rotation, backups, and recovery procedures.
- PHI detection is conservative application logic, not a de-identification guarantee.
  Expand fixture coverage with real-world medical trace patterns before production use.
- Generated CLI validation uses static checks plus optional isolated venv smoke tests;
  full containerized network egress allowlisting is still a recommended next step.
- Browser-level end-to-end tests should be added for the complete capture, review,
  reveal, generation, approval, and reconnect flows.
- Alembic baseline should be rehearsed against a copy of any existing local database
  before applying it to user-held data.
- Operational SOPs are still needed for retention approvals, purge cadence, backup
  handling, mitmproxy CA teardown, incident response, and generated-artifact review.

## Recommended Next Tasks

1. Add a medical trace fixture corpus and assert no plaintext sensitive values appear
   in the database, API responses, frontend defaults, generation input, logs, or
   generated artifacts.
2. Move generated CLI smoke tests into a container or sandbox with explicit network
   egress allowlists.
3. Add Playwright coverage for login, explicit capture start, stopped/deleted capture
   rejection, raw reveal reason capture, generation gating, and approval flow.
4. Create operator SOPs for regulated local use, retention, backup/restore, CA
   teardown, generated-code approval, and non-local deployment review.
5. Rehearse Alembic migrations and retention purge against a representative copy of
   existing local data.
