"""Security guardrails and ADK pre-flight callback hooks for the OKF Spanner Query Agent.

Enforces Rule 11 (Model Armor pre-flight hook) and Rule 14 (Immutability of reference/ directory).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuerySecurityGuardrailError(PermissionError):
    """Raised when a query prompt violates enterprise security or reference immutability policies."""


class QuerySafetyEvaluationResult(BaseModel):
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


def check_query_prompt_security(prompt: str) -> dict[str, Any]:
    """Evaluate prompt for adversarial jailbreaks, SQL/GQL injection directives, or reference mutation attempts."""
    lowered = (prompt or "").lower()
    structural_indicators = (
        ("ignore", "instructions"),
        ("disregard", "instructions"),
        ("system prompt", "override"),
        ("bypass", "security"),
        ("delete all", "files"),
        ("rm -rf", "/"),
        ("drop table", "spanner"),
        ("delete from", "rawsourcedocuments"),
        ("modify", "reference/raw"),
        ("overwrite", "reference/wiki"),
    )

    for tok_a, tok_b in structural_indicators:
        if tok_a in lowered and tok_b in lowered:
            return QuerySafetyEvaluationResult(
                filterMatchState="MATCH_FOUND",
                violation_type="PROMPT_INJECTION_OR_POLICY_VIOLATION",
                matched_pattern=f"{tok_a} ... {tok_b}",
            ).model_dump()

    return QuerySafetyEvaluationResult(
        filterMatchState="NO_MATCH",
        violation_type=None,
    ).model_dump()


def query_agent_before_callback(callback_context: Any) -> Any:
    """ADK Pre-flight security hook executed before query_agent reasoning."""
    prompt = ""
    if hasattr(callback_context, "user_content") and callback_context.user_content:
        parts = getattr(callback_context.user_content, "parts", None) or []
        prompt = " ".join(getattr(p, "text", "") or "" for p in parts)
    elif hasattr(callback_context, "prompt"):
        prompt = callback_context.prompt or ""
    elif isinstance(callback_context, str):
        prompt = callback_context
    elif isinstance(callback_context, dict):
        prompt = callback_context.get("prompt", "")

    check = check_query_prompt_security(prompt)
    if check["filterMatchState"] == "MATCH_FOUND":
        raise QuerySecurityGuardrailError(
            f"Security violation detected: {check['violation_type']}. Operation aborted."
        )

    if isinstance(callback_context, str):
        return callback_context
    return None
