"""Run workspace (layout per skills/adef-shared-guardrails/references/artifact-layout.md).

Enforces, outside the prompts:
- one writer per stage folder (per-agent write allowlist)           E2-3
- secret scanner on every file write                                E2-4
- no technology names in logical artifacts                          GT-13
- append-only, hash-chained logs (editing a past entry is detected) E1-5
- approvals tied to artifact hashes, with expiry                    E2-1, GT-03
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import runs_dir
from ..guardrails.actions import GuardrailBlocked
from ..guardrails.scanners import scan_secrets, scan_tech_terms
from ..util import dump_yaml, now_iso, sha256_bytes, sha256_text

STAGE_FOLDERS = ["00-intake", "01-requirements", "02-mapping", "03-design/logical", "03-design/physical",
                 "04-build", "05-test", "06-release", "07-operations", "08-consumption", "final",
                 "control/handoffs"]

WRITE_ALLOWLIST: dict[str, list[str]] = {
    "adef-orchestrator": ["00-intake/", "final/", "control/"],
    "adef-intent-requirements": ["01-requirements/"],
    "adef-source-target-mapping": ["02-mapping/"],
    "adef-solution-design": ["03-design/"],
    "adef-pipeline-build": ["04-build/"],
    "adef-test-quality": ["05-test/"],
    "adef-release-deploy": ["06-release/"],
    "adef-operations-observability": ["07-operations/"],
    "adef-data-consumption": ["08-consumption/"],
}
LOGICAL_PREFIXES = ("01-requirements/", "02-mapping/", "03-design/logical/")
# Raw technology names are allowed where they are data, not design: imported inventories.
TECH_SCAN_EXEMPT = ("02-mapping/source-inventory.md", "02-mapping/profile-summary.md")

GATE_ROLES: dict[str, list[str]] = {
    "G0": ["product_owner", "data_architect"],
    "G1": ["product_owner"],
    "G2": ["data_steward"],
    "G3": ["data_architect"],
    "G4": ["tech_lead"],
    "G5": ["tech_lead", "product_owner"],
    "G6a": ["release_manager"],
    "G6b": ["release_manager", "platform_owner"],
    "G7": ["platform_owner"],
    "G8": ["product_owner", "data_steward"],
}
ROLE_LABELS = {"product_owner": "Product Owner", "data_architect": "Data Architect", "data_steward": "Data Steward",
               "tech_lead": "Tech Lead", "release_manager": "Release Manager", "platform_owner": "Platform Owner",
               "security_compliance": "Security and Compliance"}

_locks: dict[str, threading.RLock] = {}


def _lock_for(run_id: str) -> threading.RLock:
    return _locks.setdefault(run_id, threading.RLock())


def bundle_hash(artifacts: dict[str, str]) -> str:
    return sha256_text("\n".join(f"{p}:{h}" for p, h in sorted(artifacts.items())))


class RunWorkspace:
    def __init__(self, run_id: str, root: Path | None = None):
        self.run_id = run_id
        self.root = (root or runs_dir()) / run_id
        self.lock = _lock_for(run_id)

    # ---------- creation / basic io ----------
    def exists(self) -> bool:
        return (self.root / "control" / "run.yaml").exists()

    def create(self, run_def: dict, stack_profile: dict, domain_pack_text: str) -> None:
        if self.exists():
            raise FileExistsError(self.run_id)
        for f in STAGE_FOLDERS:
            (self.root / f).mkdir(parents=True, exist_ok=True)
        self._raw_write("control/run.yaml", dump_yaml(run_def))
        self._raw_write("control/stack-profile.yaml", dump_yaml(stack_profile))
        self._raw_write("control/domain-pack.yaml", domain_pack_text)
        self._raw_write("control/decision-log.md", f"# Decision log - {self.run_id}\n\nAppend-only.\n")
        for log in ("approvals", "action-log", "decision-log"):
            (self.root / "control" / f"{log}.jsonl").touch()

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise GuardrailBlocked("path-escape", f"Path {rel} escapes the run workspace")
        return p

    def _raw_write(self, rel: str, content: str | bytes) -> str:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        # atomic replace: concurrent readers (API polling, receiver checks) never see a partial file
        tmp = p.with_name(f".{p.name}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        return sha256_bytes(data)

    def read(self, rel: str) -> str:
        return self.path(rel).read_text()

    def read_yaml(self, rel: str) -> Any:
        return yaml.safe_load(self.read(rel))

    def read_json(self, rel: str) -> Any:
        return json.loads(self.read(rel))

    def has(self, rel: str) -> bool:
        return self.path(rel).exists()

    def sha(self, rel: str) -> str | None:
        p = self.path(rel)
        return sha256_bytes(p.read_bytes()) if p.exists() else None

    def files(self) -> list[dict]:
        out = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.name.endswith((".lock", ".tmp")):
                rel = str(p.relative_to(self.root))
                if rel.startswith(("repo/", "sandbox/", "lakehouse/")):
                    continue
                out.append({"path": rel, "size": p.stat().st_size, "sha256": sha256_bytes(p.read_bytes())})
        return out

    @property
    def run(self) -> dict:
        return self.read_yaml("control/run.yaml")

    @property
    def stack(self) -> dict:
        return self.read_yaml("control/stack-profile.yaml")

    @property
    def domain(self) -> dict:
        return self.read_yaml("control/domain-pack.yaml")

    # ---------- guarded writes ----------
    def write(self, agent: str, rel: str, content: str, *, allow_tech: bool = False) -> str:
        allowed = WRITE_ALLOWLIST.get(agent, [])
        if not any(rel.startswith(a) for a in allowed):
            self.log_action({"agent": agent, "action": "write_artifact", "class": "A4", "target": rel,
                             "phase": "blocked", "rule": "one-writer-per-folder"})
            raise GuardrailBlocked("one-writer-per-folder",
                                   f"{agent} may not write {rel}; it owns only {', '.join(allowed)}")
        if scan_secrets(content):
            self.log_action({"agent": agent, "action": "write_artifact", "class": "A4", "target": rel,
                             "phase": "blocked", "rule": "no-secrets-in-artifacts"})
            raise GuardrailBlocked("no-secrets-in-artifacts", f"Secret-like content blocked in {rel}")
        if rel.startswith(LOGICAL_PREFIXES) and rel not in TECH_SCAN_EXEMPT and not allow_tech:
            terms = scan_tech_terms(content)
            if terms:
                self.log_action({"agent": agent, "action": "write_artifact", "class": "A1", "target": rel,
                                 "phase": "blocked", "rule": "logical-before-physical", "terms": terms})
                raise GuardrailBlocked("logical-before-physical",
                                       f"Technology terms {terms} are not allowed in logical artifact {rel}")
        with self.lock:
            h = self._raw_write(rel, content)
        self.log_action({"agent": agent, "action": "write_artifact", "class": "A1", "target": rel,
                         "phase": "done", "sha256": h})
        return h

    # ---------- append-only hash-chained logs ----------
    def append_log(self, name: str, entry: dict) -> dict:
        with self.lock:
            p = self.path(f"control/{name}.jsonl")
            prev = "0" * 64
            if p.exists() and p.stat().st_size:
                last = p.read_text().strip().splitlines()[-1]
                prev = json.loads(last)["entry_hash"]
            rec = {"ts": now_iso(), "run_id": self.run_id, **entry, "prev_hash": prev}
            rec["entry_hash"] = sha256_text(json.dumps(rec, sort_keys=True))
            with p.open("a") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            return rec

    def read_log(self, name: str) -> list[dict]:
        p = self.path(f"control/{name}.jsonl")
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    def verify_log(self, name: str) -> dict:
        prev = "0" * 64
        for i, rec in enumerate(self.read_log(name)):
            body = {k: v for k, v in rec.items() if k != "entry_hash"}
            if rec.get("prev_hash") != prev or sha256_text(json.dumps(body, sort_keys=True)) != rec.get("entry_hash"):
                return {"log": name, "ok": False, "broken_at": i}
            prev = rec["entry_hash"]
        return {"log": name, "ok": True, "entries": len(self.read_log(name))}

    def log_action(self, entry: dict) -> dict:
        return self.append_log("action-log", entry)

    def log_decision(self, decision: str, options: list[str], evidence: list[str], decided_by: str) -> None:
        rec = self.append_log("decision-log", {"decision": decision, "options": options, "evidence": evidence,
                                               "decided_by": decided_by})
        with self.lock, self.path("control/decision-log.md").open("a") as f:
            f.write(f"\n## {rec['ts']} - {decision}\n\n- Decided by: {decided_by}\n"
                    f"- Options considered: {'; '.join(options) or 'n/a'}\n"
                    f"- Evidence: {', '.join(evidence) or 'n/a'}\n")

    # ---------- approvals ----------
    def current_hashes(self, paths: list[str]) -> dict[str, str]:
        return {p: (self.sha(p) or "missing") for p in paths}

    def request_gate(self, gate: str, stage: str, artifacts: list[str], requested_by: str, *, summary: str,
                     evidence: list[str], risk: str, cost: str, rollback: str, options: list[str],
                     extra_roles: list[str] | None = None) -> dict:
        hashes = self.current_hashes(artifacts)
        roles = list(dict.fromkeys(GATE_ROLES.get(gate, []) + (extra_roles or [])))
        n = sum(1 for r in self.read_log("approvals") if r.get("type") == "request") + 1
        req = {"type": "request", "request_id": f"REQ-{gate}-{n:03d}", "gate": gate, "stage": stage,
               "action_class": "A3" if gate in ("G6b", "G8", "G7") else "A2",
               "subject": artifacts[0] if artifacts else stage, "artifacts": hashes,
               "artifact_sha256": bundle_hash(hashes), "required_roles": roles, "requested_by": requested_by,
               "summary": summary, "evidence": evidence, "risk": risk, "cost": cost, "rollback": rollback,
               "options": options,
               "expires": (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")}
        return self.append_log("approvals", req)

    def latest_request(self, gate: str) -> dict | None:
        reqs = [r for r in self.read_log("approvals") if r.get("type") == "request" and r["gate"] == gate]
        return reqs[-1] if reqs else None

    def decide(self, gate: str, approver: str, role: str, decision: str, comment: str = "",
               conditions: list[str] | None = None) -> dict:
        if decision not in ("approved", "rejected", "approved-with-conditions"):
            raise ValueError("decision must be approved, rejected or approved-with-conditions")
        if approver.lower().startswith("adef-") or approver.lower() in ("agent", "system", "orchestrator"):
            raise GuardrailBlocked("agents-never-approve", "An agent can never record an approval decision")
        holders = (self.run.get("approvers") or {})
        if holders.get(role) != approver:
            raise GuardrailBlocked("named-approver-only",
                                   f"{approver} does not hold the {ROLE_LABELS.get(role, role)} role in run.yaml")
        req = self.latest_request(gate)
        if not req:
            raise GuardrailBlocked("no-request", f"No open approval request for {gate}")
        if role not in req["required_roles"]:
            raise GuardrailBlocked("role-not-required", f"{ROLE_LABELS.get(role, role)} is not an approver for {gate}")
        now_hashes = self.current_hashes(list(req["artifacts"]))
        if bundle_hash(now_hashes) != req["artifact_sha256"]:
            raise GuardrailBlocked("approval-drift",
                                   f"Artifacts for {gate} changed after the request; the gate must be re-requested")
        n = sum(1 for r in self.read_log("approvals") if r.get("type") == "decision") + 1
        rec = {"type": "decision", "approval_id": f"APR-{n:04d}", "request_id": req["request_id"], "gate": gate,
               "action_class": req["action_class"], "subject": req["subject"],
               "artifact_sha256": req["artifact_sha256"], "decision": decision, "approver": approver,
               "role": ROLE_LABELS.get(role, role), "role_key": role, "conditions": conditions or [],
               "comment": comment, "expires": req["expires"], "timestamp": now_iso()}
        out = self.append_log("approvals", rec)
        self.log_decision(f"{gate} {decision} by {ROLE_LABELS.get(role, role)}", req["options"],
                          list(req["artifacts"]), approver)
        return out

    def record_artifact_reviews(self, gate: str, approver: str, role: str, reviews: list[dict]) -> tuple[str, str]:
        """Record one approve/reject per artifact of the open request for this gate, by a named approver.

        Every artifact in the request must be reviewed; a rejection needs a reason. Each review is bound to the
        artifact's hash. Returns the derived gate decision and the combined comment for the decision record."""
        if approver.lower().startswith("adef-") or approver.lower() in ("agent", "system", "orchestrator"):
            raise GuardrailBlocked("agents-never-approve", "An agent can never record an approval decision")
        if (self.run.get("approvers") or {}).get(role) != approver:
            raise GuardrailBlocked("named-approver-only",
                                   f"{approver} does not hold the {ROLE_LABELS.get(role, role)} role in run.yaml")
        req = self.latest_request(gate)
        if not req:
            raise GuardrailBlocked("no-request", f"No open approval request for {gate}")
        if role not in req["required_roles"]:
            raise GuardrailBlocked("role-not-required", f"{ROLE_LABELS.get(role, role)} is not an approver for {gate}")
        by_path = {}
        for r in reviews:
            if r.get("path") not in req["artifacts"]:
                raise ValueError(f"{r.get('path')} is not an artifact of {gate}")
            if r.get("decision") not in ("approved", "rejected"):
                raise ValueError(f"{r.get('path')}: decision must be approved or rejected")
            if r["decision"] == "rejected" and len((r.get("comment") or "").strip()) < 5:
                raise ValueError(f"{r['path']}: say what is wrong with it (section and defect) to reject it")
            by_path[r["path"]] = r
        missing = [p for p in req["artifacts"] if p not in by_path]
        if missing:
            raise ValueError(f"Review every artifact of {gate}; not reviewed: {', '.join(missing)}")
        current = self.current_hashes(list(req["artifacts"]))
        changed = [p for p in req["artifacts"] if current[p] != req["artifacts"][p]]
        if changed:
            raise GuardrailBlocked("approval-drift", f"Changed after the request: {', '.join(changed)}; re-request {gate}")
        n = sum(1 for r in self.read_log("approvals") if r.get("type") == "artifact_review")
        for i, path in enumerate(req["artifacts"], start=1):
            r = by_path[path]
            self.append_log("approvals", {
                "type": "artifact_review", "review_id": f"ARV-{n + i:04d}", "request_id": req["request_id"], "gate": gate,
                "path": path, "artifact_sha256": req["artifacts"][path], "decision": r["decision"],
                "comment": (r.get("comment") or "").strip(), "approver": approver, "role": ROLE_LABELS.get(role, role),
                "role_key": role, "timestamp": now_iso()})
        rejected = [by_path[p] for p in req["artifacts"] if by_path[p]["decision"] == "rejected"]
        if rejected:
            comment = (f"Rejected {len(rejected)} of {len(req['artifacts'])} artifacts:\n"
                       + "\n".join(f"- {r['path']}: {r['comment'].strip()}" for r in rejected))
            return "rejected", comment
        notes = [f"- {p}: {by_path[p]['comment'].strip()}" for p in req["artifacts"] if (by_path[p].get("comment") or "").strip()]
        return "approved", f"All {len(req['artifacts'])} artifacts approved individually." + ("\n" + "\n".join(notes) if notes else "")

    def artifact_reviews(self, request_id: str) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self.read_log("approvals"):
            if r.get("type") == "artifact_review" and r.get("request_id") == request_id:
                out.setdefault(r["path"], []).append({k: r[k] for k in ("review_id", "decision", "comment", "approver",
                                                                        "role", "role_key", "timestamp")})
        return out

    def gate_status(self, gate: str) -> dict:
        req = self.latest_request(gate)
        if not req:
            return {"gate": gate, "state": "not-requested"}
        decisions = [r for r in self.read_log("approvals")
                     if r.get("type") == "decision" and r.get("request_id") == req["request_id"]]
        now_hashes = self.current_hashes(list(req["artifacts"]))
        drift = bundle_hash(now_hashes) != req["artifact_sha256"]
        changed = [p for p, h in now_hashes.items() if req["artifacts"].get(p) != h]
        rejected = [d for d in decisions if d["decision"] == "rejected"]
        approved_roles = {d["role_key"] for d in decisions if d["decision"].startswith("approved")}
        pending = [r for r in req["required_roles"] if r not in approved_roles]
        expired = req["expires"] < datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if drift:
            state = "stale"
        elif rejected:
            state = "rejected"
        elif expired:
            state = "expired"
        elif pending:
            state = "pending"
        else:
            state = "approved"
        conditions = [c for d in decisions for c in d.get("conditions", [])]
        return {"gate": gate, "state": state, "request": req, "decisions": decisions, "pending_roles": pending,
                "changed_artifacts": changed, "conditions": conditions,
                "artifact_reviews": self.artifact_reviews(req["request_id"])}

    def gate_passed(self, gate: str) -> bool:
        return self.gate_status(gate)["state"] == "approved"

    def rejection_count(self, gate: str) -> int:
        """Number of rejected requests for this gate (several roles rejecting one request count once)."""
        return len({r["request_id"] for r in self.read_log("approvals") if r.get("type") == "decision"
                    and r["gate"] == gate and r["decision"] == "rejected"})
