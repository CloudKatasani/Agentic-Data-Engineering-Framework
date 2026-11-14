"""Enterprise deployment controls: segregation of duties, approved models, emergency stop, prompt boundary."""
import time

import pytest
from fastapi.testclient import TestClient

from adef import context_hub
from adef.api.app import app
from adef.engine.orchestrator import InputRejected
from adef.guardrails.actions import GuardrailBlocked
from adef.guardrails.scanners import redact_personal

PEOPLE = {"product_owner": "Priya Product", "data_architect": "Arun Architect", "data_steward": "Dana Steward",
          "tech_lead": "Tom Lead", "release_manager": "Rhea Release", "platform_owner": "Paul Platform",
          "security_compliance": "Sam Security"}
SOD = {"policy": {"separation_of_duties": True}}


def test_segregation_of_duties_is_enforced_from_launch_to_release(engine):
    with pytest.raises(InputRejected, match="different person"):
        engine.create_run({"client_code": "ACME", **SOD}, start=False)                # one person in every role
    with pytest.raises(InputRejected, match="Tech Lead and Release Manager"):
        engine.create_run({"client_code": "ACME", **SOD, "approvers": {**PEOPLE, "release_manager": "Tom Lead"}}, start=False)
    rid = engine.create_run({"client_code": "ACME", "autopilot": False, **SOD, "approvers": PEOPLE}, start=False)["run_id"]
    ws = engine.ws(rid)
    assert ws.run["policy"]["separation_of_duties"] is True
    engine.run_stage_sync(rid, "intake")
    paths = list(engine.status(rid)["gates_detail"]["G0"]["request"]["artifacts"])
    ok = [{"path": p, "decision": "approved"} for p in paths]
    with pytest.raises(GuardrailBlocked) as e:
        engine.review_gate(rid, "G0", "Priya Product", ["product_owner", "data_architect"], ok)
    assert e.value.rule == "separation-of-duties"
    engine.review_gate(rid, "G0", "Priya Product", ["product_owner"], ok)
    engine.review_gate(rid, "G0", "Arun Architect", ["data_architect"], ok)
    for _ in range(100):
        if engine.status(rid)["gates_detail"]["G0"]["state"] == "approved":
            break
        time.sleep(0.05)
    assert engine.status(rid)["gates_detail"]["G0"]["state"] == "approved"


def test_a_run_can_tighten_policy_but_not_loosen_it(engine):
    saved = engine.settings.load()["policy"]
    try:
        engine.settings.update("policy", {"separation_of_duties": True, "approved_providers": ["demo", "anthropic"]})
        with pytest.raises(InputRejected):                                             # asking to switch it off is ignored
            engine.create_run({"client_code": "ACME", "policy": {"separation_of_duties": False}}, start=False)
        rid = engine.create_run({"client_code": "ACME", "approvers": PEOPLE, "policy": {"approved_providers": ["demo"]}},
                                start=False)["run_id"]
        assert engine.ws(rid).run["policy"] == {"separation_of_duties": True, "approved_providers": ["demo"]}
        with pytest.raises(InputRejected, match="approved list"):
            engine.create_run({"client_code": "ACME", "approvers": PEOPLE, "policy": {"approved_providers": ["openai"]}}, start=False)
    finally:
        engine.settings.update("policy", saved)


def test_unapproved_model_provider_blocks_the_stage(engine):
    rid = engine.create_run({"client_code": "ACME", "autopilot": False, "policy": {"approved_providers": ["demo"]},
                             "agent_bindings": {"adef-orchestrator": {"provider_id": "anthropic", "model": "claude-opus-5-5"}}},
                            start=False)["run_id"]
    engine.run_stage_sync(rid, "intake")                 # orchestrator is bound to a provider outside the list
    st = engine.status(rid)
    assert st["stages"]["intake"]["status"] == "blocked" and "model-not-approved" in st["stages"]["intake"]["error"]
    ok = engine.create_run({"client_code": "ACME", "autopilot": False, "policy": {"approved_providers": ["demo"]},
                            "agent_bindings": {"adef-orchestrator": {"provider_id": "demo", "model": "adef-simulator-1"}}},
                           start=False)["run_id"]
    engine.run_stage_sync(ok, "intake")
    assert engine.status(ok)["now"]["kind"] == "review"


def test_emergency_stop_and_resume(engine):
    c = TestClient(app)
    rid = engine.create_run({"client_code": "ACME", "autopilot": False}, start=False)["run_id"]
    engine.run_stage_sync(rid, "intake")
    who = engine.ws(rid).run["approvers"]["product_owner"]
    assert c.post(f"/api/runs/{rid}/stop", json={"by": "Stranger", "reason": "because"}).status_code == 409
    assert c.post(f"/api/runs/{rid}/stop", json={"by": who, "reason": ""}).status_code == 400
    assert c.post(f"/api/runs/{rid}/stop", json={"by": who, "reason": "Wrong client scope"}).status_code == 200
    st = engine.status(rid)
    assert st["status"] == "stopped" and st["now"]["kind"] == "stopped" and st["now"]["reason"] == "Wrong client scope"
    for attempt in (lambda: engine.decide(rid, "G0", who, "product_owner", "approved"),
                    lambda: engine.start_stage(rid, "requirements")):
        with pytest.raises(GuardrailBlocked) as e:
            attempt()
        assert e.value.rule == "run-stopped"
    assert c.post(f"/api/runs/{rid}/unstop", json={"by": "Stranger"}).status_code == 409
    assert c.post(f"/api/runs/{rid}/unstop", json={"by": who}).status_code == 200
    assert engine.status(rid)["now"]["kind"] == "review"
    assert all(lg["ok"] for lg in engine.integrity(rid)["logs"])


def test_personal_identifiers_never_reach_a_prompt_or_the_context_store(engine):
    text, counts = redact_personal("a.b@corp.com, +1 (415) 555-0100, 4111-1111-1111-1111, DE89370400440532013000, 078-05-1120")
    assert counts == {"email": 1, "payment-card": 1, "bank-account": 1, "national-id": 1, "phone": 1}
    assert "corp.com" not in text and "4111" not in text
    safe = "Order 1234 5678 9012 3456 for SUB000123 on 2026-11-13, hash 08ff1ba8913887b58fa677d40ab41f7c, 62 rows"
    assert redact_personal(safe) == (safe, {})                       # ordinary numbers and ids are left alone
    rid = engine.create_run({"client_code": "ACME"}, start=False)["run_id"]
    item = context_hub.add(engine.ws(rid), "test", "note", "Contact", "Ask jane.doe@corp.com about thresholds.",
                           added_by="Demo Presenter")
    assert item["personal_data_redacted"] == 1 and "jane.doe" not in context_hub.text_of(engine.ws(rid), item)


def test_policy_settings_endpoint():
    c = TestClient(app)
    assert c.put("/api/settings/policy", json={"approved_providers": ["nope"]}).status_code == 400
    try:
        r = c.put("/api/settings/policy", json={"separation_of_duties": True, "approved_providers": ["anthropic"]})
        assert r.status_code == 200 and r.json() == {"separation_of_duties": True, "approved_providers": ["anthropic"]}
    finally:
        c.put("/api/settings/policy", json={})
