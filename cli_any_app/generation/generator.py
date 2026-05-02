import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
import anthropic

from cli_any_app.config import settings

TEMPLATES_DIR = Path(__file__).parent / "templates"

GENERATION_PROMPT = """You are an expert Python developer. Generate a complete Python Click CLI tool based on this API specification.

The API spec describes a mobile app's backend API that was reverse-engineered from network traffic.

## API Specification

{api_spec}

## Requirements

Generate these files as a JSON object where keys are file paths and values are file contents:

1. **{{package_name}}/cli.py** — Main Click entry point with command groups. Use @click.group() for the top-level and subgroups matching command_groups.

2. **{{package_name}}/api_client.py** — HTTP client class wrapping all endpoints. Handles:
   - Auth token storage/retrieval from config
   - Token refresh if refresh_endpoint is specified
   - Base URL management
   - All API calls as methods

3. **{{package_name}}/commands/*.py** — One file per command group. Each command:
   - Uses Click options for parameters
   - Calls api_client methods
   - Outputs JSON by default, table with --format table
   - Handles errors gracefully

4. **{{package_name}}/__init__.py** — Empty

Important:
- Package name: {package_name}
- CLI entry point name: {cli_name}
- Use `click` for CLI framework
- Use `httpx` for HTTP client
- All commands output JSON by default
- Include --verbose flag for raw HTTP output
- Include --format option (json/table)
- Exit codes: 0=success, 1=API error, 2=auth error, 3=config error

Respond with ONLY a JSON object mapping file paths to file contents. No markdown fences."""

SKILL_MD_PROMPT = """Generate a SKILL.md file for an AI agent to understand how to use this CLI tool.

## API Specification
{api_spec}

## CLI Name
{cli_name}

## Requirements

The SKILL.md should include:
1. Tool name and one-line description
2. Setup instructions (pip install, authentication)
3. Available commands with examples
4. Typical workflow (ordered steps)
5. Output format (JSON by default)

Keep it concise and practical. An AI agent should be able to read this and immediately use the CLI.

Respond with ONLY the markdown content, no fences."""


def get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def _safe_slug(value: str, fallback: str = "generated-cli") -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-_")
    return slug or fallback


def _safe_package_name(value: str) -> str:
    name = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not name or not name[0].isalpha():
        name = f"cli_{name or 'generated'}"
    return name[:64]


def _safe_output_path(package_dir: Path, filepath: str, package_name: str) -> Path:
    candidate = Path(filepath)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe generated path: {filepath}")
    if not candidate.parts or candidate.parts[0] != package_name:
        raise ValueError(f"Generated path must stay inside package module: {filepath}")
    out_file = (package_dir / candidate).resolve()
    root = package_dir.resolve()
    if root not in out_file.parents:
        raise ValueError(f"Generated path escapes package directory: {filepath}")
    return out_file


async def generate_cli_package(api_spec: dict, output_dir: Path, on_progress=None, session_name: str = "") -> Path:
    app_name = api_spec.get("app_name", "generated-cli")
    cli_name = _safe_slug(app_name)
    package_name = _safe_package_name(cli_name.replace("-", "_"))

    # Use session name as subfolder if provided, otherwise timestamp, to avoid overwrites
    if session_name:
        folder_name = f"{cli_name}_{_safe_slug(session_name, 'session')}"
    else:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        folder_name = f"{cli_name}_{ts}"

    package_dir = output_dir / folder_name
    package_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate boilerplate from Jinja templates
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    template_context = {
        "app_name": app_name,
        "cli_name": cli_name,
        "package_name": package_name,
        "base_urls": api_spec.get("base_urls", []),
        "auth": api_spec.get("auth", {}),
        "command_groups": api_spec.get("command_groups", []),
    }

    protected_paths: set[Path] = set()
    for template_name, output_path in [
        ("pyproject.toml.j2", "pyproject.toml"),
        ("config.py.j2", f"{package_name}/config.py"),
    ]:
        template = env.get_template(template_name)
        content = template.render(**template_context)
        out_file = package_dir / output_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content)
        protected_paths.add(out_file.resolve())

    # Step 2: Generate CLI code via Claude
    client = get_client()

    if on_progress:
        await on_progress("generating", "Generating CLI code...")

    code_response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        messages=[
            {
                "role": "user",
                "content": GENERATION_PROMPT.format(
                    api_spec=json.dumps(api_spec, indent=2),
                    package_name=package_name,
                    cli_name=cli_name,
                ),
            }
        ],
    )
    code_text = code_response.content[0].text
    if code_text.startswith("```"):
        code_text = code_text.split("\n", 1)[1].rsplit("```", 1)[0]

    files = json.loads(code_text)
    if not isinstance(files, dict):
        raise ValueError("Generator response must be a JSON object mapping paths to contents")
    for filepath, content in files.items():
        out_file = _safe_output_path(package_dir, filepath, package_name)
        if out_file.resolve() in protected_paths:
            raise ValueError(f"Generated output may not overwrite trusted template file: {filepath}")
        if out_file.exists():
            raise ValueError(f"Generated output may not overwrite existing file: {filepath}")
        if not isinstance(content, str):
            raise ValueError(f"Generated file content must be a string: {filepath}")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content)
        if on_progress:
            await on_progress("generating", f"Wrote {filepath}")

    # Step 3: Generate SKILL.md via Claude
    if on_progress:
        await on_progress("generating", "Generating SKILL.md...")

    skill_response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=4096,
        temperature=settings.llm_temperature,
        messages=[
            {
                "role": "user",
                "content": SKILL_MD_PROMPT.format(
                    api_spec=json.dumps(api_spec, indent=2),
                    cli_name=cli_name,
                ),
            }
        ],
    )
    skill_text = skill_response.content[0].text
    if skill_text.startswith("```"):
        skill_text = skill_text.split("\n", 1)[1].rsplit("```", 1)[0]
    (package_dir / "SKILL.md").write_text(skill_text)

    return package_dir
