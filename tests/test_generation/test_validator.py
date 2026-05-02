import sys
from types import SimpleNamespace

from cli_any_app.generation.validator import _console_script_command, validate_generated_cli


def test_valid_package(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "helpers.py").write_text("VALUE = 1\n")
    (pkg_dir / "cli.py").write_text(
        "import json\n\n"
        "import click\n"
        "from test_app.helpers import VALUE\n\n"
        "@click.group()\n"
        "def cli():\n"
        "    json.dumps(VALUE)\n"
    )
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_rejects_non_stdlib_non_allowlisted_imports(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\nimport rich\nfrom pandas import DataFrame\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)

    assert result["valid"] is False
    assert any(
        "Import not allowed" in error and "rich" in error
        for error in result["errors"]
    )
    assert any(
        "Import not allowed" in error and "pandas" in error
        for error in result["errors"]
    )


def test_missing_files(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    # Missing pyproject.toml and SKILL.md
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)
    assert result["valid"] is False
    assert any("pyproject.toml" in e for e in result["errors"])
    assert any("SKILL.md" in e for e in result["errors"])


def test_syntax_error(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text("[project]\n")
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("def bad syntax here:\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)
    assert result["valid"] is False
    assert any("Syntax error" in e or "parse error" in e for e in result["errors"])


def test_console_script_command_prefers_windows_wrappers(tmp_path, monkeypatch):
    env_dir = tmp_path / "venv"
    scripts_dir = env_dir / "Scripts"
    scripts_dir.mkdir(parents=True)
    wrapper = scripts_dir / "patient-cli.cmd"
    wrapper.write_text("")

    monkeypatch.setattr(sys, "platform", "win32")

    assert _console_script_command(env_dir, "patient-cli") == [str(wrapper)]


def test_rejects_unapproved_build_backend(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text(
        """
[build-system]
requires = ["evil-builder"]
build-backend = "evil.backend"

[project]
name = "test"
""".strip()
    )
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n\n@click.group()\ndef cli(): pass\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)

    assert result["valid"] is False
    assert "Build backend not allowed: evil.backend" in result["errors"]
    assert "Build dependency not allowed: evil-builder" in result["errors"]


def test_rejects_executable_build_hook_files(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "test"
""".strip()
    )
    (pkg / "setup.py").write_text("raise RuntimeError('build hook executed')\n")
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n\n@click.group()\ndef cli(): pass\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)

    assert result["valid"] is False
    assert "Executable build hook not allowed: setup.py" in result["errors"]


def test_rejects_local_build_backend_path(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"
backend-path = ["."]

[project]
name = "test"
""".strip()
    )
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n\n@click.group()\ndef cli(): pass\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)

    assert result["valid"] is False
    assert "Build backend path not allowed" in result["errors"]


def test_smoke_install_uses_restricted_pip_flags(tmp_path, monkeypatch):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "test"
dependencies = ["click>=8.0.0", "httpx>=0.27.0"]

[project.scripts]
test-cli = "test_app.cli:cli"
""".strip()
    )
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n\n@click.group()\ndef cli(): pass\n")
    (pkg_dir / "__init__.py").write_text("")

    builders = []

    class FakeEnvBuilder:
        def __init__(self, *, with_pip: bool, system_site_packages: bool = False):
            self.with_pip = with_pip
            self.system_site_packages = system_site_packages
            builders.append(self)

        def create(self, env_dir):
            bin_dir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
            bin_dir.mkdir(parents=True)
            (bin_dir / ("python.exe" if sys.platform == "win32" else "python")).write_text("")
            (bin_dir / ("test-cli.cmd" if sys.platform == "win32" else "test-cli")).write_text("")

    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("cli_any_app.generation.validator.venv.EnvBuilder", FakeEnvBuilder)
    monkeypatch.setattr("cli_any_app.generation.validator.subprocess.run", fake_run)

    result = validate_generated_cli(pkg, run_smoke=True)

    assert result["valid"] is True
    assert builders[0].with_pip is True
    assert builders[0].system_site_packages is True
    install_args = calls[0]
    assert "--no-build-isolation" in install_args
    assert "--no-deps" in install_args
    assert "--no-index" in install_args


def test_smoke_install_reports_missing_console_script(tmp_path, monkeypatch):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "test"

[project.scripts]
missing-cli = "test_app.cli:cli"
""".strip()
    )
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n\n@click.group()\ndef cli(): pass\n")
    (pkg_dir / "__init__.py").write_text("")

    class FakeEnvBuilder:
        def __init__(self, *, with_pip: bool, system_site_packages: bool = False):
            self.with_pip = with_pip
            self.system_site_packages = system_site_packages

        def create(self, env_dir):
            bin_dir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
            bin_dir.mkdir(parents=True)
            (bin_dir / ("python.exe" if sys.platform == "win32" else "python")).write_text("")

    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr("cli_any_app.generation.validator.venv.EnvBuilder", FakeEnvBuilder)
    monkeypatch.setattr("cli_any_app.generation.validator.subprocess.run", fake_run)

    result = validate_generated_cli(pkg, run_smoke=True)

    assert result["valid"] is False
    assert "Console script not found after install: missing-cli" in result["errors"]
    assert len(calls) == 1
