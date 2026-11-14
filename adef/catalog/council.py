"""Default review council: three reviewers, three lenses, three different model providers."""
from __future__ import annotations

DEFAULT_COUNCIL: dict = {
    "enabled": True, "max_revisions": 1,
    "members": [
        {"name": "Accuracy reviewer", "provider_id": "anthropic", "model": "claude-opus-5-5",
         "lens": "Correctness and completeness: is everything the stage must deliver present, internally consistent, "
                 "traceable to its inputs, and free of invented facts?"},
        {"name": "Risk reviewer", "provider_id": "openai", "model": "gpt-5.6-sol",
         "lens": "Risk, compliance and guardrails: data classification and privacy, security, cost, reversibility, "
                 "and anything that breaks a stated rule or control."},
        {"name": "Handover reviewer", "provider_id": "google-gemini", "model": "gemini-4-argon",
         "lens": "Readiness for handover: can the next agent and the human approver act on this without asking "
                 "questions? Are open questions, assumptions and evidence stated clearly?"},
    ],
}
