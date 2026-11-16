"""Consistency check: deterministic cross-artifact analysis of a run.

Reviewers and approvers should not have to find by eye that a requirement was never mapped, that a
business rule has no implementation, or that an identifier was reused. This module reads the
structured artifacts a run has produced so far and reports every break in the chain

    requirement -> mapping -> logical model -> code -> test -> release

It makes no model call and no judgement of content: every finding is a fact about the artifacts.
Checks whose inputs do not exist yet are reported as `pending`, so the same check runs at every gate.
"""
from __future__ import annotations

import json
import re

from .. import questions


def _json(ws, rel):
    try:
        return ws.read_json(rel) if ws.has(rel) else None
    except ValueError:
        return None


def _yaml(ws, rel):
    try:
        return ws.read_yaml(rel) if ws.has(rel) else None
    except Exception:  # noqa: BLE001 - an unreadable file is reported as a finding by the caller
        return None


def _check(cid, title, stage, items, pending=False, warn=False, ok="No problems found."):
    items = [] if pending else items
    status = "pending" if pending else ("warn" if warn and items else "fail" if items else "pass")
    return {"id": cid, "title": title, "stage": stage, "status": status,
            "detail": "Not produced yet." if pending else (f"{len(items)} to resolve." if items else ok),
            "items": [str(i) for i in items[:12]], "more": max(0, len(items) - 12)}


