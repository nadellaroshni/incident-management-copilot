"""Checks an investigation result against the output contract and the evidence it was built from."""

from __future__ import annotations

RISK_LEVELS = {"low", "medium", "high"}


def validate(output: dict, allowed_labels: set[str], retrieved_ids: set[str], logs: list[dict]) -> list[str]:
    """Return a list of problems. An empty list means the output is acceptable."""
    errors: list[str] = []
    if not isinstance(output, dict):
        return ["output is not a JSON object"]

    if output.get("insufficient_evidence") is True:
        return []  # an honest "not enough evidence" is always acceptable

    root = output.get("root_cause") or {}
    if root.get("label") not in allowed_labels:
        errors.append(f"root_cause.label {root.get('label')!r} is not a known failure mode")
    confidence = root.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("root_cause.confidence must be a number between 0 and 1")

    for citation in output.get("citations", []):
        if citation.get("chunk_id") not in retrieved_ids:
            errors.append(f"citation {citation.get('chunk_id')!r} was never retrieved")

    log_text = "\n".join(line.get("msg", "") for line in logs)
    for item in output.get("evidence", []):
        if item.get("quote", "") not in log_text:
            errors.append(f"evidence quote not found in logs: {item.get('quote', '')[:60]!r}")

    for step in output.get("remediation", []):
        if step.get("dry_run") is not True:
            errors.append("remediation steps must be dry-run")
        if step.get("risk") not in RISK_LEVELS:
            errors.append(f"remediation risk {step.get('risk')!r} is not low, medium or high")

    return errors
