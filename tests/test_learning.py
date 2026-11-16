"""Consistency check, open questions answered by people, and team standards learned from reviews."""
import json

import pytest
from fastapi.testclient import TestClient

from adef import context_hub, questions
from adef.api.app import app
from adef.connectors.jira import JiraClient
from adef.engine import analyze
from adef.engine.scenarios import SCENARIOS
from conftest import drive

c = TestClient(app)
WHO = "Demo Presenter"


def _run(engine, **kw):
    return engine.create_run({"client_code": "ACME", "domain_pack": "telco", "autopilot": False, **kw}, start=False)["run_id"]


def _approve(engine, rid, gate):
    for role in engine.status(rid)["gates_detail"][gate]["pending_roles"]:
        engine.decide(rid, gate, WHO, role, "approved")


def _to_mapping(engine, rid):
    for key, gate in (("intake", "G0"), ("requirements", "G1")):
        engine.run_stage_sync(rid, key)
        _approve(engine, rid, gate)
    engine.run_stage_sync(rid, "mapping")


# ------------------------------------------------------------------ consistency check
def test_checks_are_pending_until_their_inputs_exist(engine):
    rid = _run(engine)
    res = engine.status(rid)["consistency"]
    assert res["ok"] and res["counts"]["fail"] == 0
    assert {x["id"]: x["status"] for x in res["checks"]}["C03"] == "pending"
    assert [x["id"] for x in res["checks"]] == [f"C{n:02d}" for n in range(1, 13)]


@pytest.mark.parametrize("domain,project", [("utilities", "UTIL"), ("telco", "TEL"), ("financial-services", "FIN"), ("retail", "RET")])
def test_a_finished_run_is_consistent_end_to_end(engine, domain, project):
    issues = JiraClient({"mode": "demo"}).search(f"project = {project}")
    rid = engine.create_run({"client_code": "ACME", "domain_pack": domain, "jira_issues": issues})["run_id"]
    res = drive(engine, rid)["consistency"]
    assert res["counts"] == {"pass": 12, "fail": 0, "warn": 0, "pending": 0}, [x for x in res["checks"] if x["status"] != "pass"]


def test_breaks_in_the_chain_are_reported(engine):
    rid = _run(engine)
    _to_mapping(engine, rid)
    ws = engine.ws(rid)
    assert analyze.analyze(ws)["counts"]["fail"] == 0
    mp = ws.read_json("02-mapping/mapping.json")
    reqs = ws.read_json("01-requirements/requirements.json")
    target = reqs["requirements"][0]["id"]
    for m in mp["mappings"]:                                   # nothing covers the first requirement any more
        m["req_ids"] = [r for r in m.get("req_ids") or [] if r != target]
    mp["dq_rules"] = [d for d in mp["dq_rules"] if d.get("requirement") != target]
    mp["mappings"][0]["req_ids"] = ["REQ-999"]                 # a requirement that does not exist
    mp["mappings"][1]["id"] = mp["mappings"][0]["id"]          # a reused identifier
    mp["mappings"][2]["confidence"] = "low"
    ws._raw_write("02-mapping/mapping.json", json.dumps(mp))
    by_id = {x["id"]: x for x in analyze.analyze(ws)["checks"]}
    assert by_id["C01"]["status"] == "fail" and "used 2 times" in by_id["C01"]["items"][0]
    assert by_id["C03"]["status"] == "fail" and by_id["C03"]["items"][0].startswith(target)
    assert by_id["C05"]["status"] == "fail" and any("REQ-999" in i for i in by_id["C05"]["items"])
    assert by_id["C06"]["status"] == "warn"                    # a person confirms; it does not block
    assert by_id["C08"]["status"] == "pending"                 # nothing built yet


def test_every_scenario_traces_requirements_and_rules():
    """The built-in scenarios are the worked example agents are measured against: they must be traceable."""
    for pack, sc in SCENARIOS.items():
        attrs = [a for e in sc["entities"] for a in e["attributes"]]
        cited = {r for a in attrs for r in a["req_ids"]} | {d["requirement"] for d in sc["dq"]}
        rules = {a["business_rule"] for a in attrs} | {m["business_rule"] for m in sc["metrics"]}
        assert {r[0] for r in sc["requirements"]} <= cited, pack
        assert {b[0] for b in sc["business_rules"]} <= rules, pack
        assert all(any(a["req_ids"] for a in e["attributes"]) for e in sc["entities"]), pack


