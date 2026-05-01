# Regulated Medical Readiness Review

Date: 2026-05-01
Branch: `nm-cx/compliance-audit-review`
Scope: full repository review of backend API, persistence, capture/proxy, generation/LLM pipeline, frontend, tests, packaging, and operational documentation.

## Readiness Verdict

This codebase is not ready for regulated medical-field use with real customer traffic or ePHI/PHI.

The core product shape is useful, but the current implementation captures, stores, displays, and sends sensitive mobile traffic before adequate access control, redaction, retention, audit, or generated-code governance exists. The P0 tasks below should be treated as blockers before any real medical customer data is processed.

## Review Decomposition

| Track | Scope | Review focus |
| --- | --- | --- |
| Backend API and models | `cli_any_app/main.py`, `cli_any_app/api/*.py`, `cli_any_app/models/*.py` | auth, lifecycle, validation, async SQLAlchemy, data retention, auditability |
| Capture/proxy | `cli_any_app/capture/*.py`, cert and capture endpoints | mitmproxy lifecycle, certificate handling, PHI ingress, payload bounds, filtering |
| Generation/LLM pipeline | `cli_any_app/generation/*.py`, templates, generation API | PHI redaction, prompt injection, path safety, model settings, generated-code validation |
| Frontend | `frontend/src/**/*.tsx`, `frontend/src/lib/api.ts`, config | capture workflow, PHI display, generation gating, WebSocket resilience, accessibility |
| Tests/config/operations | `pyproject.toml`, package files, docs, tests, CI posture | supply chain, migration posture, CI gaps, documentation accuracy, release controls |

## Verification Performed

- `.venv/bin/python -m pytest tests/ -q`: passed, `54 passed`.
- `npm run build` in `frontend/`: passed.
- `npm run lint` in `frontend/`: passed with 1 warning in `frontend/src/pages/Dashboard.tsx` for missing `useEffect` dependencies.
- `.venv/bin/python -m pip check`: passed, no broken Python requirements.
- `.venv/bin/ruff check .`: failed with 32 diagnostics.
- Official regulatory/security reference pages checked on 2026-05-01: HHS HIPAA Security Rule, HHS HIPAA Audit Protocol, FDA cybersecurity FAQ, and NIST SSDF.

## P0 Blockers

### AUD-001: Add Authentication, Authorization, CSRF, and WebSocket Origin Checks

Priority: P0

Affected areas:
- `cli_any_app/config.py:8`
- `cli_any_app/main.py:19`
- `cli_any_app/main.py:41`
- `cli_any_app/api/settings.py:22`
- `cli_any_app/api/flows.py:86`

Problem:
- The app defaults to `0.0.0.0` and exposes all REST and WebSocket routes without auth.
- Any LAN client can enumerate sessions, read captured traffic, start or stop recording, delete data, trigger generation, or replace the Anthropic API key.
- WebSockets accept connections by session ID only.

Fix:
- Default `CLI_ANY_APP_HOST` to `127.0.0.1`.
- Add a real authenticated user/session layer, even if initially single-user local.
- Require auth on every REST route except a deliberately tiny health endpoint.
- Add CSRF protection for browser-authenticated state-changing routes.
- Require WebSocket auth tokens and validate `Origin`.
- Add explicit non-local deployment mode requiring TLS/reverse-proxy configuration.
- Ensure frontend never renders raw backend error bodies to users.

Tests to add:
- Unauthenticated REST requests return 401/403.
- Cross-origin WebSocket attempts are rejected.
- CSRF-negative POST/PUT/DELETE requests fail.
- API-key update, request retrieval, generation, deletion, and capture routes require auth.

### AUD-002: Protect Internal Capture Ingress

Priority: P0

Affected areas:
- `cli_any_app/api/capture.py:28`
- `cli_any_app/api/capture.py:44`
- `cli_any_app/capture/proxy_manager.py:23`
- `cli_any_app/capture/addon.py:43`

Problem:
- `/api/internal/capture` is publicly reachable on the same app server.
- The endpoint trusts caller-provided `session_id`.
- It does not verify that the session exists, is currently recording, or is owned by the active proxy process.
- A LAN client can inject synthetic traffic, poison generation inputs, or write large payloads into the database.

