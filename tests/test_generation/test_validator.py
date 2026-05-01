import sys

from cli_any_app.generation.validator import _console_script_command, validate_generated_cli


def test_valid_package(tmp_path):
    pkg = tmp_path / "test-app"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (pkg / "SKILL.md").write_text("# Test\n")
    pkg_dir = pkg / "test_app"
    pkg_dir.mkdir()
    (pkg_dir / "cli.py").write_text("import click\n\n@click.group()\ndef cli(): pass\n")
    (pkg_dir / "__init__.py").write_text("")

    result = validate_generated_cli(pkg)
    assert result["valid"] is True
    assert len(result["errors"]) == 0


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
