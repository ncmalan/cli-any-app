import ast
import py_compile
import re
import subprocess
import sys
import tempfile
import tomllib
import venv
from pathlib import Path

ALLOWED_DEPENDENCIES = {"click", "httpx"}
ALLOWED_BUILD_BACKENDS = {"setuptools.build_meta"}
ALLOWED_BUILD_DEPENDENCIES = {"setuptools", "wheel"}
UNSAFE_IMPORTS = {"subprocess", "socket", "ftplib", "telnetlib", "pickle", "marshal"}
UNSAFE_CALLS = {"eval", "exec", "compile", "__import__"}
SAFE_PROJECT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def validate_generated_cli(package_dir: Path, *, run_smoke: bool = False) -> dict:
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

    pyproject = package_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            metadata = tomllib.loads(pyproject.read_text())
            project = metadata.get("project", {})
            name = project.get("name", "")
            if not SAFE_PROJECT_NAME.match(name):
                errors.append(f"Unsafe project name: {name}")
            _validate_build_system(metadata, errors)
            for dep in project.get("dependencies", []):
                dep_name = re.split(r"[<>=!~; \[]", dep, maxsplit=1)[0].lower()
                if dep_name and dep_name not in ALLOWED_DEPENDENCIES:
                    errors.append(f"Dependency not allowed: {dep_name}")
        except tomllib.TOMLDecodeError as e:
            errors.append(f"Invalid pyproject.toml: {e}")

    # Find cli.py anywhere in the package
    cli_modules = list(package_dir.rglob("cli.py"))
    if cli_modules:
        for cli_module in cli_modules:
            try:
                tree = ast.parse(cli_module.read_text())
                _check_ast_safety(tree, cli_module.relative_to(package_dir), errors)
            except SyntaxError as e:
                errors.append(f"CLI module parse error in {cli_module.relative_to(package_dir)}: {e}")
    else:
        errors.append("cli.py not found in package")

    for py_file in package_dir.rglob("*.py"):
        if py_file.name == "cli.py":
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        _check_ast_safety(tree, py_file.relative_to(package_dir), errors)

    if run_smoke and not errors:
        _run_isolated_smoke_test(package_dir, errors, warnings)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _check_ast_safety(tree: ast.AST, rel_path: Path, errors: list[str]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in UNSAFE_IMPORTS:
                    errors.append(f"Unsafe import in {rel_path}: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in UNSAFE_IMPORTS:
                errors.append(f"Unsafe import in {rel_path}: {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in UNSAFE_CALLS:
                errors.append(f"Unsafe call in {rel_path}: {node.func.id}")
            if isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if isinstance(owner, ast.Name) and owner.id == "os" and node.func.attr == "system":
                    errors.append(f"Unsafe call in {rel_path}: os.system")


def _validate_build_system(metadata: dict, errors: list[str], *, required: bool = False) -> None:
    build_system = metadata.get("build-system")
    if not build_system:
        if required:
            errors.append("Smoke test requires an explicit build-system")
        return

    backend = build_system.get("build-backend", "")
    if backend not in ALLOWED_BUILD_BACKENDS:
        errors.append(f"Build backend not allowed: {backend or 'missing'}")

    for requirement in build_system.get("requires", []):
        dep_name = re.split(r"[<>=!~; \[]", requirement, maxsplit=1)[0].lower()
        if dep_name and dep_name not in ALLOWED_BUILD_DEPENDENCIES:
            errors.append(f"Build dependency not allowed: {dep_name}")


def _run_isolated_smoke_test(package_dir: Path, errors: list[str], warnings: list[str]) -> None:
    pyproject = package_dir / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text())
    _validate_build_system(metadata, errors, required=True)
    if errors:
        return

    scripts = metadata.get("project", {}).get("scripts", {})
    if not scripts:
        warnings.append("Smoke test skipped: no console script declared")
        return
    script_name = next(iter(scripts))

    with tempfile.TemporaryDirectory(prefix="cli-any-app-validate-") as tmp:
        env_dir = Path(tmp) / "venv"
        # Dependencies are allowlisted before this point; expose the host environment so
        # --no-deps/--no-index smoke tests can import them without network access.
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env_dir)
        python = env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

        install = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-build-isolation",
                "--no-deps",
                "--no-index",
                str(package_dir),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
        if install.returncode != 0:
            errors.append(f"Smoke install failed: {install.stdout[-1000:]}")
            return

        help_run = subprocess.run(
            [*_console_script_command(env_dir, script_name), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        if help_run.returncode != 0:
            errors.append(f"Smoke --help failed: {help_run.stdout[-1000:]}")


def _console_script_command(env_dir: Path, script_name: str) -> list[str]:
    if sys.platform != "win32":
        return [str(env_dir / "bin" / script_name)]

    scripts_dir = env_dir / "Scripts"
    candidates = [
        scripts_dir / f"{script_name}.exe",
        scripts_dir / f"{script_name}.cmd",
        scripts_dir / f"{script_name}.bat",
        scripts_dir / script_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]
    return [str(candidates[0])]
