"""Cleaning up previous runs: archive or delete, always recorded, never while an agent is working."""
import io
import zipfile

from fastapi.testclient import TestClient

from adef.api.app import app
from adef.guardrails.actions import GuardrailBlocked

c = TestClient(app)
PEOPLE = {"product_owner": "Priya Product", "data_architect": "Arun Architect", "data_steward": "Dana Steward",
          "tech_lead": "Tom Lead", "release_manager": "Rhea Release", "platform_owner": "Paul Platform",
          "security_compliance": "Sam Security"}


def _run(engine, **kw):
    rid = engine.create_run({"client_code": "CLEANUP", "autopilot": False, **kw}, start=False)["run_id"]
    engine.run_stage_sync(rid, "intake")
    return rid


def test_archive_keeps_the_evidence_and_records_who_cleaned_up(engine):
    a, b = _run(engine), _run(engine)
    r = c.post("/api/runs-cleanup", json={"run_ids": [a, "RUN-1999-001"], "by": "Paul Platform"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["run_id"] for x in out["removed"]] == [a] and out["skipped"] == [{"run_id": "RUN-1999-001", "reason": "not found"}]
    ids = [x["run_id"] for x in engine.list_runs()]
    assert a not in ids and b in ids
    entry = next(x for x in c.get("/api/runs-archive").json() if x["run_id"] == a)
    assert entry["by"] == "Paul Platform" and entry["mode"] == "archive" and entry["available"] and entry["client_code"] == "CLEANUP"
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/runs-archive/{a}.zip").content))
    names = z.namelist()
    assert f"{a}/control/approvals.jsonl" in names and f"{a}/00-intake/intake-brief.md" in names
    assert c.get("/api/runs-archive/..%2Fsecrets.zip").status_code in (400, 404)
    # a cleaned-up run's number is never handed out again
    assert engine.new_run_id() not in (a, b) and int(engine.new_run_id().split("-")[-1]) > int(b.split("-")[-1])


def test_delete_is_permanent_and_needs_a_named_person(engine):
    rid = _run(engine)
    assert c.post("/api/runs-cleanup", json={"run_ids": [rid], "by": "", "mode": "delete"}).status_code == 409
    assert c.post("/api/runs-cleanup", json={"run_ids": [rid], "by": "adef-orchestrator", "mode": "delete"}).status_code == 409
    assert c.post("/api/runs-cleanup", json={"run_ids": [], "by": "Paul Platform"}).status_code == 400
    assert c.post("/api/runs-cleanup", json={"run_ids": [rid], "by": "Paul Platform", "mode": "shred"}).status_code == 400
    assert c.delete(f"/api/runs/{rid}?by=Paul Platform&mode=delete").json()["removed"][0]["mode"] == "delete"
    entry = next(x for x in c.get("/api/runs-archive").json() if x["run_id"] == rid)
    assert entry["mode"] == "delete" and not entry["available"]
    assert c.get(f"/api/runs/{rid}").status_code == 404


def test_working_and_governed_runs_are_protected(engine):
    busy = _run(engine)
    engine._live.add((busy, "requirements"))            # an agent is working on it
    try:
        out = engine.cleanup_runs([busy], "Paul Platform", "delete")
        assert out["removed"] == [] and "still working" in out["skipped"][0]["reason"]
    finally:
        engine._live.discard((busy, "requirements"))
    governed = _run(engine, approvers=PEOPLE, policy={"separation_of_duties": True})
    out = engine.cleanup_runs([governed], "Paul Platform", "delete")
    assert out["removed"] == [] and "archive it instead" in out["skipped"][0]["reason"]
    assert engine.cleanup_runs([governed, busy], "Paul Platform", "archive")["skipped"] == []
    try:
        engine.cleanup_runs([busy], "system")
        raise AssertionError("an unnamed actor cleaned up a run")
    except GuardrailBlocked as e:
        assert e.rule == "named-approver-only"
