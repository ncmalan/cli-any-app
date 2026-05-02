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
UNSAFE_BUILD_HOOK_FILES = {"setup.py"}
UNSAFE_IMPORTS = {"subprocess", "socket", "ftplib", "telnetlib", "pickle", "marshal"}
UNSAFE_CALLS = {"eval", "exec", "compile", "__import__"}
SAFE_PROJECT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def validate_generated_cli(package_dir: Path, *, run_smoke: bool = False) -> dict:
    errors = []
    warnings = []
    allowed_import_roots = STDLIB_MODULES | ALLOWED_DEPENDENCIES | _local_import_roots(package_dir)

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

    _validate_generated_build_hooks(package_dir, errors)

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
                _check_ast_safety(tree, cli_module.relative_to(package_dir), errors, allowed_import_roots)
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
        _check_ast_safety(tree, py_file.relative_to(package_dir), errors, allowed_import_roots)

    if run_smoke and not errors:
        _run_isolated_smoke_test(package_dir, errors, warnings)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _local_import_roots(package_dir: Path) -> set[str]:
    roots = {py_file.stem for py_file in package_dir.glob("*.py") if py_file.stem != "__init__"}
    for init_file in package_dir.rglob("__init__.py"):
        if init_file.parent != package_dir:
            roots.add(init_file.parent.name)
    return roots


def _check_ast_safety(
    tree: ast.AST,
    rel_path: Path,
    errors: list[str],
    allowed_import_roots: set[str],
) -> None:
    unsafe_call_names = {name: name for name in UNSAFE_CALLS}
    unsafe_module_aliases: dict[str, str] = {"os": "os", "importlib": "importlib"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import_allowed(alias.name, rel_path, errors, allowed_import_roots)
                root = alias.name.split(".", 1)[0]
                if root in unsafe_module_aliases.values():
                    unsafe_module_aliases[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                _check_import_allowed(node.module, rel_path, errors, allowed_import_roots)
                _track_imported_unsafe_calls(node, unsafe_call_names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _check_unsafe_call(node, rel_path, errors, unsafe_call_names, unsafe_module_aliases)


def _track_imported_unsafe_calls(node: ast.ImportFrom, unsafe_call_names: dict[str, str]) -> None:
    unsafe_members = {
        "os": {"system": "os.system"},
        "importlib": {"import_module": "importlib.import_module"},
    }
    module_members = unsafe_members.get(node.module or "")
    if not module_members:
        return

    for alias in node.names:
        if alias.name == "*":
            for member, canonical_name in module_members.items():
                unsafe_call_names[member] = canonical_name
        elif alias.name in module_members:
            unsafe_call_names[alias.asname or alias.name] = module_members[alias.name]


def _check_unsafe_call(
    node: ast.Call,
    rel_path: Path,
    errors: list[str],
    unsafe_call_names: dict[str, str],
    unsafe_module_aliases: dict[str, str],
) -> None:
    if isinstance(node.func, ast.Name) and node.func.id in unsafe_call_names:
        errors.append(f"Unsafe call in {rel_path}: {unsafe_call_names[node.func.id]}")
    if isinstance(node.func, ast.Attribute):
        owner = node.func.value
        if not isinstance(owner, ast.Name):
            return
        owner_module = unsafe_module_aliases.get(owner.id)
        if owner_module == "os" and node.func.attr == "system":
            errors.append(f"Unsafe call in {rel_path}: os.system")
        if owner_module == "importlib" and node.func.attr == "import_module":
            errors.append(f"Unsafe call in {rel_path}: importlib.import_module")


def _check_import_allowed(
    module_name: str,
    rel_path: Path,
    errors: list[str],
    allowed_import_roots: set[str],
) -> None:
    root = module_name.split(".", 1)[0]
    if root in UNSAFE_IMPORTS:
        errors.append(f"Unsafe import in {rel_path}: {module_name}")
    elif root not in allowed_import_roots:
        errors.append(f"Import not allowed in {rel_path}: {module_name}")


def _validate_generated_build_hooks(package_dir: Path, errors: list[str]) -> None:
    for hook_file in sorted(package_dir.rglob("*")):
        if hook_file.is_file() and hook_file.name in UNSAFE_BUILD_HOOK_FILES:
            errors.append(f"Executable build hook not allowed: {hook_file.relative_to(package_dir)}")


def _validate_build_system(metadata: dict, errors: list[str], *, required: bool = False) -> None:
    build_system = metadata.get("build-system")
    if not build_system:
        if required:
            errors.append("Smoke test requires an explicit build-system")
        return

    if build_system.get("backend-path"):
        errors.append("Build backend path not allowed")

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

        console_script = _console_script_command(env_dir, script_name)
        if not Path(console_script[0]).exists():
            errors.append(f"Console script not found after install: {script_name}")
            return

        try:
            help_run = subprocess.run(
                [*console_script, "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
        except OSError as e:
            errors.append(f"Smoke --help failed to start: {e}")
            return
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
