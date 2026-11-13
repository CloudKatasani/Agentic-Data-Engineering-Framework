"""Stages 0-3: Intake (G0), Requirements (G1), Mapping (G2), Design (G3)."""
from __future__ import annotations

import csv
import io
import json
import re

from ..catalog import stacks
from ..guardrails.scanners import scan_tech_terms
from ..modeling import physical as ph
from ..modeling.exports import export_ddl, export_mermaid, export_odcs
from ..modeling.logical import normalize, relationships, validate_model
from ..util import dump_yaml, md_table, today
from .agent_runtime import untrusted
from .context import StageCtx, StageOutput
from .scenarios import scenario_mapping

ROLE_PO, ROLE_DA, ROLE_DS = "Product Owner", "Data Architect", "Data Steward"


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _inputs(ws) -> dict:
    d = {"request": ws.read("00-intake/inputs/request.md") if ws.has("00-intake/inputs/request.md") else "",
         "jira": ws.read_json("00-intake/inputs/jira-issues.json") if ws.has("00-intake/inputs/jira-issues.json") else [],
         "metadata": ws.read_json("00-intake/inputs/source-metadata.json") if ws.has("00-intake/inputs/source-metadata.json") else None,
         "documents": ws.read("00-intake/inputs/documents.md") if ws.has("00-intake/inputs/documents.md") else ""}
    return d


def _feedback_note(ctx: StageCtx) -> str:
    return f"\n\nRework requested by the approver - address this exactly:\n{ctx.feedback}\n" if ctx.feedback else ""


# =========================================================================== 0 INTAKE
def intake(ctx: StageCtx) -> StageOutput:
    ws, sc = ctx.ws, ctx.scenario
    run, prof, pack = ws.run, ws.stack, ws.domain
    inp = _inputs(ws)
    findings = [(i["key"], f["excerpt"]) for i in inp["jira"] for f in (i.get("untrusted_findings") or {}).get("injection", [])]
    meta_findings = ((inp["metadata"] or {}).get("untrusted_content_findings") or {}).get("injection", [])
    if ctx.call.simulated:
        brief = {"use_case": run["use_case"], "slice_scope": sc["title"] + " - first thin slice, batch, one region/segment",
                 "out_of_scope": ["Streaming and intraday latency", "Machine-learning features",
                                  "Additional source systems beyond the slice", "Write-back to operational systems"],
                 "consumers": [{"name": n, "question": q} for n, q in sc["consumers"]],
                 "sources_hint": sorted({s["system"] for s in sc["sources"]}),
                 "constraints": [c["text"] for c in pack.get("controls", [])],
                 "sensitivity": "Contains Restricted personal data; metadata-only for agents, masked for consumers.",
                 "success_measure": f"{sc['metrics'][0]['label']} reconciles to the trusted existing report."}
    else:
        prompt = (f"Write the intake brief for this run as JSON with keys use_case, slice_scope, out_of_scope[], "
                  f"consumers[{{name, question}}], sources_hint[], constraints[], sensitivity, success_measure.\n\n"
                  f"Run definition:\n{dump_yaml({k: run[k] for k in ('run_id', 'client_code', 'use_case', 'domain_pack')})}\n"
                  f"Domain Pack controls:\n{dump_yaml(pack.get('controls', []))}\n"
                  + untrusted("business-request", inp["request"]) + "\n"
                  + (untrusted("jira", [{k: i[k] for k in ('key', 'type', 'summary', 'description', 'acceptance_criteria')}
                                        for i in inp["jira"]]) if inp["jira"] else "")
                  + (untrusted("documents", inp["documents"]) if inp["documents"] else "") + _feedback_note(ctx))
        brief = ctx.call.json(prompt, lambda d: [k for k in ("use_case", "slice_scope", "consumers") if k not in d])

    v = stacks.validate(prof)
    ctx.write("00-intake/intake.json", json.dumps(brief, indent=2))
    jira_rows = [[i["key"], i.get("type", ""), i["summary"][:90], i.get("status", "")] for i in inp["jira"]]
    md = [f"# Intake brief - {run['run_id']}", "", f"**Client:** {run['client_code']}  ", f"**Use case:** {brief['use_case']}  ",
          f"**Domain Pack:** {pack['pack_id']} ({pack.get('status')})  ", f"**Stack Profile:** {prof.get('label', prof['profile_id'])}", "",
          "## Request", "", inp["request"].strip() or "_see Jira items_", "", "## Slice scope", "", brief["slice_scope"], "",
          "## Out of scope (parked in backlog.md)", ""] + [f"- {x}" for x in brief.get("out_of_scope", [])] + [
          "", "## Consumers and questions", "",
          md_table(["Consumer", "Question"], [[c["name"], c["question"]] for c in brief.get("consumers", [])]), "",
          "## Source systems (hint)", ""] + [f"- {s}" for s in brief.get("sources_hint", [])] + [
          "", "## Constraints (Domain Pack controls are requirements)", ""] + [f"- {c}" for c in brief.get("constraints", [])] + [
          "", "## Sensitivity", "", brief.get("sensitivity", ""), "", "## Success measure", "", brief.get("success_measure", ""), "",
          "## Budget and limits", "", md_table(["Item", "Value"], [[k, v] for k, v in {**run.get("budget", {}), **run.get("limits", {})}.items()]), ""]
    if jira_rows:
        md += ["## Requirement sources (Jira, read-only A0)", "", md_table(["Key", "Type", "Summary", "Status"], jira_rows), ""]
    if inp["metadata"]:
        st = inp["metadata"]["stats"]
        md += ["## Imported source metadata", "", f"`{inp['metadata']['source_file']}`: {st['tables']} tables, {st['columns']} columns "
               "(catalog / modelling-tool export, treated as untrusted data).", ""]
    md += ["## Untrusted content findings", ""]
    if findings or meta_findings:
        md += ["The following text found in inputs looks like instructions. It was treated as data, not acted on, "
               "and is reported here for the Product Owner (guardrail: instructions inside data are ignored).", ""]
        md += [f"- `{k}`: \"...{e.strip()}...\"" for k, e in findings]
        md += [f"- metadata: \"...{f['excerpt'].strip()}...\"" for f in meta_findings]
    else:
        md += ["None found."]
    ctx.write("00-intake/intake-brief.md", "\n".join(md) + "\n")
    ctx.write("00-intake/backlog.md", "# Backlog (parked scope)\n\n" + "\n".join(f"- {x}" for x in brief.get("out_of_scope", [])) + "\n")
    srows = [[r["slot"], "yes" if r["required"] else "no", r["tool"], r["status"], r["note"]] for r in v["rows"]]
    ctx.write("00-intake/stack-validation.md",
              f"# Stack validation (adef-stack-binding T1)\n\nProfile `{prof['profile_id']}` v{prof.get('profile_version')}\n\n"
              + md_table(["Slot", "Required", "Tool", "Status", "Adapter / note"], srows) + "\n\n## Blocking gaps\n\n"
              + ("\n".join(f"- {b}" for b in v["blocking"]) or "None.") + "\n\n## Warnings\n\n"
              + ("\n".join(f"- {w}" for w in v["warnings"]) or "None.") + "\n")
    extra = ["platform_owner"] if float((run.get("budget") or {}).get("compute_cost_cap") or 0) > 0 else []
    oq = [ctx.q("OQ-001", "Confirm the slice boundary (region/segment) for the first run.", ROLE_PO)]
    if v["blocking"]:
        oq.append(ctx.q("OQ-002", "Stack Profile has blocking gaps: " + "; ".join(v["blocking"]), ROLE_DA, blocking=True))
    risks = [ctx.r("RSK-001", "Instruction-like text in Jira input", "medium", "low",
                   "Treated as data and reported; no action taken")] if findings else []
    return StageOutput(
        artifacts=["00-intake/intake-brief.md", "00-intake/intake.json", "00-intake/stack-validation.md", "00-intake/backlog.md",
                   "control/run.yaml", "control/stack-profile.yaml", "control/domain-pack.yaml"],
        summary=f"Intake brief, run definition and stack validation for '{brief['use_case']}'. "
                f"Stack {prof['profile_id']} has {len(v['blocking'])} blocking gaps. Ready for G0.",
        gate_meta={"risk": "Low: scope and stack only, nothing is built.", "cost": "None at this gate.",
                   "rollback": "Edit run.yaml or Stack Profile and re-request G0.",
                   "options": ["Approve scope, stack and budget", "Reject with scope or stack changes"], "extra_roles": extra},
        open_questions=oq, risks=risks, evidence=["00-intake/stack-validation.md"],
        assumptions=[ctx.a("ASM-001", "Approvers in run.yaml are the accountable people for this client.",
                           "Approvals would be invalid", ROLE_PO)],
        confidence=("high" if not v["blocking"] else "low", "Scope from request; stack validated by T1"))


