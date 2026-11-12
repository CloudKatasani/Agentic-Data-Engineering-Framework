import json

import pytest

from adef.connectors.jira import JiraClient
from conftest import drive


@pytest.mark.parametrize("domain,stack,project", [("utilities", "example-a", "UTIL"), ("telco", "example-b", "TEL"),
                                                  ("financial-services", "gcp-bigquery", "FIN"), ("retail", "aws-redshift", "RET")])
def test_full_lifecycle_simulator(engine, domain, stack, project):
    issues = JiraClient({"mode": "demo"}).search(f"project = {project}")
    rid = engine.create_run({"client_code": "ACME", "domain_pack": domain, "stack_profile": stack, "jira_issues": issues})["run_id"]
    st = drive(engine, rid)
    ws = engine.ws(rid)
    assert all(s["status"] in ("approved", "done") for s in st["stages"].values())
    res = json.loads(sorted((ws.root / "05-test" / "results").glob("*.json"))[-1].read_text())
    assert res["summary"]["fail"] == 0
    trace = ws.read("final/traceability-matrix.csv").splitlines()[1:]
    assert trace and all(line.endswith(",pass") for line in trace)
    assert all(lg["ok"] for lg in engine.integrity(rid)["logs"])
    assert len(list((ws.root / "final" / "exports").iterdir())) >= 15
    assert "UTIL-8" not in ws.read("01-requirements/requirements.md") or domain != "utilities"
    if domain == "utilities":
        assert "Untrusted content findings" in ws.read("00-intake/intake-brief.md")


def test_secret_in_request_rejected(engine):
    from adef.engine.orchestrator import InputRejected
    with pytest.raises(InputRejected):
        engine.create_run({"request": "connect with password: Hunter2Hunter2"}, start=False)


def test_rejection_and_rework(engine):
    rid = engine.create_run({"client_code": "ACME", "autopilot": False}, start=False)["run_id"]
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    engine.decide(rid, "G0", st["run"]["approvers"]["product_owner"], "product_owner", "rejected",
                  "00-intake/intake-brief.md slice scope: limit to one region")
    assert engine.status(rid)["stages"]["intake"]["status"] == "rejected"
    engine.run_stage_sync(rid, "intake", feedback="limit to one region")
    assert engine.status(rid)["stages"]["intake"]["status"] == "awaiting-approval"
