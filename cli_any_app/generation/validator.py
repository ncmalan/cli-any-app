import ast
import py_compile
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

    # Find cli.py anywhere in the package
    cli_modules = list(package_dir.rglob("cli.py"))
    if cli_modules:
        for cli_module in cli_modules:
            try:
                ast.parse(cli_module.read_text())
            except SyntaxError as e:
                errors.append(f"CLI module parse error in {cli_module.relative_to(package_dir)}: {e}")
    else:
        errors.append("cli.py not found in package")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
