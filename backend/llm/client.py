"""Foundry client using Azure OpenAI / Foundry models.

This module supports Azure Foundry chat model calls only. It does not use any
legacy Claude or Bedrock APIs. The model endpoint and key must be provided
through environment variables in backend/.env or the process environment.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

try:
    from azure.ai.openai import OpenAIClient
    from azure.core.credentials import AzureKeyCredential
except ImportError:  # pragma: no cover
    OpenAIClient = None
    AzureKeyCredential = None

FOUNDRY_ENDPOINT = os.getenv("AZURE_FOUNDRY_ENDPOINT")
FOUNDRY_API_KEY = os.getenv("AZURE_FOUNDRY_KEY")
FOUNDRY_CHAT_MODEL = os.getenv("AZURE_FOUNDRY_CHAT_MODEL", "gpt-35-turbo-foundry")


def _required_env(name: str, value: Optional[str]) -> str:
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            "Create backend/.env from backend/.env.example or set it in the environment."
        )
    return value


@lru_cache(maxsize=1)
def _openai_client() -> "OpenAIClient":
    if OpenAIClient is None or AzureKeyCredential is None:
        raise RuntimeError(
            "The azure-ai-openai package is required to use Azure Foundry models. "
            "Install it with `pip install azure-ai-openai`."
        )
    endpoint = _required_env("AZURE_FOUNDRY_ENDPOINT", FOUNDRY_ENDPOINT)
    key = _required_env("AZURE_FOUNDRY_KEY", FOUNDRY_API_KEY)
    return OpenAIClient(endpoint, AzureKeyCredential(key))


def call_model(
    system: str,
    messages: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """Invoke an Azure Foundry chat model and return a normalized response."""
    client = _openai_client()
    model_id = model or FOUNDRY_CHAT_MODEL
    if not model_id:
        raise RuntimeError(
            "Missing Azure Foundry model name. Set AZURE_FOUNDRY_CHAT_MODEL in backend/.env."
        )

    response = client.get_chat_completions(
        model=model_id,
        messages=[{"role": "system", "content": system}] + messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    content = "".join(
        choice.message.content
        for choice in response.choices
        if choice.message and choice.message.content
    )
    return {"content": [{"type": "text", "text": content}], "raw": response}


def extract_text(response: Any) -> str:
    """Extract plain text from the normalized response."""
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict) and "text" in response:
        return str(response["text"]).strip()
    parts = []
    for block in response.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()
