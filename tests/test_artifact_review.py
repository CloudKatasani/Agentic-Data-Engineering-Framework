"""Per-artifact approve/reject at a gate."""
import pytest

from adef.guardrails.actions import GuardrailBlocked


def _intake(engine):
    rid = engine.create_run({"client_code": "ACME", "autopilot": False}, start=False)["run_id"]
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    gd = st["gates_detail"]["G0"]
    return rid, st, gd


def _by_person(st, gd):
    people = {}
    for r in gd["pending_roles"]:
        people.setdefault(st["run"]["approvers"][r], []).append(r)
    return people


def test_all_artifacts_approved_passes_gate(engine):
    rid, st, gd = _intake(engine)
    paths = list(gd["request"]["artifacts"])
    for who, roles in _by_person(st, gd).items():
        engine.review_gate(rid, "G0", who, roles, [{"path": p, "decision": "approved"} for p in paths])
    st = engine.status(rid)
    g0 = st["gates_detail"]["G0"]
    assert g0["state"] == "approved"
    for p in paths:
        assert {v["role_key"] for v in g0["artifact_reviews"][p]} == set(gd["request"]["required_roles"])
    assert all(lg["ok"] for lg in engine.integrity(rid)["logs"])


def test_one_rejected_artifact_rejects_gate_with_reason(engine):
    rid, st, gd = _intake(engine)
    paths = list(gd["request"]["artifacts"])
    who, roles = next(iter(_by_person(st, gd).items()))
    reviews = [{"path": p, "decision": "approved"} for p in paths]
    reviews[0] = {"path": paths[0], "decision": "rejected", "comment": "Scope section: limit to one region"}
    res = engine.review_gate(rid, "G0", who, roles, reviews)
    assert res["gate_state"] == "rejected"
    st = engine.status(rid)
    assert st["stages"]["intake"]["status"] == "rejected"
    assert f"- {paths[0]}: Scope section: limit to one region" in st["stages"]["intake"]["error"]
    assert st["gates_detail"]["G0"]["artifact_reviews"][paths[0]][0]["decision"] == "rejected"


def test_review_validation(engine):
    rid, st, gd = _intake(engine)
    paths = list(gd["request"]["artifacts"])
    who, roles = next(iter(_by_person(st, gd).items()))
    ok = [{"path": p, "decision": "approved"} for p in paths]
    with pytest.raises(ValueError, match="Review every artifact"):
        engine.review_gate(rid, "G0", who, roles, ok[1:] if len(ok) > 1 else [])
    with pytest.raises(ValueError, match="say what is wrong"):
        engine.review_gate(rid, "G0", who, roles, [{"path": paths[0], "decision": "rejected"}] + ok[1:])
    with pytest.raises(ValueError, match="not an artifact"):
        engine.review_gate(rid, "G0", who, roles, ok + [{"path": "x/other.md", "decision": "approved"}])
    with pytest.raises(GuardrailBlocked):
        engine.review_gate(rid, "G0", "adef-orchestrator", roles, ok)
    with pytest.raises(GuardrailBlocked):
        engine.review_gate(rid, "G0", "Someone Else", roles, ok)
    assert engine.status(rid)["gates_detail"]["G0"]["artifact_reviews"] == {}
    engine.review_gate(rid, "G0", who, roles, ok)
    with pytest.raises(ValueError, match="Already decided|not awaiting"):
        engine.review_gate(rid, "G0", who, roles, ok)


def test_review_blocked_after_drift(engine):
    rid, st, gd = _intake(engine)
    paths = list(gd["request"]["artifacts"])
    who, roles = next(iter(_by_person(st, gd).items()))
    ws = engine.ws(rid)
    (ws.root / paths[0]).write_text((ws.root / paths[0]).read_text() + "\nedited\n")
    with pytest.raises((GuardrailBlocked, ValueError)):
        engine.review_gate(rid, "G0", who, roles, [{"path": p, "decision": "approved"} for p in paths])


def test_review_endpoint(engine):
    from fastapi.testclient import TestClient
    from adef.api.app import app
    c = TestClient(app)
    rid, st, gd = _intake(engine)
    role = gd["pending_roles"][0]
    who = st["run"]["approvers"][role]
    paths = list(gd["request"]["artifacts"])
    r = c.post(f"/api/runs/{rid}/gates/G0/review", json={"approver": who, "roles": [role], "reviews": []})
    assert r.status_code == 400 and "Review every artifact" in r.json()["detail"]
    r = c.post(f"/api/runs/{rid}/gates/G0/review", json={"approver": who, "roles": [role],
                                                       "reviews": [{"path": p, "decision": "approved"} for p in paths]})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/runs/{rid}").json()["gates_detail"]["G0"]["artifact_reviews"][paths[0]][0]["role_key"] == role
