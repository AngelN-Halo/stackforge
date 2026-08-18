from __future__ import annotations

import json

import httpx

from app.config import settings
from app.schemas import AIResponse


SYSTEM_PROMPT = """You are StackForge, an internal AI app builder. Return JSON only.
Schema:
{
  "assistant_explanation": string,
  "files": [{"path": string, "content": string, "action": "create|update|delete"}],
  "commands": [string],
  "notes": [string]
}
Rules:
- Every file object should include action. If uncertain, use "update".
- Use project-relative POSIX paths only.
- Return complete replacement content for create/update operations.
- Never modify .git, .stackforge, stackforge.json, secrets, or dependency/build output folders.
- Commands are suggestions only and are never executed automatically.
- Do not output markdown, code fences, or unknown JSON fields."""


async def generate_change_plan(description: str, tree: dict, context_files: dict[str, str], user_message: str) -> AIResponse:
    prompt = {
        "project_description": description,
        "current_file_tree": tree,
        "relevant_file_contents": context_files,
        "user_request": user_message,
        "expected_output_format": "structured JSON",
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(prompt)},
    ]

    payload = {
        "model": settings.default_model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }

    headers = {}
    if settings.litellm_api_key:
        headers["Authorization"] = f"Bearer {settings.litellm_api_key}"

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(f"{settings.litellm_base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

    data = json.loads(content)
    return AIResponse(**data)