Fix:
- Generate a per-recording random capture token and pass it to mitmdump as an addon option.
- Require `Authorization: Bearer <capture_token>` or an HMAC header on capture posts.
- Reject capture unless `session.status == "recording"` and `proxy_manager.owns_session(session_id)` is true.
- Restrict capture ingress to loopback where possible, or use a Unix-domain socket/local-only side channel.
- Return clear 404/409/413 errors for invalid sessions, lifecycle state, or payload size.

Tests to add:
- Capture without token fails.
- Capture with wrong token fails.
- Capture into stopped/deleted/nonexistent sessions fails.
- Capture into a session not owned by the active proxy fails.
- Oversized headers/bodies fail closed.

### AUD-003: Redact, Minimize, Bound, and Encrypt Captured Traffic at Ingest

Priority: P0

Affected areas:
- `cli_any_app/capture/addon.py:31`
- `cli_any_app/capture/addon.py:35`
- `cli_any_app/api/capture.py:44`
- `cli_any_app/models/request.py:20`
- `frontend/src/pages/SessionReview.tsx:280`

Problem:
- Full request/response headers and bodies are captured and persisted as plaintext.
- The UI displays raw request and response bodies.
- Redaction only happens later in generation, after data has already been stored and exposed.
- This is a direct ePHI/PHI handling blocker.

Fix:
- Make body capture opt-in per session or per flow.
- Redact or drop sensitive headers before database write.
- Store minimal metadata by default: method, normalized host/path, status, content type, size, hashes, and redacted samples.
- Add strict max header bytes, request body bytes, response body bytes, and total session storage limits.
- Skip binary/file/protobuf bodies unless explicitly enabled.
- Encrypt retained payloads at rest with clear key-management documentation.
- Add retention windows, purge jobs, soft delete metadata, and generated-artifact cleanup.
- Put raw body reveal behind explicit authorization, purpose capture, and an audit event.

Tests to add:
- Authorization, cookies, API keys, JWTs, form credentials, and PHI-like body values are not stored in plaintext.
- Body capture disabled stores only metadata.
- Payload caps prevent large body persistence.
- Raw reveal writes an audit event.

### AUD-004: Replace Narrow Redaction With PHI-Aware Recursive Redaction

Priority: P0

Affected areas:
- `cli_any_app/generation/redactor.py:3`
- `cli_any_app/generation/redactor.py:32`
- `cli_any_app/generation/normalizer.py:37`
- `cli_any_app/generation/analyzer.py:222`

Problem:
- Redaction only covers exact keys in dictionaries.
- Lists, raw string bodies, query strings, path identifiers, GraphQL payloads, XML/form bodies, emails, phone numbers, DOBs, MRNs, addresses, diagnoses, medications, and many auth headers can reach the model.
- The README claims PII redaction, but implementation only covers a narrow secret subset.

Fix:
- Redact recursively across dicts, lists, scalars, URLs, query params, path segments, headers, cookies, and raw strings.
- Add PHI detectors for emails, phone numbers, dates of birth, SSN-like values, MRN/patient IDs, addresses, and health-specific terms.
- Add header denylist patterns, not just exact header names.
- Parse common body types by content type: JSON, form encoded, multipart metadata, XML, GraphQL.
- Add a fail-closed generation preflight: if redaction confidence is low or unknown body types contain candidate PHI, require manual review.
- Keep deterministic redaction placeholders that preserve shape without leaking values.

Tests to add:
- Query/path PHI redaction.
- Raw string, list, nested dict, form, XML, and GraphQL redaction.
- Medical trace fixture with patient IDs, diagnosis text, medication names, addresses, and dates.
- Prompt-injection strings are treated as data and do not alter analyzer behavior.

### AUD-005: Sandbox LLM-Generated File Paths and Package Names

Priority: P0

Affected areas:
- `cli_any_app/generation/generator.py:75`
- `cli_any_app/generation/generator.py:137`
- `cli_any_app/generation/templates/pyproject.toml.j2`
- `frontend/src/pages/SessionSetup.tsx:14`

