"""Lifecycle stages, owners, gates and handoff routing (BUILD_SPEC sections 4 and 5)."""
from __future__ import annotations

STAGES: list[dict] = [
    {"key": "intake", "label": "Intake", "agent": "adef-orchestrator", "folder": "00-intake", "gates": ["G0"],
     "next_agent": "adef-intent-requirements", "envelope_stage": "intake"},
    {"key": "requirements", "label": "Requirements", "agent": "adef-intent-requirements", "folder": "01-requirements",
     "gates": ["G1"], "next_agent": "adef-source-target-mapping", "envelope_stage": "requirements"},
    {"key": "mapping", "label": "Mapping", "agent": "adef-source-target-mapping", "folder": "02-mapping", "gates": ["G2"],
     "next_agent": "adef-solution-design", "envelope_stage": "mapping"},
    {"key": "design", "label": "Design", "agent": "adef-solution-design", "folder": "03-design", "gates": ["G3"],
     "next_agent": "adef-pipeline-build", "envelope_stage": "design"},
    {"key": "build", "label": "Build", "agent": "adef-pipeline-build", "folder": "04-build", "gates": ["G4"],
     "next_agent": "adef-test-quality", "envelope_stage": "build"},
    {"key": "test", "label": "Test", "agent": "adef-test-quality", "folder": "05-test", "gates": ["G5"],
     "next_agent": "adef-release-deploy", "envelope_stage": "test"},
    {"key": "release", "label": "Release", "agent": "adef-release-deploy", "folder": "06-release", "gates": ["G6a", "G6b"],
     "next_agent": "adef-operations-observability", "envelope_stage": "release"},
    {"key": "operations", "label": "Operations", "agent": "adef-operations-observability", "folder": "07-operations",
     "gates": ["G7"], "next_agent": "adef-data-consumption", "envelope_stage": "operations"},
    {"key": "consumption", "label": "Consumption", "agent": "adef-data-consumption", "folder": "08-consumption",
     "gates": ["G8"], "next_agent": "adef-orchestrator", "envelope_stage": "consumption"},
    {"key": "assembly", "label": "Delivery pack", "agent": "adef-orchestrator", "folder": "final", "gates": [],
     "next_agent": "human", "envelope_stage": "assembly"},
]
STAGE_KEYS = [s["key"] for s in STAGES]
GATE_LABELS = {"G0": "Scope, stack, budget", "G1": "Requirements baseline", "G2": "Source-to-target mapping",
               "G3": "Logical + physical design and cost", "G4": "Merge to protected branch",
               "G5": "Test evidence / release readiness", "G6a": "Promote to shared environment",
               "G6b": "Promote to production", "G7": "Operational change and pre-approved actions",
               "G8": "Publication to consumers"}


def stage(key: str) -> dict:
    return next(s for s in STAGES if s["key"] == key)


def index(key: str) -> int:
    return STAGE_KEYS.index(key)


def previous_gate(key: str) -> str | None:
    i = index(key)
    if i == 0:
        return None
    return STAGES[i - 1]["gates"][-1] if STAGES[i - 1]["gates"] else None
