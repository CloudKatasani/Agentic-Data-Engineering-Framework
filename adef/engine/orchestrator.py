"""The control plane: runs stages, enforces gates, routes handoffs, assembles delivery.

Stage agents run in background threads. All state lives in the run workspace
(control/state.json plus the append-only logs), so the API is stateless and a restart
resumes from disk.
"""
from __future__ import annotations

import json
import re
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .. import context_hub
from ..catalog import stacks
from ..catalog.domains import load_pack_text
from ..config import runs_dir
from ..guardrails.actions import GuardrailBlocked
from ..guardrails.scanners import scan_injection, scan_secrets
from ..llm.base import LLMError
from ..catalog.providers import provider_ready
from ..llm.router import build_provider, binding_for
from ..llm.simulator import SimulatorProvider
from ..settings_store import SettingsStore
from ..util import dump_yaml, load_yaml, now_iso, sha256_file
from ..workspace import handoff as ho
from ..workspace.run import GATE_ROLES, ROLE_LABELS, RunWorkspace
from . import agents_back as back
from . import agents_front as front
from .agent_runtime import AgentCall, Usage
from .context import StageCtx, StageOutput
from .scenarios import for_domain
from .stages import GATE_LABELS, STAGE_KEYS, STAGES, previous_gate, stage

RUNNERS = {"intake": front.intake, "requirements": front.requirements, "mapping": front.mapping, "design": front.design,
           "build": back.build, "test": back.test, "release": back.release, "operations": back.operations,
           "consumption": back.consumption}


class InputRejected(Exception):
    pass