Problem:
- `app_name` and `session_name` are weakly transformed and used in package names and output paths.
- Model-returned JSON keys are written directly as file paths.
- A malicious or broken model response can write `../` paths, overwrite trusted template files, emit invalid TOML/Python names, or create unexpected files.

Fix:
- Validate app/session names at API and UI boundaries.
- Show a generated CLI/package name preview before session creation.
- Slugify folder names and use packaging-normalized project names.
- Require valid Python identifiers for packages.
- Reject dot segments, absolute paths, path separators in names, reserved names, and oversized names.
- Resolve every output path and verify it remains under the intended `package_dir`.
- Use a strict generated file manifest: package `__init__.py`, `cli.py`, `api_client.py`, `commands/*.py`, optional tests/docs only.
- Prevent LLM output from overwriting trusted template-generated files unless explicitly allowed.

Tests to add:
- Malicious generated paths such as `../x.py`, absolute paths, symlinks, and template overwrite attempts fail.
- Invalid package/session names are rejected in API and UI.
- TOML/Python escaping tests for generated metadata.

### AUD-006: Add Generated-Code Security Validation and Sandboxed Smoke Tests

Priority: P0

Affected areas:
- `cli_any_app/generation/validator.py:10`
- `README.md:105`

Problem:
- Validation only compiles/parses Python and checks for a few filenames.
- It does not inspect build backends, dependencies, entry points, imports, subprocess usage, file/network access, plaintext secret handling, or generated CLI behavior.
- README instructs users to install generated packages even though validation is not a security gate.

Fix:
- Add generated package metadata validation.
- Add dependency allowlists and pinned dependency policy.
- Static-check generated code for disallowed imports and operations: `subprocess`, dynamic `eval`/`exec`, filesystem writes outside config, unsafe deserialization, shell usage, hidden network destinations, credential logging.
- Run generated packages in an ephemeral venv/container with network disabled except approved target hosts.
- Smoke-test import, `--help`, and representative no-op commands.
- Produce file hashes, validation report, and human approval state.
- Do not mark packages installable until security validation passes.

Tests to add:
- Generated package with unsafe import fails.
- Generated package with unexpected dependency fails.
- Generated package with malformed entry point fails.
- Sandboxed smoke test failure keeps session in `needs_review` or `validation_failed`.

## P1 High-Priority Fixes

### AUD-007: Implement a Session and Flow State Machine

Priority: P1

Affected areas:
- `cli_any_app/api/sessions.py:60`
- `cli_any_app/api/sessions.py:88`
- `cli_any_app/api/flows.py:59`
- `cli_any_app/api/capture.py:35`
- `frontend/src/pages/Recording.tsx:34`
- `frontend/src/pages/SessionReview.tsx:151`

Problem:
- Recording can start automatically when a route loads.
- Deleting a recording session does not stop mitmdump.
- Stopping recording does not always close active flows.
- Capture attaches to the latest open flow regardless of session status.
- Multiple active flows can exist.

Fix:
- Define allowed states: `created`, `recording`, `stopped`, `generating`, `complete`, `error`, `validation_failed`, `needs_review`.
- Make start, stop, delete, flow creation, capture, and generation enforce allowed transitions.
- Stop owned proxy processes on session delete.
- Close active flows on stop recording.
- Enforce one active flow per session.
- In the UI, require an explicit "Start capture" action instead of starting capture on route load.

Tests to add:
- Cannot capture while stopped.
- Delete recording session stops proxy.
- Stop recording closes active flow.
- Concurrent active flow creation is rejected.
- Navigating to the record page does not start capture until confirmed.

### AUD-008: Harden mitmdump Process Lifecycle

Priority: P1

Affected areas:
- `cli_any_app/capture/proxy_manager.py:17`
- `cli_any_app/capture/proxy_manager.py:24`
- `cli_any_app/main.py:16`

Problem:
- `Popen` returns immediately, so the session can be marked recording before mitmdump is ready.
- stdout/stderr pipes are not drained and can block.
- There is no startup health check, lock, shutdown cleanup, or robust failure propagation.