# ------------------------------------------------------------------ open questions
def test_open_questions_have_unique_ids_and_can_be_answered(engine):
    issues = JiraClient({"mode": "demo"}).search("project = TEL")
    rid = _run(engine, jira_issues=issues)
    engine.run_stage_sync(rid, "intake")
    _approve(engine, rid, "G0")
    engine.run_stage_sync(rid, "requirements")
    qs = engine.status(rid)["questions"]
    assert qs and len({q["key"] for q in qs}) == len(qs)
    assert len({(q["stage"], q["id"]) for q in qs}) == len(qs)
    q = qs[0]

    r = c.post(f"/api/runs/{rid}/questions/answer", json={"key": q["key"], "answer": "Yes, keep it out of this slice.", "by": "adef-requirements"})
    assert r.status_code == 400                                 # an agent cannot answer for a person
    assert c.post(f"/api/runs/{rid}/questions/answer", json={"key": "nope:OQ-1", "answer": "x y", "by": WHO}).status_code == 404
    r = c.post(f"/api/runs/{rid}/questions/answer", json={"key": q["key"], "answer": "Yes, keep it out of this slice.", "by": WHO})
    assert r.status_code == 200, r.text
    first = r.json()["answer"]["context_id"]

    ws = engine.ws(rid)
    got = next(x for x in questions.collect(ws) if x["key"] == q["key"])
    assert got["answer"]["by"] == WHO and got["answer"]["answer"] == "Yes, keep it out of this slice."
    block = context_hub.prompt_block(ws, "mapping")[0]             # the answer reaches every later agent
    assert first in block and "keep it out of this slice" in block and "Answer to an open question" in block

    r = c.post(f"/api/runs/{rid}/questions/answer", json={"key": q["key"], "answer": "No: bring it into this slice.", "by": WHO})
    second = r.json()["answer"]["context_id"]
    block = context_hub.prompt_block(ws, "mapping")[0]             # a corrected answer replaces the earlier one
    assert second != first and "bring it into this slice" in block and "keep it out of this slice" not in block
    assert questions.summary(ws)["open"] == len(qs) - 1


def test_an_unanswered_blocking_question_fails_the_check(engine):
    rid = _run(engine)
    engine.run_stage_sync(rid, "intake")
    ws = engine.ws(rid)
    path = sorted((ws.root / "control" / "handoffs").glob("*.yaml"))[-1]
    from adef.util import dump_yaml, load_yaml
    env = load_yaml(path.read_text())
    env["open_questions"] = [{"id": "OQ-900", "question": "Which calendar defines a month?", "blocking": True, "ask_whom": "Product Owner"}]
    path.write_text(dump_yaml(env))
    c12 = analyze.analyze(ws)["checks"][-1]
    assert c12["id"] == "C12" and c12["status"] == "fail" and "OQ-900" in c12["items"][0]
    questions.answer(ws, "intake:OQ-900", "The billing calendar.", WHO)
    assert analyze.analyze(ws)["checks"][-1]["status"] == "pass"


# ------------------------------------------------------------------ team standards
def test_team_standards_reach_the_right_agent_in_new_runs(engine):
    bad = c.post("/api/standards", json={"stage": "design", "title": "Keys", "text": "Surrogate keys end in _sk.", "added_by": "adef-design"})
    assert bad.status_code == 400                               # only a named person teaches the team
    assert c.post("/api/standards", json={"stage": "nowhere", "title": "x", "text": "long enough text", "added_by": WHO}).status_code == 400
    leak = c.post("/api/standards", json={"stage": "build", "title": "Conn", "added_by": WHO,
                                          "text": "Connect with password = 'Sup3rSecretValue99' on the warehouse."})
    assert leak.status_code == 400
    r = c.post("/api/standards", json={"stage": "design", "title": "Surrogate key naming", "added_by": WHO,
                                       "text": "Every surrogate key is named <entity>_sk and is never exposed to consumers.",
                                       "source": "Learned from a rework in RUN-1"})
    assert r.status_code == 200, r.text
    everywhere = c.post("/api/standards", json={"stage": "all", "title": "Language", "added_by": WHO,
                                                "text": "Write every document in British English."}).json()
    sid = r.json()["id"]
    try:
        assert sid.startswith("STD-") and sid in [s["id"] for s in c.get("/api/settings").json()["standards"]]
        rid = _run(engine)
        ws = engine.ws(rid)
        design, mapping = context_hub.prompt_block(ws, "design")[0], context_hub.prompt_block(ws, "mapping")[0]
        assert "named <entity>_sk" in design and "Team standard" in design
        assert "named <entity>_sk" not in mapping and "British English" in mapping and "British English" in design
    finally:
        assert c.delete(f"/api/standards/{sid}").status_code == 200
        c.delete(f"/api/standards/{everywhere['id']}")
    assert c.delete(f"/api/standards/{sid}").status_code == 404
    assert "named <entity>_sk" not in context_hub.prompt_block(engine.ws(_run(engine)), "design")[0]
