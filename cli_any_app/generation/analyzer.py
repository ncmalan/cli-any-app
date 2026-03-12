import json

import anthropic

from cli_any_app.config import settings

ANALYSIS_PROMPT = """You are an expert API reverse engineer. Analyze the following captured network trace from a mobile app and produce a structured API specification.

The trace was captured via mitmproxy while a human used the "{app}" mobile app. Each "flow" represents a labeled user action (e.g., "login", "search", "add to cart").

Produce a JSON response with this structure:
{{
  "app_name": "{app}",
  "base_urls": ["list of base API URLs observed"],
  "auth": {{
    "type": "bearer|cookie|api_key|none",
    "obtain_from": "endpoint path that returns the token, or null",
    "header_name": "Authorization or custom header name",
    "refresh_endpoint": "endpoint for token refresh, or null"
  }},
  "command_groups": [
    {{
      "name": "group name for CLI (e.g., auth, restaurant, cart)",
      "description": "what this group does",
      "commands": [
        {{
          "name": "command name (e.g., login, search, add)",
          "description": "what this command does",
          "endpoint": {{
            "method": "POST",
            "path": "/v1/auth/login",
            "base_url": "https://api.example.com"
          }},
          "parameters": [
            {{
              "name": "param_name",
              "type": "string|int|float|bool",
              "required": true,
              "source": "user_input|previous_response|config",
              "description": "what this parameter is"
            }}
          ],
          "response_fields": ["list of key response fields"],
          "requires_auth": true
        }}
      ]
    }}
  ],
  "state_dependencies": [
    {{"command": "cart.add", "requires": ["auth.login", "restaurant.menu"]}}
  ]
}}

Here is the captured trace:

{trace}

Respond with ONLY the JSON, no markdown fences or explanation."""


def get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def analyze_api_surface(normalized_data: dict) -> dict:
    client = get_client()
    prompt = ANALYSIS_PROMPT.format(
        app=normalized_data["app"],
        trace=json.dumps(normalized_data, indent=2),
    )
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)