Fix:
- Add async-safe lock around start/stop.
- Check for missing `mitmdump` before marking recording.
- Add readiness probe on proxy listen port.
- Drain or redirect process logs to bounded files with redaction.
- Add graceful shutdown cleanup in FastAPI lifespan.
- Record startup/stop errors in session state.

Tests to add:
- Missing mitmdump returns conflict/error state.
- Port conflict does not mark session recording.
- Hung process is killed and state is updated.
- Concurrent start/stop is deterministic.

### AUD-009: Replace Destructive Ingest-Time Noise Filtering With Auditable Review-Time Filtering

Priority: P1

Affected areas:
- `cli_any_app/api/capture.py:30`
- `cli_any_app/api/domains.py:25`
- `cli_any_app/capture/noise_domains.py`

Problem:
- Known noise domains are discarded at ingest.
- Broad CDN patterns can hide real healthcare APIs hosted behind those providers.
- Domain filter state is in memory only, lost on restart, and unaudited.

Fix:
- Store minimal metadata for all domains.
- Default to a target-domain allowlist selected by the user.
- Persist domain filter decisions in a database table with actor, timestamp, reason, and source.
- Normalize hostnames with lowercase, trailing-dot handling, and IDNA.
- Apply inclusion/exclusion at review/generation time, not capture time.

Tests to add:
- Noise domain metadata remains reviewable.
- Filters persist after restart.
- Domain toggles for nonexistent sessions/domains fail.
- Domain changes create audit events.

### AUD-010: Add Database Migrations, Constraints, and Audit Tables

Priority: P1

Affected areas:
- `cli_any_app/models/database.py:18`
- `cli_any_app/models/session.py:13`
- `cli_any_app/models/flow.py:13`
- `cli_any_app/models/request.py:13`

Problem:
- Startup uses `Base.metadata.create_all`.
- There is no migration history, downgrade/upgrade path, schema drift detection, or migration CI.
- Models lack key indexes, uniqueness constraints, check constraints, and audit metadata.

Fix:
- Add Alembic.
- Enable SQLite foreign key enforcement for local deployments.
- Add indexes on foreign keys and common query fields.
- Add status enum/check constraints.
- Add `UniqueConstraint(session_id, order)` on flows.
- Add audit tables for session, capture, filter, reveal, generation, delete, and settings events.
- Add `created_at`, `updated_at`, `deleted_at`, retention metadata, and purge state where appropriate.

Tests to add:
- Migration upgrade/downgrade smoke tests.
- Foreign key enforcement tests.
- Cascade/delete and artifact cleanup tests.
- Audit event creation tests.

### AUD-011: Add Immutable Generation Attempts and Reproducibility Metadata

Priority: P1

Affected areas:
- `cli_any_app/api/generate.py:21`
- `cli_any_app/api/generate.py:93`
- `cli_any_app/api/generate.py:103`
- `cli_any_app/models/generated_cli.py`

Problem:
- Repeated generation can race and overwrite state.
- `_run_generation` select-then-inserts under a unique `session_id`.
- `validation_errors` can still lead to a `complete` status.
- Only `api_spec`, `package_path`, and `SKILL.md` are persisted.

Fix:
- Add a `generation_attempts` table.
- Atomically transition to `generating` only from allowed states.
- Use idempotency keys or active-attempt locks.
- Persist normalized/redacted input hashes, prompts, model/version, token settings, response IDs, generated file hashes, validation report, and approval status.
- Store validation failures as `validation_failed` or `needs_review`, not `complete`.

Tests to add:
- Double-click generation creates at most one active attempt.
- Validation errors do not show success/installable state.
- Attempt metadata is persisted and immutable.
- Generated file hashes match stored records.

### AUD-012: Treat Captured Traffic as Hostile Prompt-Injection Input

Priority: P1

Affected areas:
- `cli_any_app/generation/analyzer.py:100`
- `cli_any_app/generation/analyzer.py:222`
- `cli_any_app/generation/analyzer.py:360`

Problem:
- Captured headers, URLs, request bodies, response bodies, and labels are untrusted data.
- The analyzer returns them verbatim as tool results.
- The resulting spec is accepted as instructions for code generation.