class Engine:
    def __init__(self, settings: SettingsStore | None = None, workers: int = 4):
        self.settings = settings or SettingsStore()
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="adef-agent")
        self._lock = threading.RLock()
        self._live: set[tuple[str, str]] = set()   # (run_id, stage key or "gate:Gx") being worked on in this process

    # ------------------------------------------------------------------ state
    def ws(self, run_id: str) -> RunWorkspace:
        ws = RunWorkspace(run_id)
        if not ws.exists():
            raise KeyError(run_id)
        return ws

    def _state(self, ws) -> dict:
        return json.loads(ws.path("control/state.json").read_text())

    def _save(self, ws, st: dict) -> None:
        with ws.lock:
            ws._raw_write("control/state.json", json.dumps(st, indent=2))

    def _update(self, ws, fn) -> dict:
        with ws.lock:
            st = self._state(ws)
            fn(st)
            st["updated"] = now_iso()
            self._save(ws, st)
            return st

    def event(self, ws, text: str, kind: str = "info") -> None:
        ws.append_log("events", {"kind": kind, "text": text})

    def list_runs(self) -> list[dict]:
        out = []
        for d in sorted(runs_dir().glob("RUN-*"), reverse=True):
            ws = RunWorkspace(d.name)
            if ws.exists():
                try:
                    st = self._state(ws)
                    run = ws.run
                    out.append({"run_id": d.name, "client_code": run["client_code"], "use_case": run["use_case"],
                                "domain_pack": run["domain_pack"], "stack": ws.stack.get("label", ws.stack["profile_id"]),
                                "status": st["status"], "current": st.get("current"), "created": st["created"],
                                "updated": st.get("updated"),
                                "pending_gates": [g for g, v in st.get("gates", {}).items() if v == "pending"]})
                except (OSError, KeyError, ValueError):
                    continue
        return out

    def new_run_id(self) -> str:
        year = datetime.now().year
        existing = [int(m.group(1)) for d in runs_dir().glob(f"RUN-{year}-*")
                    if (m := re.match(rf"RUN-{year}-(\d+)$", d.name))]
        return f"RUN-{year}-{(max(existing) + 1 if existing else 1):03d}"

    # ------------------------------------------------------------------ create
    def create_run(self, p: dict, start: bool = True) -> dict:
        request = p.get("request", "")
        for field in ("request", "use_case", "documents"):
            if scan_secrets(p.get(field) or ""):
                raise InputRejected("The request contains what looks like a password, key or token. It was not stored. "
                                    "Rotate that credential now, and add credentials only through the Secrets vault "
                                    "(referenced by name). (GT-01)")
        domain = p.get("domain_pack") or "utilities"
        profile = p.get("stack_profile") or stacks.preset("example-a")
        if isinstance(profile, str):
            profile = self.stack_by_id(profile)
        other_clients = {r["client_code"] for r in self.list_runs()} - {p.get("client_code")}
        if p.get("copy_from_run"):
            src = self.ws(p["copy_from_run"])
            if src.run["client_code"] != p.get("client_code"):
                raise InputRejected("Copying artifacts from another client's run is prohibited (A4: client isolation, GT-11).")
        _ = other_clients
        team = self.settings.load()
        overrides = {}
        for agent, o in (p.get("agent_bindings") or {}).items():
            if agent not in team["agents"]:
                raise InputRejected(f"Unknown agent `{agent}`")
            if not any(pr["id"] == o.get("provider_id") for pr in team["providers"]):
                raise InputRejected(f"{agent}: unknown provider `{o.get('provider_id')}`")
            if not str(o.get("model") or "").strip():
                raise InputRejected(f"{agent}: choose a model")
            overrides[agent] = {"provider_id": o["provider_id"], "model": str(o["model"]).strip(),
                                "effort": o.get("effort") or team["agents"][agent].get("effort") or "medium"}
        run_id = self.new_run_id()
        sc = for_domain(domain)
        approvers = {**self.settings.load()["approver_defaults"], **(p.get("approvers") or {})}
        run_def = {"run_id": run_id, "client_code": (p.get("client_code") or "CLIENT-A").upper(),
                   "use_case": p.get("use_case") or sc["title"], "domain_pack": domain,
                   "stack_profile": "stack-profile.yaml", "approvers": approvers,
                   "budget": {"compute_cost_cap": float(p.get("compute_cost_cap") or 0), "max_stage_loops": 3, "max_run_days": 10},
                   "limits": {"profiling_row_cap": int(profile.get("limits", {}).get("profiling_row_cap", 10000)),
                              "query_timeout_seconds": int(profile.get("limits", {}).get("query_timeout_seconds", 120))},
                   "autopilot": bool(p.get("autopilot", True)),
                   # where Pipeline 1 extracts from; credentials only by vault reference
                   "source_connection": {k: v for k, v in (p.get("source_connection") or
                                                           {"type": "sqlite-local", "pack": domain}).items()
                                         if k != "password"},
                   "agent_bindings": {a: {k: v for k, v in binding_for(a, team, overrides.get(a)).items()
                                          if k in ("provider_id", "model", "effort")} for a in team["agents"]},
                   "agent_overrides": sorted(overrides)}
        ws = RunWorkspace(run_id)
        ws.create(run_def, profile, load_pack_text(domain))
        ws._raw_write("00-intake/inputs/request.md", request or sc["request"])
        if p.get("jira_issues"):
            ws._raw_write("00-intake/inputs/jira-issues.json", json.dumps(p["jira_issues"], indent=2))
        if p.get("source_metadata"):
            ws._raw_write("00-intake/inputs/source-metadata.json", json.dumps(p["source_metadata"], indent=2))
        if p.get("documents"):
            ws._raw_write("00-intake/inputs/documents.md", p["documents"])
        st = {"run_id": run_id, "status": "active", "created": now_iso(), "updated": now_iso(), "current": "intake",
              "stages": {s["key"]: {"status": "pending", "attempts": 0, "returns": 0} for s in STAGES},
              "gates": {}, "usage": {}, "metrics": {"guardrail_blocks": 0}}
        self._save(ws, st)
        ws.log_decision("Run created", ["proceed", "do not start"], ["control/run.yaml"], "adef-orchestrator")
        self.event(ws, f"Run {run_id} created for {run_def['client_code']}: {run_def['use_case']}")
        if start:
            self.start_stage(run_id, "intake")
        return {"run_id": run_id}

    def stack_by_id(self, pid: str) -> dict:
        p = stacks.preset(pid)
        if p:
            return p
        for sp in self.settings.load().get("stack_profiles", []):
            if sp["profile_id"] == pid:
                return sp
        raise KeyError(f"unknown stack profile {pid}")

    # ------------------------------------------------------------------ stage execution
    def start_stage(self, run_id: str, key: str, feedback: str | None = None) -> None:
        ws = self.ws(run_id)
        st = self._state(ws)
        if st["stages"][key]["status"] == "running" and (run_id, key) in self._live:
            return
        self._live.add((run_id, key))
        self._update(ws, lambda s: (s["stages"][key].update(status="running", started=now_iso(), error=None, finished=None),
                                    s.update(current=key)))
        self.pool.submit(self._run_stage_safe, run_id, key, feedback)

    def run_stage_sync(self, run_id: str, key: str, feedback: str | None = None) -> None:
        ws = self.ws(run_id)
        self._live.add((run_id, key))
        self._update(ws, lambda s: (s["stages"][key].update(status="running", started=now_iso(), error=None, finished=None),
                                    s.update(current=key)))
        self._run_stage_safe(run_id, key, feedback)

    def _run_stage_safe(self, run_id: str, key: str, feedback: str | None) -> None:
        ws = self.ws(run_id)
        try:
            self._run_stage(ws, key, feedback)
        except GuardrailBlocked as e:
            self._block(ws, key, f"Guardrail `{e.rule}`: {e.message}")
        except (LLMError, ho.EnvelopeInvalid) as e:
            self._fail(ws, key, str(e))
        except Exception as e:  # noqa: BLE001 - surface any agent crash in the console
            self._fail(ws, key, f"{type(e).__name__}: {e}")
            ws.append_log("events", {"kind": "error", "text": traceback.format_exc()[-1500:]})
        finally:
            self._live.discard((run_id, key))

    def _block(self, ws, key, msg):
        self._update(ws, lambda s: (s["stages"][key].update(status="blocked", error=msg),
                                    s["metrics"].__setitem__("guardrail_blocks", s["metrics"].get("guardrail_blocks", 0) + 1)))
        self.event(ws, f"{stage(key)['label']} blocked and escalated to the human owner. {msg}", "blocked")
        ws.log_decision(f"Escalation: {stage(key)['label']} blocked", ["fix input and retry", "change scope"], [], "adef-orchestrator")

    def _fail(self, ws, key, msg):
        self._update(ws, lambda s: s["stages"][key].update(status="failed", error=msg))
        self.event(ws, f"{stage(key)['label']} failed: {msg}", "error")

    def _call(self, ws, agent: str, force_fallback: str | None = None) -> AgentCall:
        settings = self.settings.load()
        # agents rebound for this run at launch keep that choice; the rest follow the saved team bindings
        override = (ws.run.get("agent_bindings") or {}).get(agent) if agent in (ws.run.get("agent_overrides") or []) else None
        b = binding_for(agent, settings, override)
        log = lambda t: self.event(ws, t, "agent")  # noqa: E731
        reason = force_fallback
        prov = None
        if not reason:
            if not provider_ready(b["provider"]):
                reason = f"{b['provider']['label']} has no API key configured"
            else:
                try:
                    prov = build_provider(b["provider"])
                except LLMError as e:
                    reason = str(e)
        if reason:
            if not (settings.get("runtime") or {}).get("simulate_unavailable_providers", True):
                raise LLMError(f"{agent}: {reason}. Configure the key or rebind the agent.")
            call = AgentCall(agent, SimulatorProvider({"id": "demo", "type": "simulator"}, None), b, log)
            call.fallback_reason = reason
            self.event(ws, f"{agent} is bound to {b['provider']['label']} / {b['model']} but {reason}; "
                           "this stage runs on the Demo Simulator (demo fallback is on).", "warn")
            ws.log_decision(f"{agent} simulated: {reason}", ["simulate for the demo", "stop until a key is configured"],
                            [], "adef-orchestrator (runtime setting simulate_unavailable_providers)")
            return call
        return AgentCall(agent, prov, b, log)

    def _receiver_check(self, ws, key: str) -> list[str]:
        i = STAGE_KEYS.index(key)
        if i == 0:
            return []
        prev = STAGES[i - 1]
        hdir = ws.root / "control" / "handoffs"
        frm, to = prev["agent"], stage(key)["agent"]
        legacy = (frm.replace("adef-", "adpe-", 1), to.replace("adef-", "adpe-", 1))  # runs started before the rename
        candidates = list(hdir.glob(f"*-{frm}-to-{to}.yaml")) + list(hdir.glob(f"*-{legacy[0]}-to-{legacy[1]}.yaml"))
        env_path = next(iter(sorted(candidates, key=lambda p: p.name, reverse=True)), None)
        if not env_path:
            return [f"No handoff envelope from {prev['agent']}"]
        env = load_yaml(env_path.read_text())
        return ho.receiver_checks(ws, env, previous_gate(key))

    def _run_stage(self, ws, key: str, feedback: str | None) -> None:
        s = stage(key)
        problems = self._receiver_check(ws, key)
        if problems:
            st = self._update(ws, lambda x: x["stages"][key].__setitem__("returns", x["stages"][key].get("returns", 0) + 1))
            returns = st["stages"][key]["returns"]
            prev = STAGES[STAGE_KEYS.index(key) - 1]
            self._envelope(ws, s["agent"], prev["agent"], s["envelope_stage"], "returned", None,
                           StageOutput(artifacts=[], summary=f"Handoff returned: {problems[0]}"), return_reason="; ".join(problems))
            if returns >= 3:
                raise GuardrailBlocked("three-returns", f"Handoff returned {returns} times; escalated to the human owner (GT-14)")
            raise GuardrailBlocked("receiver-check", "; ".join(problems))
        call = self._call(ws, s["agent"])
        call.context, ctx_ids = context_hub.prompt_block(ws, key)
        if ctx_ids:
            self.event(ws, f"{s['agent']} was given {len(ctx_ids)} context item(s) attached by the team: {', '.join(ctx_ids)}", "agent")
        sc = for_domain(ws.run["domain_pack"])
        ctx = StageCtx(ws=ws, call=call, scenario=sc, log=lambda t: self.event(ws, t, "agent"), feedback=feedback,
                       settings=self.settings.load())
        self.event(ws, f"{s['label']} started by {s['agent']} using {call.binding['provider']['label']} / {call.binding['model']}", "stage")
        runner = (lambda c: back.assembly(c, self.metrics(ws))) if key == "assembly" else RUNNERS[key]
        try:
            out = runner(ctx)
        except LLMError as e:
            if call.simulated or not (self.settings.load().get("runtime") or {}).get("simulate_unavailable_providers", True):
                raise
            call = self._call(ws, s["agent"], force_fallback=f"the call failed ({e})")
            ctx.call = call
            out = runner(ctx)
        if ctx_ids:
            # the record of what the agent was given goes to the gate with the stage's own artifacts
            used = context_hub.mark_used(ws, key, ctx_ids, out.artifacts)
            pack = f"{s['folder']}/context-pack.md"
            ctx.write(pack, context_hub.pack_md(ws, key, s["label"], s["agent"], used, out.inputs_used, call.simulated),
                      allow_tech=True)
            if pack not in out.artifacts:
                out.artifacts.append(pack)
        usage = call.usage.as_dict()
        if call.fallback_reason:
            usage["models"] = [f"simulated (bound to {call.binding['provider']['type']}:{call.binding['model']})"]
            usage["fallback"] = call.fallback_reason
        elif not usage["models"]:
            # be exact about what ran: a stage that needed no model call must not look like the bound model served it
            usage["models"] = ["no model call needed (rule-based stage)"]
        self._update(ws, lambda x: (x["usage"].__setitem__(s["agent"], self._merge_usage(x["usage"].get(s["agent"]), usage)),
                                    x["stages"][key].update(attempts=x["stages"][key].get("attempts", 0) + 1, finished=now_iso(),
                                                            summary=out.summary, artifacts=out.artifacts)))
        if not out.request_gate:
            self._envelope(ws, s["agent"], "human", s["envelope_stage"], "ready", None, out, usage=usage)
            self._update(ws, lambda x: (x["stages"][key].update(status="done"), x.update(status="completed", current=None)))
            self.event(ws, f"Run complete. {out.summary}", "done")
            return
        gate = s["gates"][0]
        self._envelope(ws, s["agent"], s["next_agent"], s["envelope_stage"], "needs-approval", gate, out, usage=usage)
        self._request(ws, key, gate, out)

    @staticmethod
    def _merge_usage(a: dict | None, b: dict) -> dict:
        if not a:
            return b
        return {"fallback": b.get("fallback"), "calls": a["calls"] + b["calls"], "input_tokens": a["input_tokens"] + b["input_tokens"],
                "output_tokens": a["output_tokens"] + b["output_tokens"], "tokens": a["tokens"] + b["tokens"],
                "llm_cost_usd": round(a["llm_cost_usd"] + b["llm_cost_usd"], 4), "seconds": a["seconds"] + b["seconds"],
                "models": sorted(set(a["models"]) | set(b["models"]))}

    def _envelope(self, ws, frm, to, stage_name, status, gate, out: StageOutput, usage=None, return_reason=None):
        arts = []
        for pth in out.artifacts:
            if ws.has(pth):
                kind = ("config" if pth.startswith("control/") else "logical" if pth.startswith(("01-", "02-", "03-design/logical"))
                        else "physical" if pth.startswith("03-design/physical") else "code" if pth.startswith("04-")
                        else "evidence")
                arts.append({"path": pth, "sha256": ws.sha(pth), "kind": kind, "owner_agent": frm if frm != "human" else "adef-orchestrator"})
        if not arts:
            arts = [{"path": "control/run.yaml", "sha256": ws.sha("control/run.yaml"), "kind": "config", "owner_agent": "adef-orchestrator"}]
        u = usage or {}
        env = {"run_id": ws.run_id, "seq": ho.next_seq(ws), "from_agent": frm, "to_agent": to, "stage": stage_name,
               "status": status, "summary": out.summary[:600], "artifacts": arts,
               "inputs_used": [{"path": p, "sha256": ws.sha(p)} for p in out.inputs_used if ws.has(p)],
               "requirement_ids": [r for r in out.requirement_ids if re.match(r"^(REQ|BR|NFR)-\d{3}$", r)],
               "assumptions": out.assumptions, "open_questions": out.open_questions, "risks": out.risks,
               "evidence": out.evidence, "constraints": out.constraints,
               "confidence": {"level": out.confidence[0], "why": out.confidence[1] or "n/a"},
               "budget_used": {"compute_cost": 0, "tokens": int(u.get("tokens", 0)), "elapsed_minutes": round(u.get("seconds", 0) / 60, 2)}}
        if gate:
            env["gate"] = gate
        if return_reason:
            env["return_reason"] = return_reason
        return ho.write_envelope(ws, env)

    def _request(self, ws, key, gate, out: StageOutput, artifacts: list[str] | None = None):
        gm = out.gate_meta
        req = ws.request_gate(gate, key, artifacts or out.artifacts, stage(key)["agent"], summary=out.summary,
                              evidence=out.evidence, risk=gm.get("risk", ""), cost=gm.get("cost", ""),
                              rollback=gm.get("rollback", ""), options=gm.get("options", []),
                              extra_roles=gm.get("extra_roles"))
        self._update(ws, lambda x: (x["stages"][key].update(status="awaiting-approval"), x["gates"].__setitem__(gate, "pending")))
        roles = ", ".join(ROLE_LABELS[r] for r in req["required_roles"])
        self.event(ws, f"Gate {gate} ({GATE_LABELS[gate]}) requested from {roles}", "gate")

    # ------------------------------------------------------------------ approvals
    def decide(self, run_id: str, gate: str, approver: str, role: str, decision: str, comment: str = "",
               conditions: list[str] | None = None) -> dict:
        ws = self.ws(run_id)
        rec = ws.decide(gate, approver, role, decision, comment, conditions)
        self.event(ws, f"{gate} {decision} by {approver} as {ROLE_LABELS.get(role, role)}" + (f": {comment}" if comment else ""), "gate")
        key = next(s["key"] for s in STAGES if gate in s["gates"])
        if decision == "rejected":
            n = ws.rejection_count(gate)
            status = "blocked" if n >= 2 else "rejected"
            self._update(ws, lambda x: (x["stages"][key].update(status=status, error=f"{gate} rejected: {comment}"),
                                        x["gates"].__setitem__(gate, "rejected")))
            if n >= 2:
                self.event(ws, f"{gate} rejected twice - escalated to the human owner", "blocked")
            return {"decision": rec, "gate_state": "rejected"}
        gs = ws.gate_status(gate)
        if gs["state"] != "approved":
            return {"decision": rec, "gate_state": gs["state"], "pending_roles": gs["pending_roles"]}
        self._update(ws, lambda x: x["gates"].__setitem__(gate, "approved"))
        self._live.add((run_id, f"gate:{gate}"))
        self.pool.submit(self._after_gate_safe, run_id, key, gate)
        return {"decision": rec, "gate_state": "approved"}

    def _after_gate_safe(self, run_id, key, gate):
        ws = self.ws(run_id)
        try:
            self._after_gate(ws, key, gate)
        except GuardrailBlocked as e:
            self._block(ws, key, f"Guardrail `{e.rule}`: {e.message}")
        except Exception as e:  # noqa: BLE001
            self._fail(ws, key, f"post-approval action failed: {type(e).__name__}: {e}")
        finally:
            self._live.discard((run_id, f"gate:{gate}"))

    def _after_gate(self, ws, key, gate):
        log = lambda t: self.event(ws, t, "action")  # noqa: E731
        ids = [d["approval_id"] for d in ws.gate_status(gate)["decisions"] if d["decision"].startswith("approved")]
        if gate == "G4":
            back.after_g4(ws, log)
        elif gate == "G6a":
            arts = back.after_g6a(ws, log)
            out = StageOutput(artifacts=arts, summary="REL-001 verified in test (shared). Requesting G6b for production.",
                              gate_meta={"risk": "Production change (A3).", "cost": "Within approved estimate.",
                                         "rollback": "Rehearsed per REL-001-rollback.md",
                                         "options": ["Approve production deployment", "Reject"]})
            self._envelope(ws, "adef-release-deploy", "adef-orchestrator", "release", "needs-approval", "G6b", out)
            self._request(ws, key, "G6b", out)
            return
        elif gate == "G6b":
            back.after_g6b(ws, log, ids)
        elif gate == "G8":
            back.after_g8(ws, log, ids)
        self._update(ws, lambda x: x["stages"][key].update(status="approved"))
        nxt = STAGE_KEYS[STAGE_KEYS.index(key) + 1] if key != STAGE_KEYS[-1] else None
        if nxt and ws.run.get("autopilot", True):
            self.start_stage(ws.run_id, nxt)
        else:
            self._update(ws, lambda x: x.update(current=nxt))

    def review_gate(self, run_id: str, gate: str, approver: str, roles: list[str], reviews: list[dict],
                    conditions: list[str] | None = None) -> dict:
        """Per-artifact review: each role held by the approver reviews every artifact, then the gate decision is
        derived (any rejected artifact rejects the gate, with the reasons as rework feedback)."""
        ws = self.ws(run_id)
        if not roles:
            raise ValueError("choose at least one role to review as")
        gs = ws.gate_status(gate)
        if gs["state"] != "pending":
            raise ValueError(f"{gate} is {gs['state']}, not awaiting review")
        done = [r for r in roles if r not in gs["pending_roles"]]
        if done:
            raise ValueError(f"Already decided for {gate}: {', '.join(ROLE_LABELS.get(r, r) for r in done)}")
        out = []
        for role in roles:
            decision, comment = ws.record_artifact_reviews(gate, approver, role, reviews)
            if decision == "approved" and conditions:
                decision = "approved-with-conditions"
            self.event(ws, f"{gate}: {ROLE_LABELS.get(role, role)} reviewed {len(reviews)} artifacts "
                           f"({sum(1 for r in reviews if r['decision'] == 'rejected')} rejected)", "gate")
            res = self.decide(run_id, gate, approver, role, decision, comment, conditions)
            out.append({"role": role, **res})
            if decision == "rejected":
                break  # the gate is rejected; further roles need not review this version
        return {"results": out, "gate_state": out[-1]["gate_state"]}

    def rework(self, run_id: str, key: str, feedback: str) -> None:
        ws = self.ws(run_id)
        if scan_injection(feedback):
            self.event(ws, "Rework feedback contains instruction-like text; passed to the agent as data only.", "warn")
        self.start_stage(run_id, key, feedback)

    def rerequest(self, run_id: str, gate: str) -> dict:
        """After an approved artifact was edited (approval drift), re-open the gate with new hashes."""
        ws = self.ws(run_id)
        old = ws.latest_request(gate)
        if not old:
            raise KeyError(gate)
        key = old["stage"]
        out = StageOutput(artifacts=list(old["artifacts"]), summary=old["summary"],
                          gate_meta={k: old[k] for k in ("risk", "cost", "rollback", "options")},
                          evidence=old.get("evidence", []))
        out.gate_meta["extra_roles"] = [r for r in old["required_roles"] if r not in GATE_ROLES.get(gate, [])]
        self._request(ws, key, gate, out)
        later = STAGE_KEYS[STAGE_KEYS.index(key) + 1:]
        self._update(ws, lambda x: [x["stages"][k].update(status="pending") for k in later if x["stages"][k]["status"] != "pending"])
        self.event(ws, f"{gate} re-opened after artifact change; downstream stages reset to pending", "gate")
        return ws.latest_request(gate)

    # ------------------------------------------------------------------ human edits (approval drift demo)
    def human_edit(self, run_id: str, rel: str, content: str, editor: str) -> dict:
        ws = self.ws(run_id)
        if rel.startswith("control/") or not re.match(r"^(0\d-[\w-]+|final)/", rel):
            raise GuardrailBlocked("protected-path", "Control files and logs cannot be edited")
        if scan_secrets(content):
            raise GuardrailBlocked("no-secrets-in-artifacts", "Secret-like content blocked")
        before = ws.sha(rel)
        ws._raw_write(rel, content)
        ws.log_action({"agent": "human", "actor": editor, "action": "edit_artifact", "class": "A1", "target": rel,
                       "phase": "done", "sha_before": before, "sha256": ws.sha(rel)})
        stale = [g for g in self._gates_containing(ws, rel) if ws.gate_status(g)["state"] == "stale"]
        if stale:
            self.event(ws, f"{rel} edited by {editor}; approval for {', '.join(stale)} is now stale and must be re-requested", "warn")
        return {"path": rel, "stale_gates": stale}

    def _gates_containing(self, ws, rel):
        return sorted({r["gate"] for r in ws.read_log("approvals") if r.get("type") == "request" and rel in r["artifacts"]})

    # ------------------------------------------------------------------ status + metrics
    def _recover(self, ws, st: dict) -> dict:
        """A stage marked running that no worker in this process owns was cut off (server restart): make it retryable."""
        orphans = [k for k, ss in st["stages"].items() if ss["status"] == "running" and (ws.run_id, k) not in self._live]
        for k in orphans:
            self._fail(ws, k, "Interrupted: the server restarted while this stage was running. Retry to run it again.")
        return self._state(ws) if orphans else st

    def _stalled_gate(self, ws, st: dict, gates: dict) -> tuple[str, str] | None:
        """A fully approved gate whose follow-up work never finished (stage still awaiting approval, nobody working)."""
        for s in STAGES:
            if st["stages"][s["key"]]["status"] != "awaiting-approval":
                continue
            asked = [g for g in s["gates"] if gates[g]["state"] != "not-requested"]
            if asked and gates[asked[-1]]["state"] == "approved" and (ws.run_id, f"gate:{asked[-1]}") not in self._live:
                return s["key"], asked[-1]
        return None

    def _now(self, ws, st: dict, gates: dict) -> dict:
        """What the run is doing right now and who it is waiting on: one answer, shown on every tab."""
        if st["status"] == "completed":
            return {"kind": "complete"}
        bind = ws.run.get("agent_bindings") or {}
        for s in STAGES:
            ss = st["stages"][s["key"]]
            if ss["status"] == "running":
                return {"kind": "running", "stage": s["key"], "label": s["label"], "agent": s["agent"],
                        "model": (bind.get(s["agent"]) or {}).get("model"), "since": ss.get("started")}
        for s in STAGES:
            ss = st["stages"][s["key"]]
            if ss["status"] in ("failed", "blocked", "rejected"):
                return {"kind": ss["status"], "stage": s["key"], "label": s["label"], "agent": s["agent"], "error": ss.get("error")}
        for g, gd in gates.items():
            if gd["state"] == "stale":
                return {"kind": "stale", "gate": g, "gate_label": GATE_LABELS[g]}
        for g, gd in gates.items():
            if gd["state"] == "pending":
                return {"kind": "review", "gate": g, "gate_label": GATE_LABELS[g], "since": gd["request"].get("ts"),
                        "artifacts": len(gd["request"]["artifacts"]),
                        "waiting_on": [{"role": ROLE_LABELS.get(r, r), "name": ws.run["approvers"].get(r, "?")}
                                       for r in gd["pending_roles"]]}
        for g in gates:
            if (ws.run_id, f"gate:{g}") in self._live:
                return {"kind": "finishing", "gate": g, "gate_label": GATE_LABELS[g]}
        stalled = self._stalled_gate(ws, st, gates)
        if stalled:
            return {"kind": "resume", "stage": stalled[0], "gate": stalled[1], "label": stage(stalled[0])["label"]}
        for i, s in enumerate(STAGES):
            if st["stages"][s["key"]]["status"] == "pending" and (i == 0 or st["stages"][STAGES[i - 1]["key"]]["status"] == "approved"):
                return {"kind": "next", "stage": s["key"], "label": s["label"], "agent": s["agent"]}
        return {"kind": "idle"}

    def resume(self, run_id: str) -> dict:
        """Continue a run that is not waiting on anyone: finish interrupted post-approval work or start the next stage."""
        ws = self.ws(run_id)
        st = self.status(run_id)
        now = st["now"]
        if now["kind"] == "resume":
            self._live.add((run_id, f"gate:{now['gate']}"))
            self.pool.submit(self._after_gate_safe, run_id, now["stage"], now["gate"])
            self.event(ws, f"Resumed the follow-up work for {now['gate']}", "info")
        elif now["kind"] == "next":
            self.start_stage(run_id, now["stage"])
        else:
            raise ValueError(f"Nothing to resume: the run is {now['kind']}")
        return {"ok": True, "resumed": now}

    def _team(self, ws, st: dict) -> dict:
        """Who did what and how long it took: agent working time versus time spent waiting on human review."""
        apr = ws.read_log("approvals")
        secs = lambda a, b: max(0.0, (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())  # noqa: E731
        bind = ws.run.get("agent_bindings") or {}
        rows, tot = [], {"agent_seconds": 0.0, "human_wait_seconds": 0.0, "decisions": 0, "artifacts": 0, "reviews": 0}
        for s in STAGES:
            ss = st["stages"][s["key"]]
            work = secs(ss["started"], ss["finished"]) if ss.get("started") and ss.get("finished") else 0.0
            reqs = [r for r in apr if r.get("type") == "request" and r["gate"] in s["gates"]]
            decs = [r for r in apr if r.get("type") == "decision" and r["gate"] in s["gates"]]
            wait = 0.0
            for r in reqs:
                mine = [d["timestamp"] for d in decs if d["request_id"] == r["request_id"]]
                if mine and r.get("ts"):
                    wait += secs(r["ts"], max(mine))
            roles = list(dict.fromkeys(role for g in s["gates"] for role in
                                       ((ws.latest_request(g) or {}).get("required_roles") or GATE_ROLES.get(g, []))))
            rows.append({"stage": s["key"], "label": s["label"], "agent": s["agent"],
                         "model": (bind.get(s["agent"]) or {}).get("model"), "status": ss["status"],
                         "agent_seconds": round(work, 1), "human_wait_seconds": round(wait, 1), "gates": s["gates"],
                         "humans": [{"role": ROLE_LABELS.get(r, r), "name": ws.run["approvers"].get(r, "?")} for r in roles],
                         "decisions": len(decs), "artifacts": len(ss.get("artifacts") or [])})
            tot["agent_seconds"] += work
            tot["human_wait_seconds"] += wait
            tot["decisions"] += len(decs)
            tot["artifacts"] += len(ss.get("artifacts") or [])
        tot["reviews"] = sum(1 for r in apr if r.get("type") == "artifact_review")
        tot["agent_seconds"], tot["human_wait_seconds"] = round(tot["agent_seconds"], 1), round(tot["human_wait_seconds"], 1)
        return {"stages": rows, "totals": tot}

    def status(self, run_id: str) -> dict:
        ws = self.ws(run_id)
        st = self._recover(ws, self._state(ws))
        gates = {}
        for s in STAGES:
            for g in s["gates"]:
                gs = ws.gate_status(g)
                gates[g] = {k: gs.get(k) for k in ("state", "pending_roles", "changed_artifacts", "conditions")}
                gates[g]["artifact_reviews"] = gs.get("artifact_reviews") or {}
                if gs.get("request"):
                    req = gs["request"]
                    gates[g]["request"] = {k: req.get(k) for k in ("request_id", "summary", "risk", "cost", "rollback", "options",
                                                                   "evidence", "required_roles", "artifacts", "expires",
                                                                   "artifact_sha256", "action_class", "ts")}
                    gates[g]["decisions"] = gs["decisions"]
        stale_seen = False
        for s in STAGES:
            ss = st["stages"][s["key"]]
            if any(gates[g]["state"] == "stale" for g in s["gates"]):
                ss["display"] = "stale"
                stale_seen = True
            elif stale_seen and ss["status"] in ("approved", "awaiting-approval", "done"):
                ss["display"] = "stale-upstream"
            else:
                ss["display"] = ss["status"]
        run = ws.run
        return {**st, "gates_detail": gates, "run": run, "stack": ws.stack, "stage_defs": STAGES, "gate_labels": GATE_LABELS,
                "role_labels": ROLE_LABELS, "now": self._now(ws, st, gates), "team": self._team(ws, st),
                "context_counts": {k: sum(1 for i in context_hub.items(ws) if i["stage"] in (k, "all")) for k in STAGE_KEYS}}

    def metrics(self, ws) -> dict:
        st = self._state(ws)
        apr = ws.read_log("approvals")
        reqs = [r for r in apr if r.get("type") == "request"]
        decs = [r for r in apr if r.get("type") == "decision"]
        rej = [d for d in decs if d["decision"] == "rejected"]
        first_pass = len({r["gate"] for r in reqs} - {d["gate"] for d in rej})
        blocks = sum(1 for a in ws.read_log("action-log") if a.get("phase") == "blocked")
        total = Usage()
        per = []
        for agent, u in st.get("usage", {}).items():
            total.input_tokens += u["input_tokens"]
            total.output_tokens += u["output_tokens"]
            total.cost += u["llm_cost_usd"]
            per.append([agent, ", ".join(u["models"]), u["calls"], u["tokens"], f"${u['llm_cost_usd']:.4f}"])
        g5 = next((d for d in decs if d["gate"] == "G5"), None)
        ct = "n/a"
        if g5:
            ct = str(datetime.fromisoformat(g5["timestamp"]) - datetime.fromisoformat(st["created"])).split(".")[0]
        return {"gates_requested": len(reqs), "first_pass_pct": round(100 * first_pass / max(1, len({r['gate'] for r in reqs}))),
                "rejections": len(rej), "guardrail_blocks": blocks, "tokens": total.input_tokens + total.output_tokens,
                "llm_cost": f"${total.cost:.4f}", "per_agent": per, "cycle_time": ct}

    def integrity(self, run_id: str) -> dict:
        ws = self.ws(run_id)
        return {"logs": [ws.verify_log(n) for n in ("approvals", "action-log", "decision-log", "events")]}


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


_ = (dump_yaml, sha256_file)
