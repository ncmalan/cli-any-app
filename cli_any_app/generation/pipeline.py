from collections.abc import Callable, Coroutine
from typing import Any

from cli_any_app.config import settings
from cli_any_app.generation.analyzer import analyze_api_surface
from cli_any_app.generation.generator import generate_cli_package
from cli_any_app.generation.normalizer import normalize_session_data
from cli_any_app.generation.redactor import redact_sensitive_data
from cli_any_app.generation.validator import validate_generated_cli

ProgressCallback = Callable[[str, str, str | None], Coroutine[Any, Any, None]]


async def run_pipeline(
    session_data: dict,
    session_id: str,
    on_progress: ProgressCallback | None = None,
) -> dict:
    output_dir = settings.generated_dir

    async def emit(step: str, message: str, detail: str | None = None):
        if on_progress:
            await on_progress(step, message, detail)

    # Step 1: Normalize
    await emit("normalizing", "Normalizing captured traffic...")
    normalized = normalize_session_data(session_data)
    flow_count = len(normalized.get("flows", []))
    req_count = sum(len(f.get("requests", [])) for f in normalized.get("flows", []))
    await emit("normalizing", f"Normalized {req_count} API requests across {flow_count} flows")

    # Step 2: Redact & Analyze
    await emit("analyzing", "Redacting sensitive data...")
    redacted = redact_sensitive_data(normalized)
    api_spec = await analyze_api_surface(redacted, on_progress=on_progress)

    # Step 3: Generate
    await emit("generating", "Generating CLI package with Claude...")
    package_path = await generate_cli_package(api_spec, output_dir, on_progress=on_progress)
    await emit("generating", f"Package written to {package_path}")

    # Step 4: Validate
    await emit("validating", "Validating generated package...")
    validation = validate_generated_cli(package_path)
    if validation["valid"]:
        await emit("validating", "Validation passed!")
    else:
        await emit("validating", f"Validation issues: {', '.join(validation['errors'])}")

    return {
        "status": "success" if validation["valid"] else "validation_errors",
        "api_spec": api_spec,
        "package_path": str(package_path),
        "validation": validation,
    }