Fix:
- Add explicit untrusted-data boundaries to prompts.
- Reduce `get_request_detail` exposure and require targeted detail retrieval.
- Validate submitted API specs with Pydantic/jsonschema.
- Reject endpoints, methods, hosts, commands, or dependencies not observed/approved.
- Add total data and token budgets.
- Add a policy gate between analysis and code generation.

Tests to add:
- Prompt-injection text inside traffic cannot change system behavior.
- Submitted specs with unobserved endpoints fail.
- Unknown properties and invalid names fail schema validation.

### AUD-013: Add LLM Timeout, Retry, Model, and Audit Controls

Priority: P1

Affected areas:
- `cli_any_app/generation/analyzer.py:320`
- `cli_any_app/generation/generator.py:119`
- `cli_any_app/config.py`

Problem:
- LLM calls use hard-coded model names and no explicit timeout/retry/backoff settings.
- There is no request ID, token-budget policy, temperature configuration, or model audit trail.

Fix:
- Add settings for model, timeout, retries, backoff, temperature, and max tokens.
- Validate API key presence before background jobs start.
- Persist request/response metadata without storing unredacted PHI.
- Add safe user-facing errors that omit prompts, bodies, paths, and secrets.

Tests to add:
- Missing API key fails before status changes to generating.
- Timeout/retry behavior is deterministic under mocked API failures.
- Progress and error messages do not contain PHI.

### AUD-014: Correct Request Ordering in Generation

Priority: P1

Affected areas:
- `cli_any_app/api/generate.py:28`
- `cli_any_app/models/flow.py:23`

Problem:
- Flows are ordered, but `Flow.requests` has no relationship `order_by`, and the selectin-loaded requests are not explicitly ordered.
- API inference depends on request chronology for auth, pagination, and stateful medical workflows.

Fix:
- Define `Flow.requests` with `order_by=(CapturedRequest.timestamp, CapturedRequest.id)`.
- Or load requests explicitly ordered when serializing for generation.
- Include sequence numbers in normalized data.

Tests to add:
- Generation serialization preserves request timestamp/id order.
- Auth-before-dependent-request ordering is stable.

### AUD-015: Fix Certificate and Device Pairing Controls

Priority: P1

Affected areas:
- `cli_any_app/api/cert.py:31`
- `cli_any_app/api/cert.py:60`
- `cli_any_app/api/cert.py:70`
- `frontend/src/pages/Dashboard.tsx:93`

Problem:
- The app serves a long-lived mitmproxy CA over unauthenticated HTTP.
- QR generation can point to `0.0.0.0`.
- Fallback interface detection uses an external `8.8.8.8` connect trick.
- There is no per-session CA, one-time download, pairing token, rotation, or removal workflow.

Fix:
- Use per-session mitmproxy `confdir` and CA where feasible.
- Require authenticated one-time certificate download or pairing token.
- Generate cert URLs from an explicit user-selected LAN host, never `0.0.0.0`.
- Avoid external network interface detection.
- Add setup warnings, certificate removal instructions, active proxy scope, and teardown reminders.

Tests to add:
- QR endpoint never emits `0.0.0.0`.
- Certificate download requires auth/pairing.
- Session cleanup destroys per-session CA material where configured.

## P2 Important Fixes

### AUD-016: Add Input Validation and Size Limits

Priority: P2

Affected areas:
- `cli_any_app/api/sessions.py:13`
- `cli_any_app/api/flows.py:15`
- `cli_any_app/api/capture.py:16`
- `frontend/src/pages/SessionSetup.tsx:14`

Fix:
- Use Pydantic constraints for UUID/path params, HTTP method enum, status code range, URL validation, bounded session and flow labels, bounded headers/body sizes, and safe app slugs.
- Return structured 422/413 responses.
- Mirror validation in frontend with CLI/package preview.

### AUD-017: Normalize and Sanitize URLs Correctly

Priority: P2

Affected areas:
- `cli_any_app/generation/normalizer.py:26`
- `cli_any_app/generation/normalizer.py:37`
- `cli_any_app/capture/filters.py:27`

Fix:
- Use scheme-specific default ports: HTTP 80, HTTPS 443.
- Parse query params into structured redacted fields.
- Replace UUID/date/email/MRN-like path segments, not just numeric IDs.
- Normalize hosts case/trailing-dot/IDNA.

