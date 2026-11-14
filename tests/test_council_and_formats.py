"""Council of three reviews every stage output before handover; documents can be handed over in other formats."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from adef.api.app import app
from adef.engine import council, formats
from adef.engine.agent_runtime import AgentCall
from adef.engine.context import StageCtx, StageOutput
from adef.engine.orchestrator import InputRejected
from adef.engine.stages import stage
from adef.llm.base import LLMResult

c = TestClient(app)
DEMO_AGENT = {"agent_bindings": {"adef-orchestrator": {"provider_id": "demo", "model": "adef-simulator-1"}}}


def _run(engine, **kw):
    return engine.create_run({"client_code": "ACME", "autopilot": False, **kw}, start=False)["run_id"]


# ----------------------------------------------------------------------------- council
def test_every_stage_output_is_reviewed_and_the_report_goes_to_the_gate(engine):
    rid = _run(engine)
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    summary = st["stages"]["intake"]["council"]
    assert summary["outcome"] == "passed" and summary["approvals"] == 3 and len(summary["members"]) == 3
    assert {m["served_by"] for m in summary["members"]} == {"simulated"}         # no keys here: labelled, not hidden
    assert "00-intake/council-review.md" in st["gates_detail"]["G0"]["request"]["artifacts"]
    report = engine.ws(rid).read("00-intake/council-review.md")
    assert "structural checks only" in report and "advisory" in report and "Outcome: Passed" in report
    assert st["now"]["kind"] == "review"                                         # a person still decides the gate


def test_council_can_be_switched_off_for_a_run(engine):
    rid = _run(engine, council_enabled=False)
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    assert st["stages"]["intake"]["council"] is None
    assert "00-intake/council-review.md" not in st["gates_detail"]["G0"]["request"]["artifacts"]


def test_structural_reviewer_catches_unfinished_output(engine):
    rid = _run(engine)
    ws = engine.ws(rid)
    ws._raw_write("00-intake/x.md", "# Brief\n\nScope: TODO\n")
    ws._raw_write("00-intake/y.json", "{not json")
    out = StageOutput(artifacts=["00-intake/x.md", "00-intake/y.json", "00-intake/missing.md"], summary="")
    r0 = council._structural(0, ws, out.artifacts, out)
    assert r0["verdict"] == "revise" and {f["artifact"] for f in r0["findings"]} == set(out.artifacts)
    assert any("no summary" in f["issue"] for f in council._structural(2, ws, out.artifacts, out)["findings"])


class _Reviewer:
    """A fake live model that votes as scripted, per council seat and per round."""
    type = "anthropic"

    def __init__(self, script):
        self.script, self.calls = script, 0

    def complete(self, **kw):
        verdict = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        body = {"verdict": verdict, "score": 4 if verdict == "approve" else 2, "summary": f"{verdict} it",
                "findings": [] if verdict == "approve" else [{"artifact": "00-intake/doc.md", "severity": "major",
                                                              "issue": "Scope section is missing", "suggestion": "Add the scope"}]}
        return LLMResult(text=json.dumps(body), model=kw["model"], provider="anthropic", input_tokens=10, output_tokens=5)


def _live_council(monkeypatch, scripts):
    seats = iter([_Reviewer(s) for s in scripts])
    built = {}

    def build(p):                      # one fake model per council seat, kept across review rounds
        if p["id"] not in built:
            built[p["id"]] = next(seats)
        return built[p["id"]]

    monkeypatch.setattr(council, "provider_ready", lambda p: True)
    monkeypatch.setattr(council, "build_provider", build)
    return built


def test_two_of_three_must_approve_and_the_agent_revises_from_the_findings(engine, monkeypatch):
    _live_council(monkeypatch, [["revise", "approve"], ["revise", "approve"], ["approve"]])
    rid = _run(engine)
    ws = engine.ws(rid)
    s = stage("intake")
    call = AgentCall("adef-orchestrator", _Reviewer(["approve"]), {"model": "m", "provider": {"label": "P", "type": "anthropic"}},
                     lambda _t: None)                                          # a live (not simulated) stage agent
    ctx = StageCtx(ws=ws, call=call, scenario={}, log=lambda _t: None)
    seen = []

    def runner(cx):
        seen.append(cx.feedback)
        cx.write("00-intake/doc.md", "# Intake\n\n" + ("Scope: one region.\n" if cx.feedback else "Draft.\n"))
        return StageOutput(artifacts=["00-intake/doc.md"], summary="Intake brief ready.")

    out, reviews = engine._council(ws, s, ctx, runner, runner(ctx), call)
    assert [r["outcome"] for r in reviews] == ["not-satisfied", "passed"] and [r["approvals"] for r in reviews] == [1, 3]
    assert seen[0] is None and "Scope section is missing" in seen[1] and "Fix: Add the scope" in seen[1]
    assert "Scope: one region" in ws.read("00-intake/doc.md")                   # the revised output is what is handed over
    report = ws.read("00-intake/council-review.md")
    assert "after 1 revision" in report and "## Round 2" in report and "00-intake/council-review.md" in out.artifacts
    assert council.summary(reviews) == {"outcome": "passed", "approvals": 3, "rounds": 2, "major_findings": 0,
                                        "members": council.summary(reviews)["members"]}
    assert reviews[0]["usage"]["calls"] == 3 and reviews[0]["usage"]["tokens"] == 45


def test_unresolved_findings_reach_the_human_approver(engine, monkeypatch):
    _live_council(monkeypatch, [["revise"], ["revise"], ["approve"]])
    rid = _run(engine)                           # the stage agent itself is simulated here, so it cannot revise
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    assert st["stages"]["intake"]["council"]["outcome"] == "not-satisfied" and st["stages"]["intake"]["council"]["rounds"] == 1
    assert st["now"]["kind"] == "review"         # not blocked: the named approver sees the findings and decides
    assert "did not pass this output" in engine.ws(rid).read("00-intake/council-review.md")
    assert st["usage"]["council"]["calls"] == 3


def test_reviewers_outside_the_approved_model_list_abstain(engine):
    rid = _run(engine, policy={"approved_providers": ["demo"]}, **DEMO_AGENT)
    engine.run_stage_sync(rid, "intake")
    summary = engine.status(rid)["stages"]["intake"]["council"]
    assert summary["outcome"] == "no-quorum" and {m["verdict"] for m in summary["members"]} == {"abstain"}
    assert "No quorum" in engine.ws(rid).read("00-intake/council-review.md")


def test_council_settings_endpoint():
    saved = c.get("/api/settings").json()["council"]
    assert len(saved["members"]) == 3 and saved["enabled"] is True
    assert c.put("/api/settings/council", json={"members": saved["members"][:2]}).status_code == 400
    bad = [dict(saved["members"][0], provider_id="nope")] + saved["members"][1:]
    assert c.put("/api/settings/council", json={"members": bad}).status_code == 400
    try:
        r = c.put("/api/settings/council", json={"enabled": False, "max_revisions": 9, "members": saved["members"]})
        assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["max_revisions"] == 3
    finally:
        c.put("/api/settings/council", json=saved)


# ----------------------------------------------------------------------------- output formats
MD = "# Title\n\nSome **bold** and `code` text.\n\n| ID | Rule |\n|---|---|\n| BR-1 | A & B |\n\n- one\n- two\n\n```\nSELECT 1;\n```\n"


def test_markdown_renders_to_html_and_word_deterministically():
    page = formats.to_html(MD, "T")
    assert "<h1>Title</h1>" in page and "<strong>bold</strong>" in page and "<td>A &amp; B</td>" in page and "<li>two</li>" in page
    doc = formats.to_docx(MD, "T")
    assert doc == formats.to_docx(MD, "T")                                       # same input, same bytes (hash-bound approvals)
    z = zipfile.ZipFile(io.BytesIO(doc))
    xml = z.read("word/document.xml").decode()
    assert {"[Content_Types].xml", "word/styles.xml", "_rels/.rels"} <= set(z.namelist())
    assert 'w:val="Heading1"' in xml and "A &amp; B" in xml and "<w:tbl>" in xml and "SELECT 1;" in xml
    import xml.dom.minidom
    for part in ("word/document.xml", "word/styles.xml", "[Content_Types].xml", "docProps/core.xml"):
        xml.dom.minidom.parseString(z.read(part))
    with pytest.raises(ValueError):
        formats.render(MD, "pdf", "T")


def test_stage_hands_over_documents_in_the_chosen_format(engine):
    with pytest.raises(InputRejected):
        _run(engine, output_formats={"intake": "pdf"})
    rid = _run(engine, output_formats={"intake": "docx"})
    engine.run_stage_sync(rid, "intake")
    arts = engine.status(rid)["gates_detail"]["G0"]["request"]["artifacts"]
    assert "00-intake/intake-brief.md" in arts and "00-intake/intake-brief.docx" in arts and "00-intake/council-review.docx" in arts
    assert arts["00-intake/intake-brief.docx"] == engine.ws(rid).sha("00-intake/intake-brief.docx")
    raw = c.get(f"/api/runs/{rid}/download?path=00-intake/intake-brief.docx")
    assert raw.status_code == 200 and zipfile.ZipFile(io.BytesIO(raw.content)).read("word/document.xml")
    assert all(lg["ok"] for lg in engine.integrity(rid)["logs"])


def test_format_can_be_chosen_per_stage_before_it_runs_and_on_demand(engine):
    rid = _run(engine)
    assert c.put(f"/api/runs/{rid}/stages/intake/output-format", json={"format": "pdf"}).status_code == 400
    assert c.put(f"/api/runs/{rid}/stages/nowhere/output-format", json={"format": "html"}).status_code == 400
    assert c.put(f"/api/runs/{rid}/stages/intake/output-format", json={"format": "html"}).json() == {"intake": "html"}
    engine.run_stage_sync(rid, "intake")
    st = engine.status(rid)
    assert "00-intake/intake-brief.html" in st["gates_detail"]["G0"]["request"]["artifacts"] and st["output_formats"] == {"intake": "html"}
    assert "<h1>" in engine.ws(rid).read("00-intake/intake-brief.html")
    word = c.get(f"/api/runs/{rid}/file-as?path=00-intake/backlog.md&format=docx")       # any document, any format, no change to the run
    assert word.status_code == 200 and "backlog.docx" in word.headers["content-disposition"]
    assert c.get(f"/api/runs/{rid}/file-as?path=00-intake/intake.json&format=html").status_code == 404
    assert set(c.get("/api/catalog").json()["output_formats"]) == {"markdown", "html", "docx"}
