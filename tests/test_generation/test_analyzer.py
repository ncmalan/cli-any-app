import json

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from cli_any_app.generation.analyzer import analyze_api_surface


@pytest.fixture
def sample_normalized_data():
    return {
        "app": "test-app",
        "flows": [{
            "label": "login",
            "requests": [{
                "method": "POST",
                "base_url": "https://api.example.com",
                "path": "/v1/auth/login",
                "query": "",
                "request_headers": {"Content-Type": "application/json"},
                "request_body": {"email": "<REDACTED>", "password": "<REDACTED>"},
                "status_code": 200,
                "response_headers": {},
                "response_body": {"token": "<REDACTED_TOKEN>", "user": {"id": 1}},
            }],
        }],
        "endpoint_patterns": {"/v1/auth/login": ["/v1/auth/login"]},
    }


async def test_analyze_calls_claude_and_returns_spec(sample_normalized_data):
    mock_spec = {
        "app_name": "test-app",
        "base_urls": ["https://api.example.com"],
        "auth": {
            "type": "bearer",
            "obtain_from": "/v1/auth/login",
            "header_name": "Authorization",
            "refresh_endpoint": None,
        },
        "command_groups": [{
            "name": "auth",
            "description": "Authentication",
            "commands": [{
                "name": "login",
                "description": "Login",
                "endpoint": {
                    "method": "POST",
                    "path": "/v1/auth/login",
                    "base_url": "https://api.example.com",
                },
                "parameters": [
                    {"name": "email", "type": "string", "required": True, "source": "user_input", "description": "Email"},
                    {"name": "password", "type": "string", "required": True, "source": "user_input", "description": "Password"},
                ],
                "response_fields": ["token"],
                "requires_auth": False,
            }],
        }],
        "state_dependencies": [],
    }

    mock_content = MagicMock()
    mock_content.text = json.dumps(mock_spec)
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with patch("cli_any_app.generation.analyzer.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await analyze_api_surface(sample_normalized_data)

        assert result["app_name"] == "test-app"
        assert result["auth"]["type"] == "bearer"
        assert len(result["command_groups"]) == 1
        assert result["command_groups"][0]["name"] == "auth"
        mock_client.messages.create.assert_called_once()


async def test_analyze_handles_markdown_fenced_response(sample_normalized_data):
    mock_spec = {
        "app_name": "test-app",
        "base_urls": [],
        "auth": {"type": "none"},
        "command_groups": [],
        "state_dependencies": [],
    }
    fenced = f"```json\n{json.dumps(mock_spec)}\n```"

    mock_content = MagicMock()
    mock_content.text = fenced
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with patch("cli_any_app.generation.analyzer.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await analyze_api_surface(sample_normalized_data)
        assert result["app_name"] == "test-app"