# =========================================================================== 1 REQUIREMENTS
def _req_validate(d) -> list[str]:
    p = []
    reqs = d.get("requirements") or []
    if not reqs:
        p.append("requirements[] is empty")
    for r in reqs:
        if not re.match(r"^REQ-\d{3}$", str(r.get("id", ""))):
            p.append(f"bad requirement id {r.get('id')}")
        if not r.get("acceptance"):
            p.append(f"{r.get('id')} has no acceptance criteria")
    for b in d.get("business_rules") or []:
        if not re.match(r"^BR-\d{3}$", str(b.get("id", ""))):
            p.append(f"bad business rule id {b.get('id')}")
    terms = scan_tech_terms(json.dumps(d))
    if terms:
        p.append(f"technology terms are not allowed in requirements: {terms}; rewrite them neutrally")
    return p


def requirements(ctx: StageCtx) -> StageOutput:
    ws, sc, pack = ctx.ws, ctx.scenario, ctx.ws.domain
    inp = _inputs(ws)
    intake_brief = ws.read_json("00-intake/intake.json")
    controls = pack.get("controls", [])
    if ctx.call.simulated:
        jira_by_summary = {i["summary"].strip().lower(): i["key"] for i in inp["jira"]}
        reqs = [{"id": rid, "text": text, "acceptance": [f"Given {g}, when {w}, then {t}."], "priority": "must",
                 "source": f"jira:{jira_by_summary[text.lower()]}" if text.lower() in jira_by_summary else "request",
                 "classification": "restricted" if "mask" in text.lower() else "internal"}
                for rid, text, g, w, t in sc["requirements"]]
        covered = {r["source"][5:] for r in reqs if r["source"].startswith("jira:")}
        uncovered = [i for i in inp["jira"] if i["key"] not in covered and i.get("type") != "Epic"]
        d = {"outcome": sc["request"].split(",")[0] + ".",
             "consumers": [{"name": n, "questions": [q]} for n, q in sc["consumers"]],
             "requirements": reqs,
             "business_rules": [{"id": i, "text": t, "example": e} for i, t, e in sc["business_rules"]],
             "nfrs": [{"id": i, "text": t, "measure": m} for i, t, m in sc["nfrs"]],
             "glossary_delta": [{"term": m["label"], "definition": m["definition"], "owner": ROLE_DS} for m in sc["metrics"]],
             "out_of_scope": intake_brief.get("out_of_scope", []),
             "assumptions": [ctx.a("ASM-101", "Source systems are the systems of record for their entities.",
                                   "Mapping would target the wrong source", ROLE_DS)],
             "open_questions": [ctx.q("OQ-101", f"Jira item {i['key']} ('{i['summary'][:60]}') is not part of this slice; "
                                      "confirm it is parked in the backlog.", ROLE_PO) for i in uncovered]}
    else:
        prompt = ("Produce the requirements baseline as JSON with keys: outcome, consumers[{name, questions[]}], "
                  "requirements[{id 'REQ-###', text, acceptance[] (Given/When/Then), priority must|should|could, source "
                  "(e.g. 'jira:KEY' or 'request'), classification public|internal|confidential|restricted}], "
                  "business_rules[{id 'BR-###', text, example}], nfrs[{id 'NFR-###', text, measure}], "
                  "glossary_delta[{term, definition, owner}], out_of_scope[], assumptions[{id, text, impact_if_wrong, "
                  "owner_to_confirm}], open_questions[{id, question, blocking, ask_whom}]. Use no vendor, product or "
                  "dialect names. Every requirement needs at least one testable acceptance criterion. Turn each Jira "
                  "story in scope into requirements and cite its key in source.\n\n"
                  f"Intake brief:\n{json.dumps(intake_brief, indent=1)}\n\nDomain Pack glossary and classification:\n"
                  f"{dump_yaml({k: pack.get(k) for k in ('glossary_seed', 'classification_rules')})}\n"
                  + (untrusted("jira", [{k: i.get(k) for k in ('key', 'type', 'summary', 'description', 'acceptance_criteria')}
                                        for i in inp["jira"]]) if inp["jira"] else "")
                  + "\n" + untrusted("business-request", inp["request"])
                  + (untrusted("documents", inp["documents"]) if inp["documents"] else "") + _feedback_note(ctx))
        d = ctx.call.json(prompt, _req_validate)
    # Domain Pack controls become traceable NFRs
    base = len(d.get("nfrs", []))
    for i, c in enumerate(controls, start=1):
        d.setdefault("nfrs", []).append({"id": f"NFR-{100 + base + i:03d}", "text": c["text"], "measure": f"control {c['id']}"})
    ctx.write("01-requirements/requirements.json", json.dumps(d, indent=2))
    md = [f"# Requirements - {ws.run_id}", "", "## Outcome", "", d.get("outcome", ""), "", "## Consumers and questions", ""]
    md += [f"- **{c['name']}**: " + "; ".join(c.get("questions", [])) for c in d.get("consumers", [])]
    md += ["", "## Functional requirements", "",
           md_table(["ID", "Requirement", "Priority", "Classification", "Source"],
                    [[r["id"], r["text"], r.get("priority", ""), r.get("classification", ""), r.get("source", "")] for r in d["requirements"]]),
           "", "## Business rules", "", md_table(["ID", "Rule", "Example"], [[b["id"], b["text"], b.get("example", "")] for b in d.get("business_rules", [])]),
           "", "## Non-functional requirements (including Domain Pack controls)", "",
           md_table(["ID", "Requirement", "Measure"], [[n["id"], n["text"], n.get("measure", "")] for n in d.get("nfrs", [])]),
           "", "## Out of scope", ""] + [f"- {x}" for x in d.get("out_of_scope", [])]
    ctx.write("01-requirements/requirements.md", "\n".join(md) + "\n")
    ac = [f"# Acceptance criteria - {ws.run_id}", ""]
    for r in d["requirements"]:
        ac += [f"## {r['id']}", ""] + [f"- {x}" for x in r["acceptance"]] + [""]
    ctx.write("01-requirements/acceptance-criteria.md", "\n".join(ac))
    ctx.write("01-requirements/glossary-delta.md", "# Glossary delta\n\n" + md_table(
        ["Term", "Proposed definition", "Owner"], [[g["term"], g["definition"], g.get("owner", "")] for g in d.get("glossary_delta", [])]) + "\n")
    ctx.write("01-requirements/open-items.md", "# Open items\n\n## Assumptions\n\n" + md_table(
        ["ID", "Assumption", "Impact if wrong", "Owner"], [[a["id"], a["text"], a["impact_if_wrong"], a["owner_to_confirm"]] for a in d.get("assumptions", [])])
        + "\n\n## Open questions\n\n" + md_table(["ID", "Question", "Blocking", "Ask"],
                                                 [[q["id"], q["question"], q["blocking"], q["ask_whom"]] for q in d.get("open_questions", [])]) + "\n")
    restricted = any(r.get("classification") == "restricted" for r in d["requirements"]) or bool(pack.get("classification_rules", {}).get("restricted"))
    return StageOutput(
        artifacts=["01-requirements/requirements.md", "01-requirements/requirements.json", "01-requirements/acceptance-criteria.md",
                   "01-requirements/glossary-delta.md", "01-requirements/open-items.md"],
        summary=f"{len(d['requirements'])} requirements, {len(d.get('business_rules', []))} business rules and "
                f"{len(d.get('nfrs', []))} NFRs baselined, technology-neutral. Ready for G1.",
        requirement_ids=[r["id"] for r in d["requirements"]] + [b["id"] for b in d.get("business_rules", [])],
        gate_meta={"risk": "Requirements drive everything downstream; errors here are the most expensive.",
                   "cost": "None.", "rollback": "Reject with the requirement IDs to change.",
                   "options": ["Approve baseline", "Reject with specific REQ/BR changes"],
                   "extra_roles": ["data_steward"] if restricted else []},
        assumptions=d.get("assumptions", []), open_questions=[{**q, "blocking": bool(q.get("blocking"))} for q in d.get("open_questions", [])],
        inputs_used=["00-intake/intake-brief.md", "00-intake/intake.json"], evidence=["01-requirements/acceptance-criteria.md"],
        confidence=("high" if ctx.call.simulated else "medium", "Every requirement has acceptance criteria"))


