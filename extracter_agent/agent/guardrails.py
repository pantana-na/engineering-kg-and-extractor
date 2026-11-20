"""Security guardrails and 4-point SAIF 2.0 ADK callback hooks.

Implements Rule 11 & SAIF 2.0 (SPEC-20261120-UNIFIED-WORKBENCH-V2 Section 3.1):
  1. before_agent_callback: Direct Prompt Injection (`PIJ`) & Policy screening
  2. before_model_callback: Pre-model PII/secret redaction (`EDH`) & DMS turn budget enforcement
  3. after_tool_callback: Indirect Prompt Injection (`PIJ`) screening on untrusted tool/document payloads
  4. after_model_callback: Outbound DLP scrubbing (`SDD`) & Markdown image/URL allowlist (`IMO`)
"""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field

MAX_AGENT_TOOL_CALLS: int = int(os.getenv("MAX_AGENT_TOOL_CALLS", "12"))

_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("API_KEY", re.compile(r"\bAIza[0-9A-Za-z\-_]{35,45}\b")),
    ("BEARER_TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b", re.IGNORECASE)),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("CARD_PAN", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
)

_MARKDOWN_IMG_EXFIL_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_INDIRECT_PIJ_LINE_RE = re.compile(
    r"(?im)^.*(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|disregard\s+system\s+prompt|"
    r"exfiltrate\s+to\s+https?://|override\s+system\s+instructions).*$"
)


def scrub_sensitive_dlp(text: str) -> str:
    """Deterministically redact raw secrets/tokens/PANs before LLM context or outbound response (`EDH`/`SDD`)."""
    if not text:
        return text
    cleaned = text
    for label, pattern in _SENSITIVE_PATTERNS:
        if label == "CARD_PAN":
            # Avoid redacting engineering drawing codes or hyphenated tags; only match pure 13-16 digit PAN runs
            cleaned = re.sub(
                r"(?<![A-Za-z0-9\-])(?:\d{4}[ -]?){3}\d{1,4}(?![A-Za-z0-9\-])",
                f"[REDACTED_{label}]",
                cleaned,
            )
        else:
            cleaned = pattern.sub(f"[REDACTED_{label}]", cleaned)
    return cleaned


def sanitize_outbound_markdown_urls(text: str, *, allowed_hosts: tuple[str, ...] = ()) -> str:
    """Strip unauthorized external Markdown image exfiltration tags (`![...](https://...)`) (`SAIF IMO`)."""
    if not text:
        return text

    def _replace_img(match: re.Match[str]) -> str:
        alt_text = match.group(1) or "blocked-image"
        url = match.group(2)
        for host in allowed_hosts:
            if host and url.lower().startswith(f"https://{host.lower()}/"):
                return match.group(0)
        return f"[BLOCKED_EXTERNAL_IMAGE: {alt_text}]"

    return _MARKDOWN_IMG_EXFIL_RE.sub(_replace_img, text)


def sanitize_untrusted_tool_payload(payload: Any) -> Any:
    """Quarantine Indirect Prompt Injection directives embedded inside untrusted document/tool payloads (`PIJ`)."""
    if isinstance(payload, str):
        return _INDIRECT_PIJ_LINE_RE.sub("[QUARANTINED_INDIRECT_PROMPT_INJECTION]", payload)
    if isinstance(payload, list):
        return [sanitize_untrusted_tool_payload(item) for item in payload]
    if isinstance(payload, dict):
        return {k: sanitize_untrusted_tool_payload(v) for k, v in payload.items()}
    return payload


def before_model_callback(callback_context: Any, llm_request: Any = None) -> Any:
    """SAIF 2.0 Pre-Model Hook: scrub raw PII/secrets and enforce per-session tool/turn budget (`DMS`)."""
    state = getattr(callback_context, "state", None)
    if isinstance(state, dict):
        turns = int(state.get("_llm_call_count", 0)) + 1
        state["_llm_call_count"] = turns
        max_calls = int(os.getenv("MAX_AGENT_TOOL_CALLS", str(MAX_AGENT_TOOL_CALLS))) + 4
        if turns > max_calls:
            raise SecurityGuardrailError(
                f"Execution budget exceeded (max LLM calls={max_calls}). Operation stopped safely (SAIF DMS)."
            )

    contents = getattr(llm_request, "contents", None)
    if contents:
        for content in contents:
            parts = getattr(content, "parts", None) or []
            for part in parts:
                if getattr(part, "text", None):
                    part.text = scrub_sensitive_dlp(part.text)
    return None


