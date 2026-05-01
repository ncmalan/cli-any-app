import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cli_any_app.generation.generator import generate_cli_package


@pytest.fixture
def api_spec():
    return {
        "app_name": "test-app",
        "base_urls": ["https://api.example.com"],
        "auth": {
            "type": "bearer",
            "obtain_from": "/auth/login",
            "header_name": "Authorization",
            "refresh_endpoint": None,
        },
        "command_groups": [
            {
                "name": "auth",
                "description": "Authentication",
                "commands": [
                    {
                        "name": "login",
                        "description": "Login to the app",
                        "endpoint": {
                            "method": "POST",
                            "path": "/auth/login",
                            "base_url": "https://api.example.com",
                        },
                        "parameters": [
                            {
                                "name": "email",
                                "type": "string",
                                "required": True,
                                "source": "user_input",
                                "description": "Email",
                            }
                        ],
                        "response_fields": ["token"],
                        "requires_auth": False,
                    }
                ],
            }
        ],
        "state_dependencies": [],
    }


@pytest.fixture
def generated_files():
    return {
        "test_app/__init__.py": "",
        "test_app/cli.py": "import click\n\n@click.group()\ndef cli(): pass\n",
        "test_app/api_client.py": "import httpx\n\nclass ApiClient: pass\n",
        "test_app/commands/__init__.py": "",
        "test_app/commands/auth.py": "import click\n\n@click.command()\ndef login(): pass\n",
    }


def _make_mock_client(generated_files):
    """Create a mock Anthropic client that returns code files and SKILL.md."""
    mock_code_content = MagicMock()
    mock_code_content.text = json.dumps(generated_files)
    mock_code_response = MagicMock()
    mock_code_response.content = [mock_code_content]

    mock_skill_content = MagicMock()
    mock_skill_content.text = "# test-app\n\nCLI for test-app."
    mock_skill_response = MagicMock()
    mock_skill_response.content = [mock_skill_content]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[mock_code_response, mock_skill_response]
    )
    return mock_client


async def test_generate_creates_package_structure(
    tmp_path, api_spec, generated_files
):
    with patch(
        "cli_any_app.generation.generator.get_client"
    ) as mock_get_client:
        mock_client = _make_mock_client(generated_files)
        mock_get_client.return_value = mock_client

        result = await generate_cli_package(api_spec, tmp_path)

        assert result.exists()
        assert (result / "pyproject.toml").exists()
        assert (result / "test_app" / "config.py").exists()
        assert (result / "test_app" / "cli.py").exists()
        assert (result / "test_app" / "api_client.py").exists()
        assert (result / "SKILL.md").exists()

        # Verify pyproject.toml content
        pyproject = (result / "pyproject.toml").read_text()
        assert "test-app" in pyproject
        assert "click" in pyproject

        # Verify config.py has base URL
        config = (result / "test_app" / "config.py").read_text()
        assert "api.example.com" in config

        # Verify Claude was called twice (code + skill)
        assert mock_client.messages.create.call_count == 2


async def test_generate_handles_markdown_fenced_response(
    tmp_path, api_spec, generated_files
):
    """Claude sometimes wraps JSON in markdown fences — generator should strip them."""
    with patch(
        "cli_any_app.generation.generator.get_client"
    ) as mock_get_client:
        mock_client = AsyncMock()

        fenced_code = "```json\n" + json.dumps(generated_files) + "\n```"
        mock_code_content = MagicMock()
        mock_code_content.text = fenced_code
        mock_code_response = MagicMock()
        mock_code_response.content = [mock_code_content]

        fenced_skill = "```markdown\n# test-app\n\nCLI for test-app.\n```"
        mock_skill_content = MagicMock()
        mock_skill_content.text = fenced_skill
        mock_skill_response = MagicMock()
        mock_skill_response.content = [mock_skill_content]

        mock_client.messages.create = AsyncMock(
            side_effect=[mock_code_response, mock_skill_response]
        )
        mock_get_client.return_value = mock_client

        result = await generate_cli_package(api_spec, tmp_path)

        assert (result / "test_app" / "cli.py").exists()
        assert (result / "SKILL.md").exists()
        skill = (result / "SKILL.md").read_text()
        assert not skill.startswith("```")


async def test_generate_creates_commands_subdir(
    tmp_path, api_spec, generated_files
):
    """Verify that nested directories like commands/ are created."""
    with patch(
        "cli_any_app.generation.generator.get_client"
    ) as mock_get_client:
        mock_client = _make_mock_client(generated_files)
        mock_get_client.return_value = mock_client

        result = await generate_cli_package(api_spec, tmp_path)

        assert (result / "test_app" / "commands" / "auth.py").exists()
        assert (result / "test_app" / "commands" / "__init__.py").exists()


async def test_generate_no_base_urls(tmp_path, generated_files):
    """When no base_urls provided, config.py should still render."""
    api_spec_no_urls = {
        "app_name": "no-url-app",
        "base_urls": [],
        "auth": {},
        "command_groups": [],
        "state_dependencies": [],
    }

    with patch(
        "cli_any_app.generation.generator.get_client"
    ) as mock_get_client:
        # Adjust generated_files for this package name
        adjusted_files = {
            k.replace("test_app", "no_url_app"): v
            for k, v in generated_files.items()
        }
        mock_client = _make_mock_client(adjusted_files)
        mock_get_client.return_value = mock_client

        result = await generate_cli_package(api_spec_no_urls, tmp_path)

        config = (result / "no_url_app" / "config.py").read_text()
        assert 'BASE_URL = ""' in config