# =========================================================================== 2 MAPPING
def _map_validate(d) -> list[str]:
    p = []
    for m in d.get("mappings") or []:
        for k in ("id", "target_entity", "target_attribute", "source", "confidence"):
            if not m.get(k):
                p.append(f"mapping row missing {k}: {m.get('id')}")
                break
    if not d.get("mappings"):
        p.append("mappings[] is empty")
    for r in d.get("dq_rules") or []:
        if r.get("type") not in ("not_null", "unique", "accepted_values", "range", "referential", "row_count_min"):
            p.append(f"{r.get('id')}: unsupported dq type {r.get('type')}")
    return p


def mapping(ctx: StageCtx) -> StageOutput:
    ws, sc = ctx.ws, ctx.scenario
    inp = _inputs(ws)
    reqs = ws.read_json("01-requirements/requirements.json")
    meta = inp["metadata"]
    pack_id = ws.domain["pack_id"]
    if ctx.call.simulated:
        d = scenario_mapping(pack_id)
        rows = d["mappings"]
        if meta:  # reconcile against the imported catalog / model export
            idx: dict[str, set] = {}
            for t in meta["tables"]:
                for c in t["columns"]:
                    idx.setdefault(c["name"].lower(), set()).add(t["name"].lower())
            for m in rows:
                if m["source"] in ("derived",) or m["source"].count(".") < 2:
                    continue
                tbl, col = m["source"].split(".")[-2].lower(), m["source"].split(".")[-1].lower()
                if col in idx and tbl in idx[col]:
                    m["confidence"], m["evidence"] = "high", f"found in {meta['source_file']}"
                elif col in idx:
                    m["confidence"], m["evidence"] = "medium", f"column found in {', '.join(sorted(idx[col]))} ({meta['source_file']})"
                else:
                    m["confidence"], m["evidence"] = "low", f"not found in {meta['source_file']}"
                    d["gaps"].append({"id": f"GAP-{len(d['gaps']) + 1:03d}", "text": f"{m['id']} source {m['source']} not in imported metadata",
                                      "options": "Confirm source with the data owner, or map to an alternative column", "owner": ROLE_DS})
    else:
        prompt = ("Produce the source-to-target mapping as JSON with keys: sources[{system, table 'system.table', owner, refresh, "
                  "description, columns[{name, type, classification, pk}]}], targets[{entity lower_snake, kind dimension|fact|reference, "
                  "grain, history type1|type2|snapshot|none, description, subject_area}], mappings[{id 'MAP-###', target_entity, "
                  "target_attribute lower_snake, target_type (string(n)|integer|bigint|decimal(p,s)|boolean|date|timestamp), "
                  "source ('system.table.column' or 'derived'), transformation (plain words), expression (portable SQL or null; "
                  "use src.<column> for the main source relation, {{stg:system.table}} for other sources, and target attribute "
                  "names for source=derived), business_rule ('BR-###' or null), classification, confidence high|medium|low, "
                  "req_ids[], pk bool, fk {entity, attribute} or null, description, evidence}], dq_rules[{id 'DQ-###', entity, "
                  "attribute (null for row_count_min), type not_null|unique|accepted_values|range|referential|row_count_min, "
                  "params {values[] | min,max | to_entity,to_attribute | where | min}, threshold 0..1, severity critical|high|medium|low, "
                  "requirement 'REQ-###', description}], entity_filters{entity: condition}, gaps[{id, text, options, owner}], "
                  "assumptions[], open_questions[]. Every entity needs a primary key attribute. Never invent a source: unknown "
                  "sources are gaps. No vendor names; no raw data values.\n\n"
                  f"Requirements:\n{json.dumps(reqs, indent=1)}\n\nDomain Pack entities and classification:\n"
                  f"{dump_yaml({k: ws.domain.get(k) for k in ('core_entities', 'classification_rules')})}\n"
                  + (untrusted("imported-source-metadata", meta["tables"]) if meta else
                     "No source metadata was imported: infer plausible sources from the requirements, mark every inferred "
                     "source with confidence low and list each as a gap.") + _feedback_note(ctx))
        d = ctx.call.json(prompt, _map_validate)
        d.setdefault("gaps", [])
    rows = d["mappings"]
    ctx.write("02-mapping/mapping.json", json.dumps(d, indent=2))
    src_rows = [[s["table"], s.get("system", ""), s.get("owner", ""), s.get("refresh", ""), len(s.get("columns", [])),
                 "metadata available" if meta or ctx.call.simulated else "to confirm", s.get("description", "")] for s in d.get("sources", [])]
    if meta:
        src_rows += [[f"{t['schema'] + '.' if t['schema'] else ''}{t['name']}", "imported", "", "", len(t["columns"]),
                      f"from {meta['source_file']}", t.get("description", "")] for t in meta["tables"]]
    ctx.write("02-mapping/source-inventory.md", "# Source inventory\n\n" + md_table(
        ["Source", "System", "Owner", "Refresh", "Columns", "Access / evidence", "Description"], src_rows) + "\n")
    prof_rows = [[s["table"], c["name"], c.get("type", ""), c.get("classification", ""), "PK" if c.get("pk") else "",
                  "metadata-only" if c.get("classification") == "restricted" else "capped profile pending"]
                 for s in d.get("sources", []) for c in s.get("columns", [])]
    ctx.write("02-mapping/profile-summary.md",
              "# Profile summary\n\nMetadata-first: no row-level values are read or stored. Restricted columns are "
              "metadata-only (guardrail section 5). Capped statistical profiling runs in the sandbox with synthetic "
              "data during Test.\n\n" + md_table(["Source", "Column", "Type", "Classification", "Key", "Profiling"], prof_rows) + "\n")
    ctx.write("02-mapping/target-attributes.csv", _csv(
        ["entity", "attribute", "type", "classification", "pk", "requirements"],
        [[m["target_entity"], m["target_attribute"], m.get("target_type", ""), m.get("classification", ""), m.get("pk", False),
          ";".join(m.get("req_ids") or [])] for m in rows]))
    ctx.write("02-mapping/source-to-target.csv", _csv(
        ["map_id", "target_entity", "target_attribute", "source", "transformation", "business_rule", "classification",
         "confidence", "requirements", "evidence"],
        [[m["id"], m["target_entity"], m["target_attribute"], m["source"], m.get("transformation", ""), m.get("business_rule") or "",
          m.get("classification", ""), m["confidence"], ";".join(m.get("req_ids") or []), m.get("evidence", "")] for m in rows]))
    rel = [[m["target_entity"], m["target_attribute"], f"{m['fk']['entity']}.{m['fk']['attribute']}", "many-to-one"]
           for m in rows if m.get("fk")]
    keys = [[t["entity"], ", ".join(m["target_attribute"] for m in rows if m["target_entity"] == t["entity"] and m.get("pk")),
             t.get("history", ""), t.get("grain", "")] for t in d.get("targets", [])]
    ctx.write("02-mapping/keys-and-relationships.md", "# Keys and relationships\n\n## Keys and change handling\n\n"
              + md_table(["Entity", "Business key", "History", "Grain"], keys) + "\n\n## Relationships\n\n"
              + md_table(["From", "Attribute", "To", "Cardinality"], rel) + "\n")
    ctx.write("02-mapping/dq-rules.csv", _csv(
        ["dq_id", "entity", "attribute", "type", "params", "threshold", "severity", "requirement", "description"],
        [[r["id"], r["entity"], r.get("attribute") or "", r["type"], json.dumps(r.get("params") or {}), r.get("threshold", 1.0),
          r.get("severity", ""), r.get("requirement", ""), r.get("description", "")] for r in d.get("dq_rules", [])]))
    low = [m for m in rows if m["confidence"] == "low"]
    ctx.write("02-mapping/gaps.md", "# Gaps\n\n" + (md_table(["ID", "Gap", "Options", "Owner"],
                                                             [[g["id"], g["text"], g.get("options", ""), g.get("owner", "")] for g in d["gaps"]])
                                                    if d["gaps"] else "No unmapped target attributes.") +
              f"\n\n## Low-confidence mappings for Data Steward review\n\n{len(low)} rows.\n" +
              ("\n".join(f"- {m['id']} {m['target_entity']}.{m['target_attribute']} <- {m['source']}" for m in low)) + "\n")
    req_ids = sorted({r for m in rows for r in (m.get("req_ids") or [])})
    return StageOutput(
        artifacts=["02-mapping/source-to-target.csv", "02-mapping/mapping.json", "02-mapping/source-inventory.md",
                   "02-mapping/profile-summary.md", "02-mapping/target-attributes.csv", "02-mapping/keys-and-relationships.md",
                   "02-mapping/dq-rules.csv", "02-mapping/gaps.md"],
        summary=f"{len(rows)} attributes mapped across {len(d.get('targets', []))} target entities with "
                f"{len(d.get('dq_rules', []))} quality rules; {len(d['gaps'])} gaps, {len(low)} low-confidence rows. Ready for G2.",
        requirement_ids=req_ids,
        gate_meta={"risk": f"{len(low)} low-confidence mappings and {len(d['gaps'])} gaps need steward judgement.",
                   "cost": "None.", "rollback": "Reject with MAP IDs to correct.",
                   "options": ["Approve mapping", "Approve with conditions on low-confidence rows", "Reject with MAP IDs"]},
        assumptions=d.get("assumptions", []), open_questions=d.get("open_questions", []),
        inputs_used=["01-requirements/requirements.json"], evidence=["02-mapping/profile-summary.md", "02-mapping/gaps.md"],
        confidence=("high" if not low else "medium", f"{len(low)} low-confidence rows"))


