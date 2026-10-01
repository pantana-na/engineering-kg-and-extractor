"""Security guardrails and ADK pre-flight callback hooks.

Implements Rule 11 & Section 1.3: Deterministic interception before agent execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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

