"""Exercise the live-LLM code path with a scripted provider (no network, no key)."""
import json

from adpe.engine.scenarios import EXPRESSIONS, SCENARIOS
from adpe.llm import router
from adpe.llm.base import LLMResult, Provider
from adpe.settings_store import AGENT_NAMES, SettingsStore
from conftest import drive

SC = SCENARIOS["utilities"]
CALLS = {"bad_once": True}


def _requirements():
    return {"outcome": "Trusted billed vs metered view.", "consumers": [{"name": n, "questions": [q]} for n, q in SC["consumers"]],
            "requirements": [{"id": r[0], "text": r[1], "acceptance": [f"Given {r[2]}, when {r[3]}, then {r[4]}."],
                              "priority": "must", "source": "request", "classification": "internal"} for r in SC["requirements"]],
            "business_rules": [{"id": b[0], "text": b[1], "example": b[2]} for b in SC["business_rules"]],
            "nfrs": [{"id": n[0], "text": n[1], "measure": n[2]} for n in SC["nfrs"]],
            "glossary_delta": [], "out_of_scope": [], "assumptions": [], "open_questions": []}


def _mapping():
    rows, n = [], 0
    for e in SC["entities"]:
        for a in e["attributes"]:
            n += 1
            rows.append({"id": f"MAP-{n:03d}", "target_entity": e["name"], "target_attribute": a["name"], "target_type": a["type"],
                         "source": a["source"], "transformation": a["transformation"],
                         "expression": EXPRESSIONS.get(("utilities", e["name"], a["name"])), "business_rule": a["business_rule"],
                         "classification": a["classification"], "confidence": "high", "req_ids": a["req_ids"], "pk": a["pk"],
                         "fk": a["fk"], "description": a["description"], "evidence": "scripted"})
    return {"sources": SC["sources"], "targets": [{"entity": e["name"], "kind": e["kind"], "grain": e["grain"], "history": e["history"],
                                                   "description": e["description"]} for e in SC["entities"]],
            "mappings": rows, "dq_rules": SC["dq"], "entity_filters": {}, "gaps": [], "assumptions": [], "open_questions": []}


def _design():
    ents = [{k: v for k, v in e.items()} for e in json.loads(json.dumps(SC["entities"]))]
    for e in ents:
        for a in e["attributes"]:
            a.pop("source"), a.pop("transformation")
    return {"model": {"name": "meter-to-cash", "description": "x", "entities": ents, "metrics": SC["metrics"]},
            "runtime_minutes": 25, "storage_gb": 40, "assumptions": [], "open_questions": []}


class Scripted(Provider):
    type = "scripted"

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None):
        assert "adpe-shared-guardrails" in system
        if "intake brief" in prompt:
            out = {"use_case": "Meter to cash", "slice_scope": "one region", "out_of_scope": [], "consumers": [{"name": "Finance", "question": "q"}],
                   "sources_hint": [], "constraints": [], "sensitivity": "restricted", "success_measure": "reconciles"}
        elif "requirements baseline" in prompt:
            if CALLS["bad_once"]:
                CALLS["bad_once"] = False
                d = _requirements()
                d["requirements"][0]["text"] = "Load bills into Snowflake"  # must be rejected and repaired
                out = d
            else:
                out = _requirements()
        elif "source-to-target mapping" in prompt:
            out = _mapping()
        elif "LOGICAL design" in prompt:
            out = _design()
        else:
            return LLMResult(text="- reviewed, no blocking issues", model=model, provider="scripted", input_tokens=50, output_tokens=10)
        return LLMResult(text="Here you go:\n```json\n" + json.dumps(out) + "\n```", model=model, provider="scripted",
                         input_tokens=len(prompt) // 4, output_tokens=500)


def test_llm_path_end_to_end(engine):
    router.CLASSES["scripted"] = Scripted
    s = SettingsStore()
    data = s.load()
    data["providers"].append({"id": "scripted", "type": "scripted", "label": "Scripted", "base_url": "", "api_key_ref": "", "options": {}})
    for a in AGENT_NAMES:
        data["agents"][a] = {"provider_id": "scripted", "model": "scripted-1", "effort": "low", "max_tokens": 4000}
    s.save(data)
    try:
        rid = engine.create_run({"client_code": "LLM", "domain_pack": "utilities"})["run_id"]
        st = drive(engine, rid)
        assert st["usage"]["adpe-intent-requirements"]["calls"] == 2  # one rejected (vendor term), one repaired
        assert "Snowflake" not in engine.ws(rid).read("01-requirements/requirements.md")
        assert "Agent review notes" in engine.ws(rid).read("04-build/build-plan.md")
    finally:
        data = s.load()
        data["providers"] = [p for p in data["providers"] if p["id"] != "scripted"]
        for a in AGENT_NAMES:
            data["agents"][a] = {"provider_id": "demo", "model": "adpe-simulator-1", "effort": "medium", "max_tokens": 16000}
        s.save(data)
