"""A run always says what it is doing and who it waits on, and can always be moved on."""
import json
import time

import pytest

from adef.engine import agent_runtime
from adef.engine.agent_runtime import AgentCall
from adef.llm.base import LLMError, LLMResult


def _set_stage(engine, rid, key, **kw):
    ws = engine.ws(rid)
    engine._update(ws, lambda s: s["stages"][key].update(**kw))


def test_now_tracks_who_the_run_waits_on(engine):
    rid = engine.create_run({"client_code": "ACME", "autopilot": False}, start=False)["run_id"]
    assert engine.status(rid)["now"] == {"kind": "next", "stage": "intake", "label": "Intake", "agent": "adef-orchestrator"}
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    assert st["now"]["kind"] == "review" and st["now"]["gate"] == "G0"
    assert {w["role"] for w in st["now"]["waiting_on"]} == {"Product Owner", "Data Architect"}
    for role in st["gates_detail"]["G0"]["pending_roles"]:
        engine.decide(rid, "G0", st["run"]["approvers"][role], role, "approved")
    for _ in range(100):
        st = engine.status(rid)
        if st["now"]["kind"] == "next":
            break
        time.sleep(0.05)
    assert st["now"]["stage"] == "requirements"       # autopilot off: the run says so instead of looking stuck
    engine.resume(rid)
    for _ in range(200):
        st = engine.status(rid)
        if st["now"]["kind"] == "review":
            break
        time.sleep(0.05)
    assert st["now"]["gate"] == "G1"
    team = st["team"]
    assert team["totals"]["decisions"] == 2 and team["stages"][0]["humans"]
    with pytest.raises(ValueError):
        engine.resume(rid)                              # waiting on a person: nothing to resume


def test_stage_orphaned_by_restart_becomes_retryable(engine):
    rid = engine.create_run({"client_code": "ACME", "autopilot": False}, start=False)["run_id"]
    _set_stage(engine, rid, "intake", status="running", started="2026-01-01T00:00:00+00:00")   # as left by a killed server
    st = engine.status(rid)
    assert st["stages"]["intake"]["status"] == "failed" and "Interrupted" in st["stages"]["intake"]["error"]
    assert st["now"]["kind"] == "failed"
    engine.start_stage(rid, "intake")
    for _ in range(200):
        st = engine.status(rid)
        if st["now"]["kind"] == "review":
            break
        time.sleep(0.05)
    assert st["now"]["gate"] == "G0"


def test_interrupted_post_approval_work_can_be_resumed(engine):
    rid = engine.create_run({"client_code": "ACME", "autopilot": True}, start=False)["run_id"]
    engine.run_stage_sync(rid, "intake")
    ws = engine.ws(rid)
    st = engine.status(rid)
    for role in st["gates_detail"]["G0"]["pending_roles"]:       # approvals recorded, follow-up never ran
        ws.decide("G0", st["run"]["approvers"][role], role, "approved")
    st = engine.status(rid)
    assert st["now"]["kind"] == "resume" and st["now"]["gate"] == "G0"
    engine.resume(rid)
    for _ in range(200):
        st = engine.status(rid)
        if st["now"].get("gate") == "G1":
            break
        time.sleep(0.05)
    assert st["stages"]["intake"]["status"] == "approved" and st["now"]["kind"] == "review"


class _Slow:
    type = "anthropic"

    def __init__(self, seconds):
        self.seconds = seconds

    def complete(self, **kw):
        time.sleep(self.seconds)
        return LLMResult(text=json.dumps({"ok": True}), model=kw["model"], provider="anthropic", input_tokens=1, output_tokens=1)


def _call(provider, log):
    return AgentCall("adef-orchestrator", provider, {"model": "m", "provider": {"label": "P"}}, log)


def test_slow_model_call_reports_a_heartbeat(monkeypatch):
    monkeypatch.setattr(agent_runtime, "HEARTBEAT_SECONDS", 0.05)
    lines = []
    assert _call(_Slow(0.3), lines.append).json("x") == {"ok": True}
    assert any("still working" in line for line in lines)


def test_model_call_has_a_time_limit(monkeypatch):
    monkeypatch.setattr(agent_runtime, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(agent_runtime, "model_timeout", lambda: 0)
    with pytest.raises(LLMError, match="no answer"):
        _call(_Slow(2), lambda _t: None).text("x")
