"""Claude client over AWS Bedrock, credentialed via Azure Key Vault.

We reuse the exact credential chain the host project already uses
(see C:\\Users\\shayavadan\\Desktop\\config): Azure Key Vault holds the AWS
Bedrock access key / secret / region and the Claude model ids. We fetch those
once at startup and talk to Bedrock directly with boto3 — no agno / whisper /
pgvector dependencies, keeping this app lightweight.

All secrets stay server-side. The frontend never sees a key.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

# ---- Azure Key Vault config
# These values should be kept in backend/.env or in the environment, not in source.
KV_CLIENT_ID = os.getenv("KV_CLIENT_ID")
KV_CLIENT_SECRET = os.getenv("KV_CLIENT_SECRET")
KV_TENANT_ID = os.getenv("KV_TENANT_ID")
KV_URL = os.getenv("KV_URL")


def _required_env(name: str, value: Optional[str]) -> str:
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            "Create backend/.env from backend/.env.example or set it in the environment."
        )
    return value


# Secret names (from AWSClaudeConfig in the host project). The Key Vault entries
# carry the Bedrock account creds + region; we only need the AWS keys from here,
# since the original Sonnet-3.7 model id stored there has been retired by AWS.
SM_AWS_ACCESS_KEY_ID = "claude-3-7-sonnet-access-key-id"
SM_AWS_SECRET_ACCESS_KEY = "claude-3-7-sonnet-secret-access-key"
SM_REGION_NAME = "claude-3-7-sonnet-region-name"

# Current models available on this Bedrock account (verified live). These use
# cross-region inference profiles (the "us." prefix is required).
#   FAST   - bulk per-node narration, Q&A answers   (cheap, quick, plenty smart)
#   SMART  - tour-sequence reasoning, hard questions (deeper reasoning)
MODEL_FAST = os.getenv("CLAUDE_FAST_MODEL", "us.anthropic.claude-sonnet-4-6")
MODEL_SMART = os.getenv("CLAUDE_SMART_MODEL", "us.anthropic.claude-opus-4-8")

# Models that no longer accept the `temperature` parameter (newer Opus tiers).
_NO_TEMPERATURE_MODELS = ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6")

# Anthropic Bedrock invoke version.
ANTHROPIC_BEDROCK_VERSION = "bedrock-2023-05-31"


@dataclass
class ClaudeConfig:
    access_key: str
    secret_key: str
    region: str


def _fetch_secret(secret_name: str) -> str:
    from azure.identity import ClientSecretCredential
    from azure.keyvault.secrets import SecretClient

    credential = ClientSecretCredential(
        _required_env("KV_TENANT_ID", KV_TENANT_ID),
        _required_env("KV_CLIENT_ID", KV_CLIENT_ID),
        _required_env("KV_CLIENT_SECRET", KV_CLIENT_SECRET),
    )
    client = SecretClient(
        vault_url=_required_env("KV_URL", KV_URL),
        credential=credential,
    )
    return client.get_secret(secret_name).value


@lru_cache(maxsize=1)
def load_config() -> ClaudeConfig:
    """Load Bedrock creds from Key Vault (cached for process life)."""
    return ClaudeConfig(
        access_key=_fetch_secret(SM_AWS_ACCESS_KEY_ID),
        secret_key=_fetch_secret(SM_AWS_SECRET_ACCESS_KEY),
        region=_fetch_secret(SM_REGION_NAME),
    )


@lru_cache(maxsize=1)
def _bedrock_client():
    import boto3
    cfg = load_config()
    return boto3.client(
        "bedrock-runtime",
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        region_name=cfg.region,
    )


def call_claude(
    system: str,
    messages: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Invoke Claude on Bedrock. Returns the parsed response body.

    `model` defaults to MODEL_FAST (Sonnet). Pass MODEL_SMART for deeper
    reasoning. `messages` uses the Anthropic Messages format:
        [{"role": "user", "content": "..."}]
    Returns the full response dict; callers pull out text or tool_use blocks.
    """
    client = _bedrock_client()
    model_id = model or MODEL_FAST

    body: Dict[str, Any] = {
        "anthropic_version": ANTHROPIC_BEDROCK_VERSION,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    # Some newer Opus tiers reject `temperature` entirely.
    if not any(tag in model_id for tag in _NO_TEMPERATURE_MODELS):
        body["temperature"] = temperature
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice

    resp = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())


def extract_text(response: Dict[str, Any]) -> str:
    """Concatenate all text blocks from a Claude response."""
    parts = []
    for block in response.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def extract_tool_use(response: Dict[str, Any], name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the first tool_use block (optionally matching a tool name)."""
    for block in response.get("content", []):
        if block.get("type") == "tool_use" and (name is None or block.get("name") == name):
            return block
    return None
