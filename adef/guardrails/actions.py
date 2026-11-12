"""Pre-tool-call hook: classify every action A0-A4 and block what is not approved.

This is the enforcement layer from BUILD_SPEC section 6. Stage code never performs a
side effect directly; it calls `ActionGuard.execute(...)` which classifies, checks the
approval records, logs before and after, and either runs the callable or raises.
"""
from __future__ import annotations

from typing import Any, Callable

# action -> (class, gate that must be approved, per-action approval needed)
ACTION_TABLE: dict[str, tuple[str, str | None, bool]] = {
    "read_metadata": ("A0", None, False),
    "profile_source": ("A0", None, False),
    "read_ticket": ("A0", None, False),
    "write_artifact": ("A1", None, False),
    "create_branch": ("A1", None, False),
    "commit_feature_branch": ("A1", None, False),
    "run_sandbox_tests": ("A1", None, False),
    "open_pull_request": ("A2", None, False),
    "merge_protected_branch": ("A2", "G4", False),
    "deploy_shared": ("A2", "G6a", False),
    "deploy_production": ("A3", "G6b", True),
    "publish_data_product": ("A3", "G8", True),
    "operational_change": ("A3", "G7", True),
    "rollback_rehearsal": ("A1", None, False),
    "drop_object": ("A3", None, True),
    "grant_access": ("A3", None, True),
    "send_external": ("A3", None, True),
    # A4 - never allowed
    "force_push": ("A4", None, False),
    "push_protected_branch_direct": ("A4", None, False),
    "read_secret_value": ("A4", None, False),
    "disable_audit": ("A4", None, False),
    "cross_client_copy": ("A4", None, False),
    "deploy_untested_commit": ("A4", None, False),
    "lower_quality_threshold": ("A4", None, False),
    "read_restricted_values": ("A4", None, False),
    "rerun_failed_job": ("A3", "G7", True),
    "skip_gate": ("A4", None, False),
}


class GuardrailBlocked(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


def classify(action: str) -> tuple[str, str | None, bool]:
    # Unknown actions default to A3 (adapter contract section 9).
    return ACTION_TABLE.get(action, ("A3", None, True))


class ActionGuard:
    def __init__(self, workspace):
        self.ws = workspace

    def execute(self, agent: str, action: str, target: str, fn: Callable[[], Any] | None = None,
                justification: str = "", per_action_approval_id: str | None = None) -> Any:
        cls, gate, needs_per_action = classify(action)
        entry = {"agent": agent, "action": action, "class": cls, "target": target, "justification": justification}
        if cls == "A4":
            self.ws.log_action({**entry, "phase": "blocked", "rule": "A4-prohibited"})
            raise GuardrailBlocked("A4-prohibited", f"`{action}` is a prohibited (A4) action and is never executed.")
        if gate and not self.ws.gate_passed(gate):
            self.ws.log_action({**entry, "phase": "blocked", "rule": f"gate-{gate}-not-approved"})
            raise GuardrailBlocked(f"gate-{gate}", f"`{action}` needs gate {gate} approved for the current artifact hashes.")
        if needs_per_action and cls == "A3" and not per_action_approval_id:
            self.ws.log_action({**entry, "phase": "blocked", "rule": "A3-needs-per-action-approval"})
            raise GuardrailBlocked("A3-per-action", f"`{action}` is A3 and needs its own explicit approval.")
        if cls in ("A2", "A3"):
            self.ws.log_action({**entry, "phase": "before", "approval_id": per_action_approval_id})
        result = fn() if fn else None
        self.ws.log_action({**entry, "phase": "after" if cls in ("A2", "A3") else "done",
                            "result": str(result)[:200] if result is not None else "ok"})
        return result
