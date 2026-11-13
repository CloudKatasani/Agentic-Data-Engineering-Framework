"""Provider and model can be chosen per agent for one run at launch."""
import pytest

from adef.engine.orchestrator import InputRejected


def test_run_override_applies_to_that_run_only(engine):
    team = engine.settings.load()["agents"]["adef-orchestrator"]
    rid = engine.create_run({"client_code": "ACME", "autopilot": False,
                             "agent_bindings": {"adef-orchestrator": {"provider_id": "demo", "model": "adef-simulator-1",
                                                                      "effort": "low"}}}, start=False)["run_id"]
    ws = engine.ws(rid)
    assert ws.run["agent_overrides"] == ["adef-orchestrator"]
    assert ws.run["agent_bindings"]["adef-orchestrator"] == {"provider_id": "demo", "model": "adef-simulator-1", "effort": "low"}
    call = engine._call(ws, "adef-orchestrator")
    assert call.binding["provider_id"] == "demo" and call.binding["model"] == "adef-simulator-1" and not call.fallback_reason
    other = engine._call(ws, "adef-solution-design")            # not overridden: follows the saved team
    assert other.binding["model"] == engine.settings.load()["agents"]["adef-solution-design"]["model"]
    assert engine.settings.load()["agents"]["adef-orchestrator"] == team      # the saved team is untouched
    plain = engine.create_run({"client_code": "ACME", "autopilot": False}, start=False)["run_id"]
    assert engine.ws(plain).run["agent_overrides"] == []
    assert engine._call(engine.ws(plain), "adef-orchestrator").binding["model"] == team["model"]
    engine.run_stage_sync(rid, "intake")
    assert engine.status(rid)["now"]["kind"] == "review"


def test_run_override_is_validated(engine):
    for bad in ({"adef-nobody": {"provider_id": "demo", "model": "m"}},
                {"adef-orchestrator": {"provider_id": "nope", "model": "m"}},
                {"adef-orchestrator": {"provider_id": "demo", "model": " "}}):
        with pytest.raises(InputRejected):
            engine.create_run({"client_code": "ACME", "agent_bindings": bad}, start=False)
