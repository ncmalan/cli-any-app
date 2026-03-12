from pathlib import Path
from cli_any_app.generation.normalizer import normalize_session_data
from cli_any_app.generation.redactor import redact_sensitive_data
from cli_any_app.generation.analyzer import analyze_api_surface
from cli_any_app.generation.generator import generate_cli_package
from cli_any_app.generation.validator import validate_generated_cli
from cli_any_app.config import settings


async def run_pipeline(session_data: dict, session_id: str) -> dict:
    output_dir = settings.generated_dir

    # Step 1: Normalize
    normalized = normalize_session_data(session_data)

    # Step 2: Redact & Analyze
    redacted = redact_sensitive_data(normalized)
    api_spec = await analyze_api_surface(redacted)

    # Step 3: Generate
    package_path = await generate_cli_package(api_spec, output_dir)

    # Step 4: Validate
    validation = validate_generated_cli(package_path)

    return {
        "status": "success" if validation["valid"] else "validation_errors",
        "api_spec": api_spec,
        "package_path": str(package_path),
        "validation": validation,
    }