### AUD-018: Fix Frontend PHI Display and Generation Gating

Priority: P2

Affected areas:
- `frontend/src/pages/SessionReview.tsx:180`
- `frontend/src/pages/SessionReview.tsx:280`
- `frontend/src/pages/Recording.tsx:320`
- `frontend/src/lib/api.ts:8`

Fix:
- Redact URL query params by default in live traffic and review pages.
- Mask request/response bodies by default with explicit reveal reason.
- Gate generation on enabled API request count, selected flows, redaction preflight, and reviewer acknowledgement.
- Normalize backend errors to safe messages.
- Fetch exact generated package path from backend instead of recomputing it in `GenerationProgress`.

### AUD-019: Bound and Recover WebSocket Streams

Priority: P2

Affected areas:
- `frontend/src/pages/Recording.tsx:60`
- `frontend/src/pages/Recording.tsx:66`
- `frontend/src/pages/GenerationProgress.tsx:115`
- `frontend/src/pages/GenerationProgress.tsx:225`

Fix:
- Use bounded buffers or virtualization for traffic and logs.
- Show connected/disconnected/reconnecting states.
- Backfill missed events through REST.
- Add retry with jitter and safe failure copy.

### AUD-020: Fix Accessibility and Responsive Layout

Priority: P2

Affected areas:
- `frontend/src/pages/SessionReview.tsx:212`
- `frontend/src/pages/SessionReview.tsx:353`
- `frontend/src/pages/Recording.tsx:167`
- `frontend/src/pages/Dashboard.tsx:90`
- `frontend/src/components/StatusBadge.tsx`
- `frontend/src/components/MethodBadge.tsx`

Fix:
- Replace clickable `div`s with semantic buttons.
- Add `aria-expanded`, `aria-pressed`, `role="switch"`, labels, keyboard support, and `role="alert"` for errors.
- Add visible focus styles and reduced-motion handling.
- Add mobile/tablet layouts for recording, review, and setup panels.

### AUD-021: Make Destructive Actions Safer

Priority: P2

Affected areas:
- `frontend/src/pages/Dashboard.tsx:59`
- `frontend/src/pages/SessionReview.tsx:101`
- `cli_any_app/api/sessions.py:60`
- `cli_any_app/api/flows.py:113`

Fix:
- Require typed confirmation or modal with request counts for deletion.
- Disable while deleting.
- Add failed-delete state.
- Add export/retention guidance.
- Prefer soft delete with purge workflow for regulated data.

### AUD-022: Harden Generated CLI Secret Handling

Priority: P2

Affected areas:
- `cli_any_app/generation/templates/config.py.j2:4`
- `cli_any_app/generation/templates/config.py.j2:14`
- `cli_any_app/generation/generator.py:43`

Fix:
- Store tokens in OS keychain where possible.
- If file storage remains, create config directories/files with restrictive permissions (`0700` directory, `0600` file).
- Redact verbose logs by default.
- Replace raw `--verbose` HTTP dump with redacted debug output and an explicit unsafe local-only mode.

## Tests, CI, and Supply Chain Tasks

### AUD-023: Fix Ruff and Add CI

Priority: P1

Current result:
- `.venv/bin/ruff check .` fails with 32 diagnostics.
- Main categories: E402 import ordering, unused imports/re-exports, and F821 forward references in model annotations.

Fix:
- Fix current Ruff failures.
- Add `.github/workflows/ci.yml`.
- Run backend pytest with coverage, Ruff, type checking (`mypy` or Pyright), frontend lint, frontend typecheck, frontend tests, frontend build, package smoke tests, and security scans.

### AUD-024: Add Frontend Test Harness

Priority: P2

Affected areas:
- `frontend/package.json`
- `frontend/src/pages/*.tsx`
- `frontend/src/lib/api.ts`

Fix:
- Add Vitest, React Testing Library, MSW, and axe checks.
- Test capture lifecycle, explicit start confirmation, domain filtering, redaction display, generation gating, WebSocket disconnect/reconnect, delete confirmation, and accessibility semantics.

### AUD-025: Add Backend Security Regression Tests

Priority: P1