# =========================================================================== 3 DESIGN
def _model_from_mapping(d: dict, name: str, domain: str, metrics: list) -> dict:
    ents = []
    for t in d["targets"]:
        attrs = []
        for m in [x for x in d["mappings"] if x["target_entity"] == t["entity"]]:
            attrs.append({"name": m["target_attribute"], "type": m.get("target_type") or "string", "pk": bool(m.get("pk")),
                          "fk": m.get("fk"), "classification": m.get("classification") or "restricted",
                          "description": m.get("description", ""), "business_rule": m.get("business_rule"),
                          "req_ids": m.get("req_ids") or [], "nullable": not m.get("pk")})
        ents.append({"name": t["entity"], "kind": t.get("kind", "dimension"), "history": t.get("history", "type1"),
                     "grain": t.get("grain", ""), "description": t.get("description", ""),
                     "subject_area": t.get("subject_area", ""), "attributes": attrs})
    return normalize({"name": name, "version": "1.0.0", "domain": domain, "entities": ents, "metrics": metrics,
                      "description": ""})


SIZE_RATE = {"XS": 1, "S": 2, "M": 4, "L": 8, "XL": 16, "small": 2, "medium": 4, "large": 8}


def design(ctx: StageCtx) -> StageOutput:
    ws, sc, prof, run = ctx.ws, ctx.scenario, ctx.ws.stack, ctx.ws.run
    mp = ws.read_json("02-mapping/mapping.json")
    reqs = ws.read_json("01-requirements/requirements.json")
    name = re.sub(r"[^a-z0-9]+", "-", run["use_case"].lower()).strip("-")[:40] or "data-product"
    if ctx.call.simulated:
        model = _model_from_mapping(mp, name, ws.domain["pack_id"], sc["metrics"])
        model["description"] = sc["title"]
        extra = {"runtime_minutes": 20, "storage_gb": 50}
    else:
        def val(dd):
            p = []
            m = dd.get("model") or {}
            m.setdefault("name", name)
            try:
                p += validate_model(normalize(m))
            except (KeyError, TypeError) as e:
                p.append(f"model malformed: {e}")
            mapped = {(x["target_entity"], x["target_attribute"]) for x in mp["mappings"]}
            have = {(e["name"], a["name"]) for e in m.get("entities", []) for a in e.get("attributes", [])}
            miss = sorted(mapped - have)
            if miss:
                p.append(f"model is missing mapped attributes: {miss[:10]}")
            for mt in m.get("metrics", []):
                if not {"name", "entity", "measure"} <= set(mt):
                    p.append(f"metric {mt.get('name')} needs name, entity, measure{{agg, attribute}}")
            terms = scan_tech_terms(json.dumps(m))
            if terms:
                p.append(f"logical model must be technology-neutral; found {terms}")
            return p
        prompt = ("Produce the LOGICAL design as JSON with keys: model{name, description, entities[{name lower_snake, label, kind, "
                  "subject_area, description, grain, history type1|type2|snapshot|none, attributes[{name, label, type, nullable, pk, "
                  "fk {entity, attribute}|null, classification, description, business_rule, req_ids[]}]}], metrics[{name, label, "
                  "definition, entity, measure{agg sum|avg|count|count_distinct|sum_bool, attribute}, denominator{agg, attribute}|null, "
                  "unit, business_rule, grain}]}, runtime_minutes (estimated daily load), storage_gb, "
                  "assumptions[], open_questions[]. Include every mapped attribute exactly once. Use no product names.\n\n"
                  f"Mapping:\n{json.dumps({k: mp[k] for k in ('targets', 'mappings', 'dq_rules')}, indent=1)}\n\n"
                  f"Requirements:\n{json.dumps({k: reqs.get(k) for k in ('requirements', 'business_rules', 'nfrs')}, indent=1)}"
                  + _feedback_note(ctx))
        dd = ctx.call.json(prompt, val)
        model = normalize({**dd["model"], "name": dd["model"].get("name") or name, "domain": ws.domain["pack_id"]})
        extra = {"runtime_minutes": dd.get("runtime_minutes", 30), "storage_gb": dd.get("storage_gb", 100)}
    dq = mp.get("dq_rules", [])
    rels = relationships(model)
    # ---------------- logical artifacts (no technology)
    ctx.write("03-design/logical/logical-model.json", json.dumps(model, indent=2))
    lm = [f"# Logical data model - {model['name']}", "", model.get("description", ""), "", "```mermaid",
          export_mermaid(model, {}).strip(), "```", ""]
    for e in model["entities"]:
        lm += [f"## {e['label']} (`{e['name']}`)", "", f"- Kind: {e['kind']}  ", f"- Grain: {e['grain']}  ",
               f"- History: {e['history']}  ", f"- {e['description']}", "",
               md_table(["Attribute", "Type", "Key", "Nullable", "Class.", "Rule", "Req"],
                        [[a["name"], a["type"], "PK" if a["pk"] else ("FK " + a["fk"]["entity"] if a.get("fk") else ""),
                          "Y" if a["nullable"] else "N", a["classification"], a.get("business_rule") or "", ", ".join(a.get("req_ids") or [])]
                         for a in e["attributes"]]), ""]
    lm += ["## Metrics", "", md_table(["Metric", "Definition", "Rule"], [[m["label"], m["definition"], m.get("business_rule") or ""] for m in model["metrics"]])]
    ctx.write("03-design/logical/logical-data-model.md", "\n".join(lm) + "\n")
    srcs = sorted({m["source"].rsplit(".", 1)[0] for m in mp["mappings"] if m["source"].count(".") >= 2})
    flow = ["# Logical data flow (medallion)", "", "| Step | From | To | Trigger | Latency |", "|---|---|---|---|---|",
            f"| 1 Ingest | source systems: {', '.join(srcs)} | bronze: as received, every batch kept, change watermark | "
            "source change window | daily, incremental |",
            "| 2a Conform | bronze | silver: typed, trimmed, de-duplicated on the business key (latest change wins) | "
            "after ingest | daily |",
            "| 2b Curate | silver | gold: " + ", ".join(e["name"] for e in model["entities"]) + " | after conform | daily |",
            "| 3 Serve | gold | analytics layer: data product output port, masked consumer views, semantic model | "
            "after quality checks pass | daily |", "",
            "Bronze, silver and gold are stored in an open table format so any engine can read them. Quality rules run "
            "after steps 2a and 2b; a critical failure stops step 3."]
    ctx.write("03-design/logical/data-flow.md", "\n".join(flow) + "\n")
    ctx.write("03-design/logical/data-contract.yaml", export_odcs(model, {"run_id": ws.run_id, "dq_rules": dq,
                                                                          "approvers": run.get("approvers")}))
    restricted = [(e["name"], a["name"]) for e in model["entities"] for a in e["attributes"] if a["classification"] == "restricted"]
    qso = ["# Quality, security and operability", "", "## Quality", "",
           md_table(["Rule", "Entity.attribute", "Type", "Threshold", "Severity"],
                    [[r["id"], f"{r['entity']}.{r.get('attribute') or '*'}", r["type"], r.get("threshold"), r.get("severity")] for r in dq]),
           "", "## Security", "", f"{len(restricted)} Restricted attributes are masked for every consumer role without an "
           "approved basis; agents see metadata only.", ""] + [f"- `{e}.{a}`" for e, a in restricted] + [
           "", "## Operability", "", "- Every load is idempotent (merge on business key); safe to re-run.",
           "- Freshness, volume and rule-failure monitors per NFRs.", "- Rollback: restore previous table version; pipeline re-run."]
    ctx.write("03-design/logical/quality-security-operability.md", "\n".join(qso) + "\n")
    tr = [[m["id"], ";".join(m.get("req_ids") or []), f"{m['target_entity']}.{m['target_attribute']}", m.get("business_rule") or ""]
          for m in mp["mappings"]] + [[r["id"], r.get("requirement", ""), f"{r['entity']}.{r.get('attribute') or '*'}", ""] for r in dq]
    ctx.write("03-design/logical/traceability.csv", _csv(["id", "requirements", "design_element", "business_rule"], tr))
    # ---------------- physical artifacts (bound to Stack Profile)
    d = ph.dialect_for(prof)
    bm = [[e["name"], "compute_engine + transformation", f"{stacks.tool(prof, 'compute_engine')} / {stacks.tool(prof, 'transformation')}",
           f"{ph.schema_name(prof)}.{ph.table_name(e, prof)}",
           {"type2": "history-type2 (ADR-001)", "none": "incremental merge (ADR-002)" if e["kind"] == "fact" else "full refresh",
            "type1": "merge/overwrite type 1", "snapshot": "periodic snapshot"}.get(e["history"], e["history"])]
          for e in model["entities"]]
    ctx.write("03-design/physical/binding-map.md", "# Binding map (stack-binding T3)\n\n" + md_table(
        ["Logical component", "Slot", "Tool", "Physical object", "Pattern"], bm) + "\n")
    v = stacks.validate(prof)
    gaps = [w for w in v["warnings"] if "no adapter" in w]
    ctx.write("03-design/physical/binding-gaps.md", "# Binding gaps\n\n" + ("\n".join(f"- {g}" for g in gaps) or "None: every logical "
              "requirement has a physical equivalent on the bound stack.") + "\n")
    ddl = export_ddl(model, {"profile": prof})
    ctx.write("03-design/physical/ddl.sql", ddl)
    pd = [f"# Physical design - {stacks.tool(prof, 'compute_engine')} ({ph.DIALECT_LABELS.get(d, d)})", "",
          f"Target schema `{ph.schema_name(prof)}`; layers {', '.join(prof['standards']['layers'])}; naming {prof['standards']['naming_case']}.", "",
          "## Environments", "", md_table(["Env", "Purpose", "Agent max class", "Secrets ref"],
                                          [[k, x["purpose"], x["agent_max_class"], x["secrets_ref"]] for k, x in prof["environments"].items()]),
          "", "## Pipelines", "", f"- Orchestration: `{stacks.tool(prof, 'orchestration')}`, daily 03:00 UTC, max one active run.",
          f"- Transformation: `{stacks.tool(prof, 'transformation')}`; quality: `{stacks.tool(prof, 'data_quality')}`.",
          f"- CI/CD: `{stacks.tool(prof, 'cicd')}`; deploy only by pipeline identity after G6.", "",
          "## The three pipelines", "",
          md_table(["#", "Pipeline", "From", "To", "Runs on"], [[h["pipeline"], h["name"], h["from"], h["to"], h["tool"]]
                                                                for h in stacks.pipeline_summary(prof)]),
          "", "Ingestion is incremental on the source `LAST_UPDATED_TS` watermark; every step is idempotent "
          "(per-batch partition overwrite, MERGE on business keys).", "",
          "## Rollback", "", "Per-object: restore previous table version (time travel / backup clone) and redeploy the previous "
          "tagged commit. Rehearsed in Release before G6b.", "", "## DDL", "", "See `ddl.sql`."]
    ctx.write("03-design/physical/physical-design.md", "\n".join(pd) + "\n")
    lim = prof.get("limits", {})
    size = str(lim.get("max_compute_size", "S"))
    rate = SIZE_RATE.get(size, 2)
    unit_price = 3.0
    rt = float(extra["runtime_minutes"])
    compute_month = rt / 60 * rate * unit_price * 30
    storage_month = float(extra["storage_gb"]) / 1024 * 23
    total = round(compute_month + storage_month, 2)
    cap = float(lim.get("monthly_cost_cap") or 0)
    over = cap > 0 and total > cap
    cost_md = ["# Cost estimate", "", "All rates are list-price **assumptions** to be confirmed by the Platform Owner.", "",
               md_table(["Item", "Arithmetic", "Monthly"], [
                   ["Compute", f"{rt:.0f} min/day / 60 x {rate} units/h (size {size}) x ${unit_price:.2f}/unit x 30 days", f"${compute_month:,.2f}"],
                   ["Storage", f"{extra['storage_gb']} GB / 1024 x $23/TB-month", f"${storage_month:,.2f}"],
                   ["**Total**", "", f"**${total:,.2f}**"]]), "",
               f"Monthly cost cap in Stack Profile: {'$' + format(cap, ',.2f') if cap else 'none (every paid action needs approval)'}.",
               "", "## Guardrails", "", f"- Auto-suspend {lim.get('auto_suspend_seconds')} s; query timeout {lim.get('query_timeout_seconds')} s; "
               f"max size {size}.", "- Sandbox runs use synthetic data only."]
    if over:
        cost_md += ["", f"**Estimate exceeds the cap by ${total - cap:,.2f}. Escalated: Platform Owner approval is required at G3 "
                    "(options: reduce frequency, smaller size, or raise the cap).**"]
    ctx.write("03-design/physical/cost-estimate.md", "\n".join(cost_md) + "\n")
    adrs = [("ADR-001", "History for changing dimensions",
             f"Entities with history type2 ({', '.join(e['name'] for e in model['entities'] if e['history'] == 'type2') or 'none'}) need point-in-time results.",
             f"Use the adapter's history-type2 pattern on {stacks.tool(prof, 'transformation')} with valid_from/valid_to/is_current.",
             "More storage; queries must filter is_current for current state."),
            ("ADR-002", "Incremental idempotent fact loads", "Facts are high volume and loads must be safely re-runnable.",
             "Merge on the business key; never append blindly.", "Requires a stable business key per fact row."),
            ("ADR-003", "Masking of Restricted attributes", f"{len(restricted)} Restricted attributes; Domain Pack controls apply.",
             f"Mask in the consumption layer and catalog-tag via {stacks.tool(prof, 'catalog_governance')}.",
             "Privileged access requires Security and Compliance approval (A3)."),
            ("ADR-004", "Platform-native strengths over portability",
             f"portability_required={prof.get('portability_required')}.",
             f"Use native features of {stacks.tool(prof, 'compute_engine')}; logical model stays neutral for rebind.",
             "Lock-in recorded; rebind test proves logical portability.")]
    for i, t, c, dcn, cons in adrs:
        ctx.write(f"03-design/physical/adr/{i}.md", f"# {i}: {t}\n\n**Status:** proposed (G3)\n\n## Context\n\n{c}\n\n"
                                                    f"## Decision\n\n{dcn}\n\n## Consequences\n\n{cons}\n")
    wp = ["# Work packages", "", md_table(["Package", "Scope", "Acceptance"], [[
        "WP-001", "Staging, " + ", ".join(e["name"] for e in model["entities"]) + ", quality rules, orchestration, CI",
        "Lint, dry-run, unit tests and run-twice idempotency pass in the sandbox; all MAP/BR/DQ IDs in manifest"]])]
    ctx.write("03-design/physical/work-packages.md", "\n".join(wp) + "\n")
    extra_roles = (["security_compliance"] if restricted else []) + (["platform_owner"] if over else [])
    arts = ["03-design/physical/physical-design.md", "03-design/logical/logical-model.json", "03-design/logical/logical-data-model.md",
            "03-design/logical/data-flow.md", "03-design/logical/data-contract.yaml", "03-design/logical/quality-security-operability.md",
            "03-design/logical/traceability.csv", "03-design/physical/binding-map.md", "03-design/physical/binding-gaps.md",
            "03-design/physical/ddl.sql", "03-design/physical/cost-estimate.md", "03-design/physical/work-packages.md"] + \
           [f"03-design/physical/adr/{a[0]}.md" for a in adrs]
    risks = [ctx.r("RSK-301", "Cost estimate above budget", "high", "medium", "Platform Owner decision at G3")] if over else []
    return StageOutput(
        artifacts=arts,
        summary=f"Logical model with {len(model['entities'])} entities and {len(rels)} relationships bound to "
                f"{prof['profile_id']}; {len(adrs)} ADRs; estimated ${total:,.2f}/month. Ready for G3.",
        requirement_ids=[r["id"] for r in reqs["requirements"]],
        gate_meta={"risk": f"{len(restricted)} Restricted attributes; {len(gaps)} binding gaps." + (" Cost above cap." if over else ""),
                   "cost": f"Estimated ${total:,.2f}/month (assumption-based)", "rollback": "Design only; reject to revise.",
                   "options": ["Approve design and estimate", "Approve with conditions (e.g. cap compute size)", "Reject with ADR/entity changes"],
                   "extra_roles": extra_roles},
        risks=risks, inputs_used=["02-mapping/mapping.json", "01-requirements/requirements.json"],
        evidence=["03-design/physical/cost-estimate.md", "03-design/physical/binding-map.md"],
        constraints=[f"compute size <= {size}"], confidence=("high" if not gaps else "medium", f"{len(gaps)} binding gaps"))
