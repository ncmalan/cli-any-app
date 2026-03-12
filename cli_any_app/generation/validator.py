import py_compile
import subprocess
from pathlib import Path


def validate_generated_cli(package_dir: Path) -> dict:
    errors = []
    warnings = []

    # Check all .py files compile
    for py_file in package_dir.rglob("*.py"):
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"Syntax error in {py_file.name}: {e}")

    # Check required files exist
    required = ["pyproject.toml", "SKILL.md"]
    for f in required:
        if not (package_dir / f).exists():
            errors.append(f"Missing required file: {f}")

    # Try to parse the CLI module
    cli_name = package_dir.name.replace("-", "_")
    cli_module = package_dir / cli_name / "cli.py"
    if cli_module.exists():
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open('{cli_module}').read())"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            errors.append(f"CLI module parse error: {result.stderr}")
    else:
        errors.append("cli.py not found in package")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