Fix:
- Auth/CSRF/WS-origin negative tests.
- Capture token/status/ownership tests.
- PHI redaction at ingest and before LLM tests.
- Malicious generated path tests.
- Concurrent flow creation tests.
- Concurrent generation tests.
- Migration and cascade tests.
- Retention and audit event tests.

### AUD-026: Pin, Audit, and Document Dependencies

Priority: P2

Affected areas:
- `pyproject.toml:10`
- `frontend/package.json:12`
- `frontend/package-lock.json:3559`
- `frontend/package-lock.json:3893`
- `README.md:46`

Problem:
- Python dependencies are lower-bound-only.
- Frontend dependencies use caret ranges.
- README says Node 18+, but locked React Router requires Node >=20 and Vite requires Node >=20.19 or >=22.12.

Fix:
- Use a Python lockfile with hashes for reproducible installs.
- Use `npm ci` in CI and releases.
- Update README to Node 20.19+ or a dependency set that supports Node 18.
- Run `pip-audit`, `npm audit`, license scans, and produce CycloneDX/SPDX SBOMs per release.

### AUD-027: Fix Packaging of Built UI

Priority: P2

Affected areas:
- `frontend/vite.config.ts:7`
- `.gitignore:14`
- `pyproject.toml:33`

Problem:
- Vite writes built assets to `cli_any_app/ui/static`.
- That directory is ignored by git.
- Python packaging only discovers packages and does not clearly include static package data.

Fix:
- Decide whether UI assets are committed, generated during release, or packaged as package data.
- Add `MANIFEST.in` or setuptools package-data config if packaging assets.
- Add wheel/sdist smoke tests that install `cli-any-app` and verify the UI serves.

### AUD-028: Update Documentation and Risk Disclosures

Priority: P2

Affected areas:
- `README.md:170`
- `docs/plans/2026-03-12-cli-any-app-design.md:70`
- `docs/plans/2026-03-12-cli-any-app-design.md:74`
- `docs/plans/2026-03-12-cli-any-app-design.md:170`

Fix:
- Correct the current PII redaction claim until real PHI-safe redaction is implemented.
- Correct the body-storage design claim; current code stores body text, not large-body file references.
- Document supported Node/Python versions.
- Document local-only vs non-local deployment requirements.
- Add medical/compliance disclaimers, data retention guidance, certificate teardown, incident response, backup/restore, and generated-code approval workflow.

## Suggested Implementation Order

1. Lock down exposure: localhost default, auth, CSRF, WebSocket auth/origin, safe errors.
2. Protect capture ingress: per-recording token, recording-state checks, loopback/local-only capture.
3. Minimize and redact at ingest: header/body caps, no raw body by default, encrypted retained payloads.
4. Add database migrations, constraints, audit events, and retention/purge foundations.
5. Replace redactor and add PHI-heavy regression fixtures.
6. Add generation governance: prompt-injection boundary, schema validation, immutable attempts.
7. Sandbox generated paths and generated-code validation.
8. Fix frontend capture/review/generation UX around explicit consent, masking, gating, accessibility, and bounded streams.
9. Add CI, Ruff/type checks, frontend tests, package smoke tests, and supply-chain scans.
10. Update documentation once implemented behavior matches the claims.

## Regulatory Baseline Used

This is not legal advice, but the review mapped findings to current official guidance themes:

- HHS HIPAA Security Rule: administrative, physical, and technical safeguards for ePHI confidentiality, integrity, and availability.
- HHS HIPAA Audit Protocol: access controls, audit controls, integrity, authentication, and transmission-security review areas.
- FDA cybersecurity FAQ: SBOM expectations for cyber devices under FD&C Act section 524B.
- NIST SP 800-218 SSDF: secure software development practices for reducing vulnerability risk.

Official references:
- HHS HIPAA Security Rule: https://www.hhs.gov/hipaa/for-professionals/security/index.html
- HHS HIPAA Audit Protocol: https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/protocol/index.html
- FDA Cybersecurity in Medical Devices FAQ: https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity-medical-devices-frequently-asked-questions-faqs
- NIST SP 800-218 SSDF: https://csrc.nist.gov/pubs/sp/800/218/final