def after_tool_callback(
    tool: Any = None,
    args: dict[str, Any] | None = None,
    tool_context: Any = None,
    tool_response: Any = None,
) -> Any:
    """SAIF 2.0 Post-Tool Hook: screen untrusted PDF/RAG/tool outputs for Indirect Prompt Injection (`PIJ`)."""
    state = getattr(tool_context, "state", None)
    if isinstance(state, dict):
        tool_calls = int(state.get("_tool_call_count", 0)) + 1
        state["_tool_call_count"] = tool_calls
        max_tools = int(os.getenv("MAX_AGENT_TOOL_CALLS", str(MAX_AGENT_TOOL_CALLS)))
        if tool_calls > max_tools:
            raise SecurityGuardrailError(
                f"Tool execution budget exceeded (max tool calls={max_tools}). Operation stopped safely (SAIF DMS)."
            )

    if tool_response is None:
        return None
    return sanitize_untrusted_tool_payload(tool_response)


def after_model_callback(callback_context: Any, llm_response: Any = None) -> Any:
    """SAIF 2.0 Post-Model Hook: scrub outbound PII/secrets (`SDD`) and block Markdown image exfiltration (`IMO`)."""
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None) or []
    for part in parts:
        if getattr(part, "text", None):
            part.text = sanitize_outbound_markdown_urls(scrub_sensitive_dlp(part.text))
    return None


class SecurityGuardrailError(PermissionError):
    """Raised when a prompt violates enterprise security policies or injection checks."""


class SafetyEvaluationResult(BaseModel):
    """Structured safety assessment result for pre-flight guardrail evaluation."""

    filterMatchState: str = Field(
        default="NO_MATCH", description="MATCH_FOUND or NO_MATCH"
    )
    violation_type: str | None = Field(
        default=None, description="Detected violation category if unsafe"
    )
    matched_pattern: str | None = Field(
        default=None, description="Matched adversarial directive or explanation"
    )


def check_prompt_security(prompt: str) -> dict[str, Any]:
    """Evaluate prompt for adversarial jailbreaks, command injections, or policy violations.

    Combines structural directive interception with structured SafetyEvaluationResult validation.
    """
    lowered = prompt.lower()
    structural_indicators = (
        ("ignore", "instructions"),
        ("disregard", "instructions"),
        ("system prompt", "override"),
        ("bypass", "security"),
        ("delete all", "files"),
        ("rm -rf", "/"),
    )

    for tok_a, tok_b in structural_indicators:
        if tok_a in lowered and tok_b in lowered:
            return SafetyEvaluationResult(
                filterMatchState="MATCH_FOUND",
                violation_type="PROMPT_INJECTION",
                matched_pattern=f"{tok_a} ... {tok_b}",
            ).model_dump()

    return SafetyEvaluationResult(
        filterMatchState="NO_MATCH",
        violation_type=None,
    ).model_dump()


def before_agent_callback(callback_context: Any) -> Any:
    """ADK Pre-flight security hook executed before model reasoning.

    Aborts immediately if adversarial prompt injection is detected.
    """
    prompt = ""
    if hasattr(callback_context, "prompt"):
        prompt = callback_context.prompt or ""
    elif isinstance(callback_context, str):
        prompt = callback_context
    elif isinstance(callback_context, dict):
        prompt = callback_context.get("prompt", "")

    check = check_prompt_security(prompt)
    if check["filterMatchState"] == "MATCH_FOUND":
        raise SecurityGuardrailError(
            f"Security violation detected: {check['violation_type']}. Operation aborted."
        )

    if isinstance(callback_context, str):
        return callback_context
    return None