def analyze(ws) -> dict:
    req = _json(ws, "01-requirements/requirements.json")
    mp = _json(ws, "02-mapping/mapping.json")
    lm = _json(ws, "03-design/logical/logical-model.json")
    man = _yaml(ws, "04-build/build-manifest.yaml")
    merge = _yaml(ws, "04-build/merge-record.yaml")
    results = sorted((ws.root / "05-test" / "results").glob("*.json")) if (ws.root / "05-test" / "results").exists() else []
    test = json.loads(results[-1].read_text()) if results else None
    checks = []

    reqs = (req or {}).get("requirements", [])
    brs = (req or {}).get("business_rules", [])
    maps = (mp or {}).get("mappings", [])
    dqs = (mp or {}).get("dq_rules", [])
    req_ids = {r["id"] for r in reqs}

    # ---- identifiers
    dup = []
    for label, items in (("requirement", reqs), ("business rule", brs), ("non-functional requirement", (req or {}).get("nfrs", [])),
                         ("mapping", maps), ("quality rule", dqs)):
        seen: dict = {}
        for i in items:
            seen[i.get("id")] = seen.get(i.get("id"), 0) + 1
        dup += [f"{label} {k} is used {n} times" for k, n in seen.items() if n > 1]
    qs = questions.collect(ws)
    seen_q: dict = {}
    for q in qs:
        seen_q[(q["stage"], q["id"])] = seen_q.get((q["stage"], q["id"]), 0) + 1
    dup += [f"open question {k[1]} ({k[0]}) is used {n} times" for k, n in seen_q.items() if n > 1]
    checks.append(_check("C01", "Every identifier is used once", "all", dup, pending=req is None and not qs,
                         ok="All identifiers are unique."))

    # ---- requirements
    checks.append(_check("C02", "Every requirement has a source and an acceptance criterion", "requirements",
                         [f"{r['id']}: " + ("no source" if not r.get("source") else "no acceptance criterion")
                          for r in reqs if not r.get("source") or not r.get("acceptance")], pending=req is None))

    # ---- requirements -> mapping
    mapped = {rid for m in maps for rid in (m.get("req_ids") or [])} | {d.get("requirement") for d in dqs}
    gap_text = json.dumps((mp or {}).get("gaps", []))
    checks.append(_check("C03", "Every requirement is covered by a mapping or a recorded gap", "mapping",
                         [f"{r['id']}: {r['text'][:80]}" for r in reqs if r["id"] not in mapped and r["id"] not in gap_text],
                         pending=mp is None))
    implemented_br = {m.get("business_rule") for m in maps} | {m.get("business_rule") for m in (lm or {}).get("metrics", [])}
    # metrics are defined with the logical model, so this is only decidable once the design exists
    checks.append(_check("C04", "Every business rule is implemented by a mapping or a metric", "design",
                         [f"{b['id']}: {b['text'][:80]}" for b in brs if b["id"] not in implemented_br],
                         pending=mp is None or lm is None))
    # keys and descriptive attributes support their entity, so an entity is in scope once any mapping into it cites a requirement
    justified = {m["target_entity"] for m in maps if m.get("req_ids")} | {d.get("entity") for d in dqs if d.get("requirement")}
    unjustified = {m["target_entity"] for m in maps} - justified
    checks.append(_check("C05", "Every mapped entity traces to a requirement that exists", "mapping",
                         [f"{m['id']} cites {rid}" for m in maps for rid in (m.get("req_ids") or []) if rid not in req_ids]
                         + [f"no mapping into {e} cites a requirement: is it in scope?" for e in sorted(unjustified)]
                         + [f"{d['id']} protects {d.get('requirement')}" for d in dqs if d.get("requirement") and d["requirement"] not in req_ids],
                         pending=mp is None))
    checks.append(_check("C06", "No low-confidence mapping is left unconfirmed", "mapping",
                         [f"{m['id']} {m['target_entity']}.{m['target_attribute']} <- {m.get('source')}" for m in maps
                          if m.get("confidence") == "low"] + [f"{m['id']} has no evidence" for m in maps if not m.get("evidence")],
                         pending=mp is None, warn=True, ok="Every mapping is medium or high confidence, with evidence."))

    # ---- mapping <-> logical model
    model_attrs = {(e["name"], a["name"]) for e in (lm or {}).get("entities", []) for a in e.get("attributes", [])}
    map_attrs = {(m["target_entity"], m["target_attribute"]) for m in maps}
    checks.append(_check("C07", "The logical model and the mapping describe the same attributes", "design",
                         [f"mapped but not in the model: {e}.{a}" for e, a in sorted(map_attrs - model_attrs)]
                         + [f"in the model but not mapped: {e}.{a}" for e, a in sorted(model_attrs - map_attrs)
                            if not re.search(r"(^valid_|^is_current$|_sk$|^load_ts$|^batch_id$)", a)],
                         pending=lm is None or mp is None))

    # ---- mapping -> code
    done = set((man or {}).get("implemented_ids") or [])
    checks.append(_check("C08", "Every quality rule is implemented in the code", "build",
                         [f"{d['id']} is not in the build manifest" for d in dqs if d["id"] not in done], pending=man is None))
    failing = [k for k, v in ((man or {}).get("checks") or {}).items() if v != "pass"]
    checks.append(_check("C09", "The build's own checks pass", "build", [f"{k} did not pass" for k in failing], pending=man is None))

    # ---- code -> test
    cases = (test or {}).get("test_cases", [])
    tested_reqs = {r for c in cases if c.get("status") == "pass" for r in (c.get("requirements") or [])}
    tested_dq = {m.group(0) for c in cases for m in [re.search(r"DQ-\d+", c.get("title", ""))] if m and c.get("status") == "pass"}
    checks.append(_check("C10", "Every must-have requirement and every quality rule has a passing test", "test",
                         [f"{r['id']} has no passing test" for r in reqs if r.get("priority", "must") == "must" and r["id"] not in tested_reqs]
                         + [f"{d['id']} has no passing test" for d in dqs if d["id"] not in tested_dq]
                         + [f"{c['id']} {c.get('title', '')[:70]}: {c.get('status')}" for c in cases if c.get("status") != "pass"],
                         pending=test is None))
    commits = []
    if test and merge and test.get("commit") != merge.get("merge_commit"):
        commits.append(f"tests ran on {str(test.get('commit'))[:10]}, but the merged commit is {str(merge.get('merge_commit'))[:10]}")
    checks.append(_check("C11", "Tests ran on the merged commit", "test", commits, pending=test is None or merge is None))

    # ---- people
    blocking = [q for q in qs if q["blocking"] and not q.get("answer")]
    checks.append(_check("C12", "Every blocking open question is answered", "all",
                         [f"{q['id']} ({q['stage']}, for {q['ask_whom']}): {q['question'][:90]}" for q in blocking], pending=False,
                         ok="No blocking question is waiting." if qs else "No open questions were raised."))

    counts = {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "fail", "warn", "pending")}
    return {"checks": checks, "counts": counts, "ok": counts["fail"] == 0}
