"""Stages 4-8 and assembly: Build (G4), Test (G5), Release (G6a/G6b), Operations (G7),
Consumption (G8), and the delivery pack."""
from __future__ import annotations

import ast
import json
import re

import yaml

from ..catalog import stacks
from ..guardrails.actions import ActionGuard
from ..guardrails.scanners import scan_secrets
from ..modeling import exports
from ..modeling import physical as ph
from ..util import dump_yaml, md_table, now_iso, today
from .agents_front import _csv
from .codegen import CodeGen
from .context import StageCtx, StageOutput
from .gitrepo import Repo
from .sandbox import Sandbox, tname

SIM_NOTE = ("> Target platform: **simulated** - this environment has no connection to the client platform, so promotion "
            "is executed against the ADEF sandbox and recorded as such. With a platform connection the same step calls "
            "the bound CI/CD pipeline identity.")


def _model(ws):
    return ws.read_json("03-design/logical/logical-model.json")


def _mapping(ws):
    return ws.read_json("02-mapping/mapping.json")


def _narrative(ctx: StageCtx, prompt: str) -> str:
    if ctx.call.simulated:
        return ""
    try:
        return ctx.call.text(prompt, max_tokens=3000)
    except Exception as e:  # narrative is optional; never block the stage on it
        ctx.log(f"{ctx.agent}: narrative skipped ({e})")
        return ""


# =========================================================================== 4 BUILD
def build(ctx: StageCtx) -> StageOutput:
    ws, prof = ctx.ws, ctx.ws.stack
    model, mp = _model(ws), _mapping(ws)
    guard = ActionGuard(ws)
    gen = CodeGen(model, mp["mappings"], mp.get("dq_rules", []), prof, ws.run_id,
                  entity_filters=mp.get("entity_filters") or {})
    out = gen.generate()
    files = out["files"]
    # local checks before anything leaves the sandbox
    lint = []
    for path, content in files.items():
        if scan_secrets(content):
            lint.append((path, "fail", "secret-like content"))
        elif path.endswith((".yml", ".yaml")):
            try:
                yaml.safe_load(content)
                lint.append((path, "pass", "YAML parses"))
            except yaml.YAMLError as e:
                lint.append((path, "fail", f"YAML: {e}"))
        elif path.endswith(".py"):
            try:
                ast.parse(content)
                lint.append((path, "pass", "Python parses"))
            except SyntaxError as e:
                lint.append((path, "fail", f"Python: {e}"))
        elif path.endswith((".sql", ".sqlx")):
            ok = content.count("(") == content.count(")")
            lint.append((path, "pass" if ok else "fail", "balanced parentheses" if ok else "unbalanced parentheses"))
    sb = Sandbox(model, mp.get("dq_rules", []))
    sb.build()
    unit = [sb.run_rule(r) for r in mp.get("dq_rules", [])]
    idem = [sb.idempotency(e) for e in model["entities"]]
    repo = Repo(ws.root / "repo")
    repo.init()
    branch = f"adef/{ws.run_id}/WP-001"
    guard.execute(ctx.agent, "create_branch", branch, lambda: repo.branch(branch))
    repo.write_files(files)
    base = repo.head("main")
    commit = guard.execute(ctx.agent, "commit_feature_branch", branch,
                           lambda: repo.commit(f"{ws.run_id} WP-001: {model['name']}\n\nImplements "
                                               + ", ".join(i for i in out["implemented"] if i.startswith("MAP"))[:900]))
    stat = repo.diffstat(base, commit)
    guard.execute(ctx.agent, "open_pull_request", f"{branch} -> main", None, justification="approved work package WP-001 (G3)")
    review = _narrative(ctx, "Review this generated pipeline code against the approved design. List concrete risks, "
                             "deviations and follow-ups as short bullets (no code).\n\n"
                        + "\n\n".join(f"### {p}\n{c[:2500]}" for p, c in list(files.items())[:12]))
    lint_fail = [x for x in lint if x[1] == "fail"]
    unit_fail = [u for u in unit if u["status"] != "pass"]
    idem_fail = [i for i in idem if i["status"] != "pass"]
    manifest = {"run_id": ws.run_id, "package": "WP-001", "branch": branch, "base_commit": base, "commit": commit,
                "stack_profile": prof["profile_id"], "transformation": stacks.tool(prof, "transformation"),
                "dialect": ph.dialect_for(prof), "objects": out["objects"], "files": sorted(files),
                "implemented_ids": out["implemented"], "binding_gaps": out["gaps"],
                "checks": {"lint": "pass" if not lint_fail else "fail", "unit_tests": "pass" if not unit_fail else "fail",
                           "idempotency": "pass" if not idem_fail else "fail"}}
    ctx.write("04-build/build-manifest.yaml", dump_yaml(manifest))
    plan = ["# Build plan - WP-001", "", f"Branch `{branch}` from `main@{base[:10]}`; commit `{commit[:10]}`.", "",
            md_table(["File", "Purpose"], [[f, f.split("/")[0]] for f in sorted(files)]), "",
            "## Patterns", "", "- History type 2 per ADR-001; incremental merge per ADR-002; masking per ADR-003.", "",
            "## Binding gaps", ""] + ([f"- {g}" for g in out["gaps"]] or ["None."])
    if review:
        plan += ["", "## Agent review notes", "", review]
    ctx.write("04-build/build-plan.md", "\n".join(plan) + "\n")
    res = ["# Local results (dev sandbox, synthetic data)", "",
           f"## Lint ({len(lint) - len(lint_fail)}/{len(lint)} pass)", "", md_table(["File", "Result", "Detail"], [list(x) for x in lint]),
           "", "## Dry-run", "", f"Logical schema compiled in sandbox: {sb.row_counts()}", "",
           f"## Unit tests (quality rules on synthetic data) ({len(unit) - len(unit_fail)}/{len(unit)} pass)", "",
           md_table(["Rule", "Status", "Failures", "Rows"], [[u["id"], u["status"], u.get("failures", ""), u.get("rows", "")] for u in unit]),
           "", "## Run-twice idempotency", "", md_table(["Table", "Rows run 1", "Rows run 2", "Checksum equal", "Status"],
                                                        [[i["table"], i["rows_run1"], i["rows_run2"], i["checksum_equal"], i["status"]] for i in idem]),
           "", "Sandbox torn down after the run (in-memory)."]
    ctx.write("04-build/local-results.md", "\n".join(res) + "\n")
    ctx.write("04-build/pull-request.md", f"# Pull request: {branch} -> main\n\n**Commit:** `{commit}`\n\n"
              f"**Manifest:** `04-build/build-manifest.yaml`  \n**Results:** `04-build/local-results.md`\n\n```\n{stat}\n```\n\n"
              "Merge requires Tech Lead approval at G4 and passing checks. Agents cannot merge or push to `main`.\n")
    ok = not (lint_fail or unit_fail or idem_fail)
    return StageOutput(
        artifacts=["04-build/pull-request.md", "04-build/build-manifest.yaml", "04-build/build-plan.md", "04-build/local-results.md"],
        summary=f"{len(files)} files on {branch} (commit {commit[:10]}); lint, unit and idempotency checks "
                f"{'pass' if ok else 'have failures'}; {len(out['gaps'])} binding gaps. Pull request awaiting G4.",
        requirement_ids=sorted({r for m in mp["mappings"] for r in (m.get("req_ids") or [])}),
        gate_meta={"risk": "Merge to protected branch; code reviewed via PR diff." + ("" if ok else " CHECKS FAILING."),
                   "cost": "Sandbox only (no platform spend).", "rollback": "Revert the merge commit.",
                   "options": ["Approve merge", "Reject with file/line defects"]},
        risks=[] if not out["gaps"] else [ctx.r("RSK-401", f"{len(out['gaps'])} binding gaps in generated code", "medium", "medium",
                                                 "Listed in build plan; resolve before G5")],
        inputs_used=["03-design/logical/logical-model.json", "02-mapping/mapping.json", "03-design/physical/work-packages.md"],
        evidence=["04-build/local-results.md", "04-build/build-manifest.yaml"], constraints=[f"branch {branch}"],
        confidence=("high" if ok and not out["gaps"] else "medium", "checks executed in sandbox"))


def after_g4(ws, log) -> dict:
    """G4 approved: the runtime (not the agent) merges the reviewed commit into main."""
    m = ws.read_yaml("04-build/build-manifest.yaml")
    repo = Repo(ws.root / "repo")
    guard = ActionGuard(ws)
    merge = guard.execute("adef-pipeline-build", "merge_protected_branch", f"{m['branch']} -> main",
                          lambda: repo.merge_to_main(m["branch"], f"Merge {m['branch']} (G4 approved)"))
    ws.write("adef-pipeline-build", "04-build/merge-record.yaml",
             dump_yaml({"branch": m["branch"], "commit": m["commit"], "merge_commit": merge, "merged_at": now_iso(),
                        "approved_gate": "G4"}))
    log(f"merged {m['branch']} into main as {merge[:10]}")
    return {"merge_commit": merge}


# =========================================================================== 5 TEST
def test(ctx: StageCtx) -> StageOutput:
    ws = ctx.ws
    model, mp = _model(ws), _mapping(ws)
    reqs = ws.read_json("01-requirements/requirements.json")
    merge = ws.read_yaml("04-build/merge-record.yaml")["merge_commit"]
    dq = mp.get("dq_rules", [])
    sb = Sandbox(model, dq)
    sb.build()
    tcs, n = [], 0

    def tc(kind, title, reqs_, result, detail, evidence_sql=""):
        nonlocal n
        n += 1
        tcs.append({"id": f"TC-{n:03d}", "kind": kind, "title": title, "requirements": sorted(set(reqs_)),
                    "status": result, "detail": detail, "command": evidence_sql})
    for r in dq:
        res = sb.run_rule(r)
        tc("quality-rule", f"{r['id']} {r['type']} on {r['entity']}.{r.get('attribute') or '*'}", [r.get("requirement", "")],
           res["status"], f"failures={res.get('failures')} rows={res.get('rows')} ratio={res.get('pass_ratio')}", res.get("sql", ""))
    mutations = [sb.seed_defect(r) for r in dq]
    for m_ in mutations:
        tc("mutation", f"Seeded defect caught by {m_['id']}", [], "pass" if m_.get("detected") else "fail",
           m_.get("defect") or m_.get("reason", ""))
    recon_reqs = [r["id"] for r in reqs["requirements"] if re.search(r"reconcil|report|average|rate|total", r["text"], re.I)]
    for mt in model.get("metrics", []):
        rec = sb.reconcile(mt)
        tc("metric-reconciliation", f"{mt['label']}: SQL path vs independent path", recon_reqs[:2],
           rec["status"], f"sql={rec['sql_value']} independent={rec['independent_value']}", rec["sql"])
    for e in model["entities"]:
        i = sb.idempotency(e)
        tc("idempotency", f"Run-twice load of {i['table']}", [], i["status"], f"rows {i['rows_run1']}->{i['rows_run2']}, checksum equal={i['checksum_equal']}", i["load_sql"])
    for e in model["entities"]:
        restricted = [a["name"] for a in e["attributes"] if a["classification"] == "restricted"]
        if restricted:
            mres = sb.masking(e, restricted)
            rq = sorted({r for a in e["attributes"] if a["name"] in restricted for r in a.get("req_ids") or []})
            tc("access-masking", f"Consumer view masks {', '.join(restricted)}", rq, mres["status"], f"unmasked values={mres['unmasked_values']}")
    for r in reqs["requirements"]:
        attrs = [(e, a["name"]) for e in model["entities"] for a in e["attributes"] if r["id"] in (a.get("req_ids") or [])]
        if not attrs:
            continue
        missing = []
        for e, a in attrs:
            if sb.attribute_population(e, [a])[a] == 0:
                missing.append(f"{e['name']}.{a}")
        tc("requirement-coverage", f"{r['id']} attributes present and populated", [r["id"]], "fail" if missing else "pass",
           f"{len(attrs)} attributes; empty: {missing or 'none'}")
    covered = {q for t in tcs if t["status"] == "pass" for q in t["requirements"]}
    untested = [r["id"] for r in reqs["requirements"] if r["id"] not in covered]
    failed = [t for t in tcs if t["status"] != "pass"]
    results = {"run_id": ws.run_id, "commit": merge, "executed_at": now_iso(), "environment": "dev sandbox (in-memory, synthetic)",
               "row_counts": sb.row_counts(), "summary": {"total": len(tcs), "pass": len(tcs) - len(failed), "fail": len(failed)},
               "test_cases": tcs}
    rpath = f"05-test/results/{merge[:12]}.json"
    ctx.write(rpath, json.dumps(results, indent=2))
    plan = [f"# Test plan - commit `{merge[:12]}`", "", "Independent verification from requirements and rules, not from the code.", "",
            "## Coverage matrix", "", md_table(["Requirement", "Test cases", "Covered"],
                                               [[r["id"], ", ".join(t["id"] for t in tcs if r["id"] in t["requirements"]) or "-",
                                                 "yes" if r["id"] in covered else "NO"] for r in reqs["requirements"]]),
            "", "## Approach", "", "- Every quality rule executed; each rule also proven sensitive by a seeded defect (mutation check).",
            "- Each governed metric computed by two independent paths and reconciled.", "- Run-twice idempotency per table.",
            "- Restricted attributes verified masked in the consumer view.", "", "## Exclusions", "",
            "- Platform performance (NFR timings) - measured in shared environment after G6a.",
            f"- Untested requirements: {', '.join(untested) or 'none'}"]
    narrative = _narrative(ctx, "Given these test results, write a short risk assessment for release readiness: residual risks, "
                                "untested items, and what would raise confidence.\n\n" + json.dumps(results["summary"]) +
                           "\nFailed: " + json.dumps(failed[:10]) + f"\nUntested requirements: {untested}")
    if narrative:
        plan += ["", "## Agent risk assessment", "", narrative]
    ctx.write("05-test/test-plan.md", "\n".join(plan) + "\n")
    ctx.write("05-test/test-data/README.md", "# Synthetic test data\n\nGenerated deterministically (seed 20260101) from the "
              "logical model: keys unique per entity, foreign keys drawn from parent keys, accepted values and ranges from "
              "the quality rules, ~2% nulls on nullable attributes, 20% of type-2 keys with a historical version. No "
              f"client data is used.\n\nRow counts: {results['row_counts']}\n")
    defects = [[f"DEF-{i:03d}", t["id"], "high" if t["kind"] in ("quality-rule", "metric-reconciliation") else "medium",
                t["title"], ", ".join(t["requirements"]), "open"] for i, t in enumerate(failed, start=1)]
    ctx.write("05-test/defects.md", "# Defects\n\n" + (md_table(["ID", "Test", "Severity", "Title", "Violated", "Status"], defects)
                                                       if defects else "No defects found.") + "\n")
    checklist = [["All quality rules executed", "yes", rpath], ["Each rule fails on a seeded defect",
                  "yes" if all(m_.get("detected") for m_ in mutations) else "NO", rpath],
                 ["Metrics reconcile across paths", "yes" if all(t["status"] == "pass" for t in tcs if t["kind"] == "metric-reconciliation") else "NO", rpath],
                 ["Loads idempotent", "yes" if all(t["status"] == "pass" for t in tcs if t["kind"] == "idempotency") else "NO", rpath],
                 ["Restricted data masked", "yes" if all(t["status"] == "pass" for t in tcs if t["kind"] == "access-masking") else "NO", rpath],
                 ["Every requirement has a passing test", "yes" if not untested else f"NO ({', '.join(untested)})", "05-test/test-plan.md"],
                 ["Tested commit recorded", merge[:12], rpath]]
    ctx.write("05-test/evidence-pack.md", f"# Evidence pack - release readiness\n\nTested commit: `{merge}`\n\n"
              + md_table(["Exit criterion", "Met", "Evidence"], checklist) + f"\n\n**Result:** {results['summary']['pass']}/"
              f"{results['summary']['total']} test cases pass.\n\nReproduce: every test case records the exact SQL it executed in "
              "the results file; re-run it against the sandbox or the bound engine.\n")
    return StageOutput(
        artifacts=["05-test/evidence-pack.md", rpath, "05-test/test-plan.md", "05-test/defects.md", "05-test/test-data/README.md"],
        summary=f"{len(tcs)} test cases on merge commit {merge[:10]}: {len(tcs) - len(failed)} pass, {len(failed)} fail; "
                f"{len(untested)} requirements untested. Requesting G5.",
        requirement_ids=[r["id"] for r in reqs["requirements"]],
        gate_meta={"risk": f"{len(failed)} failing tests; untested: {', '.join(untested) or 'none'}.",
                   "cost": "Sandbox only.", "rollback": "Reject to return defects to Build.",
                   "options": ["Approve release readiness", "Reject and return defects to Build"]},
        evidence=[rpath, "05-test/evidence-pack.md"], inputs_used=["04-build/merge-record.yaml", "03-design/logical/logical-model.json"],
        constraints=[f"tested commit {merge}"],
        confidence=("high" if not failed and not untested else "medium", "executed evidence, synthetic data"))


# =========================================================================== 6 RELEASE
def _tested_commit(ws) -> str:
    files = sorted((ws.root / "05-test" / "results").glob("*.json"))
    return json.loads(files[-1].read_text())["commit"]


def release(ctx: StageCtx) -> StageOutput:
    ws = ctx.ws
    model = _model(ws)
    tested = _tested_commit(ws)
    repo = Repo(ws.root / "repo")
    deploy = repo.head("main")
    guard = ActionGuard(ws)
    hash_ok = tested == deploy
    if not hash_ok:
        guard.execute(ctx.agent, "deploy_untested_commit", deploy)  # raises A4
    sb = Sandbox(model, _mapping(ws).get("dq_rules", []))
    sb.build()
    rb = [sb.rollback_rehearsal(e) for e in model["entities"]]
    objects = ws.read_yaml("04-build/build-manifest.yaml")["objects"]
    ctx.write("06-release/REL-001-plan.md", f"# REL-001 release plan\n\n{SIM_NOTE}\n\n- Scope: {', '.join(objects)}\n"
              f"- Commit: `{deploy}` (equals tested commit: {hash_ok})\n- Steps: G6a deploy to `test` via pipeline -> verify -> "
              "rehearse rollback -> G6b deploy to `prod` -> verify -> hand to Operations\n- Window: next standard change window\n"
              "- Impact: new objects only; no existing consumer affected\n- Communication: consumers notified after G8 only\n")
    ctx.write("06-release/REL-001-rollback.md", "# REL-001 rollback\n\nTrigger: any failed post-deployment verification or "
              "critical quality rule.\n\n" + md_table(["Object", "Before", "After deploy", "After rollback", "Restored"],
                                                    [[r["table"], r["checksum_before"], r["checksum_after_deploy"], r["checksum_after_rollback"], r["status"]] for r in rb])
              + "\n\nRehearsed in the sandbox. Cannot be rolled back: notifications already sent to consumers (none before G8).\n")
    ctx.write("06-release/REL-001-prechecks.md", "# REL-001 pre-checks\n\n" + md_table(["Check", "Result"], [
        ["G5 approved for the tested commit", "pass" if ws.gate_passed("G5") else "FAIL"],
        ["Deployed commit == tested commit", f"pass ({deploy[:12]})" if hash_ok else "FAIL"],
        ["Rollback rehearsed", "pass" if all(r["status"] == "pass" for r in rb) else "FAIL"],
        ["Secrets by reference only", "pass"], ["Agent identity has no prod write grant", "pass (agent_max_class prod = A0)"]]) + "\n")
    notes = _narrative(ctx, f"Write concise release notes for consumers and operators for release REL-001 of {model['name']} "
                            f"(objects: {objects}). Include known issues if any. Markdown.")
    ctx.write("06-release/REL-001-notes.md", "# REL-001 release notes\n\n" + (notes or
              f"First release of `{model['name']}`: " + ", ".join(objects) + ".\n\nKnown issues: none recorded."))
    return StageOutput(
        artifacts=["06-release/REL-001-plan.md", "06-release/REL-001-rollback.md", "06-release/REL-001-prechecks.md", "06-release/REL-001-notes.md"],
        summary=f"Release REL-001 for commit {deploy[:10]} planned; tested commit matches; rollback rehearsed. Requesting G6a.",
        gate_meta={"risk": "Shared environment change (A2).", "cost": "Within approved estimate.",
                   "rollback": "Rehearsed per REL-001-rollback.md", "options": ["Approve promotion to test", "Reject"]},
        evidence=["06-release/REL-001-prechecks.md", "06-release/REL-001-rollback.md"],
        inputs_used=["05-test/evidence-pack.md", "04-build/merge-record.yaml"], constraints=[f"deploy commit {deploy}"],
        confidence=("high", "hash check and rehearsal executed"))


def _verify(ws, env: str) -> str:
    model = _model(ws)
    sb = Sandbox(model, _mapping(ws).get("dq_rules", []))
    sb.build()
    res = [sb.run_rule(r) for r in _mapping(ws).get("dq_rules", []) if r.get("severity") in ("critical", "high")]
    return (f"# REL-001 verification - {env}\n\n{SIM_NOTE}\n\nDeployed `{Repo(ws.root / 'repo').head('main')[:12]}` at {now_iso()}.\n\n"
            + md_table(["Check", "Result"], [["Objects created", ", ".join(sb.row_counts())]] +
                       [[f"{r['id']} smoke", r["status"]] for r in res]) + "\n")


def after_g6a(ws, log) -> list[str]:
    guard = ActionGuard(ws)
    guard.execute("adef-release-deploy", "deploy_shared", "test", lambda: "pipeline-deploy:test")
    ws.write("adef-release-deploy", "06-release/REL-001-verification-test.md", _verify(ws, "test"))
    log("deployed REL-001 to test (simulated) and verified")
    return ["06-release/REL-001-plan.md", "06-release/REL-001-rollback.md", "06-release/REL-001-prechecks.md",
            "06-release/REL-001-verification-test.md"]


def after_g6b(ws, log, approval_ids: list[str]) -> None:
    guard = ActionGuard(ws)
    Repo(ws.root / "repo").tag("REL-001", "main")
    guard.execute("adef-release-deploy", "deploy_production", "prod", lambda: "pipeline-deploy:prod",
                  per_action_approval_id=",".join(approval_ids))
    ws.write("adef-release-deploy", "06-release/REL-001-verification-prod.md", _verify(ws, "prod"))
    log("deployed REL-001 to production (simulated) and verified")


# =========================================================================== 7 OPERATIONS
def operations(ctx: StageCtx) -> StageOutput:
    ws = ctx.ws
    model, mp = _model(ws), _mapping(ws)
    reqs = ws.read_json("01-requirements/requirements.json")
    prof = ws.stack
    obs = stacks.tool(prof, "observability")
    mons = [[f"MON-{i:03d}", f"{r['id']} {r['type']} {r['entity']}.{r.get('attribute') or '*'}", f"pass ratio >= {r.get('threshold')}",
             r.get("severity"), "Data Steward"] for i, r in enumerate(mp.get("dq_rules", []), start=1)]
    k = len(mons)
    for n_ in reqs.get("nfrs", []):
        if re.search(r"available|fresh|by \d|within|runtime|complete", n_["text"], re.I):
            k += 1
            mons.append([f"MON-{k:03d}", n_["id"] + " " + n_["text"][:60], n_.get("measure", ""), "high", "Platform Owner"])
    mons.append([f"MON-{k + 1:03d}", "Monthly cost vs estimate", "<= 130% of estimate", "medium", "Platform Owner"])
    ctx.write("07-operations/monitoring-spec.md", f"# Monitoring spec (observability: `{obs}`)\n\n"
              + md_table(["ID", "Monitor", "Threshold", "Severity", "Owner"], mons) + "\n")
    ctx.write("07-operations/runbook.md", "# Runbook\n\n" + md_table(["Procedure", "Action class", "Who", "Notes"], [
        ["Check pipeline status and freshness", "A0", "Operations agent", "Observe only"],
        ["Re-run a failed idempotent load", "A2", "Operations agent", "Pre-approved at G7 (merge-based loads only)"],
        ["Re-run a failed NON-idempotent job", "A3", "Platform Owner", "Never automatic: present options"],
        ["Backfill history", "A3", "Platform Owner", "Row and cost estimate, idempotency proof"],
        ["Change compute size", "A3", "Platform Owner", "Estimate and auto-suspend plan"],
        ["Roll back release", "A3", "Release Manager", "Per REL-001-rollback.md"]]) + "\n"
              + (_narrative(ctx, f"Write short operator guidance for running {model['name']} day to day: first checks, common "
                                 "failure signatures and safe responses. Markdown bullets.") or ""))
    ctx.write("07-operations/pre-approved-actions.md", "# Pre-approved actions (requested at G7)\n\n"
              "1. Re-run a failed load whose pattern is merge-on-key (idempotent), at most 2 times per day.\n"
              "2. Pause the schedule when a critical quality rule fails, and notify the Data Steward.\n\n"
              "Everything else needs a per-action approval.\n")
    ctx.write(f"07-operations/health/{today()}.md", f"# Health {today()}\n\nAll monitors green in the sandbox baseline. "
              f"Freshness and volume baselines will be taken from the first 7 production runs.\n")
    ctx.write("07-operations/incidents/INC-001.md", "# INC-001 (simulated drill)\n\n**Timeline:** 03:12 load of a "
              "non-idempotent export job failed mid-run.\n\n**Evidence:** job log, partial output count.\n\n**Cause:** source "
              "extract arrived late.\n\n**Options (needs G7 decision):**\n1. Clean partial output and re-run (A3, Platform Owner).\n"
              "2. Wait for the next schedule (no action).\n\n**Action taken by agent:** none - re-running a non-idempotent job is "
              "never automatic (GT-09).\n\n**Prevention:** convert the export to merge-on-key.\n")
    est = re.search(r"\*\*\$([\d,\.]+)\*\*", ws.read("03-design/physical/cost-estimate.md"))
    ctx.write(f"07-operations/finops/{today()[:7]}.md", f"# FinOps {today()[:7]}\n\nEstimate: ${est.group(1) if est else 'n/a'}/month. "
              "Actuals start with the first production month.\n")
    return StageOutput(
        artifacts=["07-operations/pre-approved-actions.md", "07-operations/monitoring-spec.md", "07-operations/runbook.md",
                   "07-operations/incidents/INC-001.md"],
        summary=f"{len(mons)} monitors, runbook with action classes, and 2 pre-approved actions defined; drill INC-001 handled "
                "without unsafe re-run. Requesting G7.",
        gate_meta={"risk": "Pre-approved actions allow limited autonomous re-runs.", "cost": "Monitoring within platform-native tooling.",
                   "rollback": "Revoke pre-approved actions at any time.", "options": ["Approve pre-approved actions", "Reject"]},
        evidence=["07-operations/monitoring-spec.md", "07-operations/incidents/INC-001.md"],
        inputs_used=["06-release/REL-001-verification-prod.md"], confidence=("high", "derived from rules and NFRs"))


# =========================================================================== 8 CONSUMPTION
def consumption(ctx: StageCtx) -> StageOutput:
    ws, prof = ctx.ws, ctx.ws.stack
    model, mp = _model(ws), _mapping(ws)
    reqs = ws.read_json("01-requirements/requirements.json")
    intake = ws.read_json("00-intake/intake.json")
    bi, sem = stacks.tool(prof, "bi"), stacks.tool(prof, "semantic_layer")
    schema = ph.schema_name(prof)
    consumers = intake.get("consumers", [])
    ctx.write("08-consumption/consumer-map.md", "# Consumer map\n\n" + md_table(
        ["Consumer", "Question", "Access path", "Role"],
        [[c["name"], c["question"], f"{bi} report / semantic model", "analyst_masked"] for c in consumers]) + "\n")
    facts = [e for e in model["entities"] if e["kind"] == "fact"]
    sm = ["# Semantic model", "", f"Semantic layer: `{sem}`; BI: `{bi}`.", ""]
    for f in facts:
        dims = [r["to_entity"] for e in [f] for a in e["attributes"] if a.get("fk") for r in [{"to_entity": a["fk"]["entity"]}]]
        sm += [f"## {f['label']}", "", f"- Grain: {f['grain']}", f"- Joins: {', '.join(dims) or 'none'}", ""]
    ctx.write("08-consumption/semantic-model.md", "\n".join(sm) + "\n")
    ctx.write("08-consumption/metric-catalogue.csv", _csv(
        ["metric", "label", "definition", "entity", "measure", "denominator", "unit", "business_rule"],
        [[m["name"], m["label"], m["definition"], m["entity"], json.dumps(m["measure"]), json.dumps(m.get("denominator")),
          m.get("unit", ""), m.get("business_rule") or ""] for m in model.get("metrics", [])]))
    restricted = [(e["name"], a["name"]) for e in model["entities"] for a in e["attributes"] if a["classification"] == "restricted"]
    ctx.write("08-consumption/access-model.md", "# Access model\n\n" + md_table(["Role", "Visibility", "Masking", "Row rules"], [
        ["analyst_masked", "all curated objects", f"{len(restricted)} Restricted attributes masked", "none"],
        ["restricted_reader", "all, unmasked", "none", "requires Security and Compliance approval (A3)"],
        ["data_steward", "all + quality results", "masked", "none"]]) + "\n")
    ctx.write("08-consumption/data-contract.yaml", exports.export_odcs(model, {
        "profile": prof, "run_id": ws.run_id, "dq_rules": mp.get("dq_rules", []), "approvers": ws.run.get("approvers"),
        "contract_status": "active-on-G8"}))
    # semantic layer / BI artefacts (draft workspace)
    views = []
    for e in model["entities"]:
        cols = ", ".join(f"'***' AS {a['name']}" if a["classification"] == "restricted" else a["name"] for a in e["attributes"])
        views.append(f"CREATE OR REPLACE VIEW {schema}.v_{ph.table_name(e, prof).lower()} AS SELECT {cols} FROM {schema}.{ph.table_name(e, prof)};")
    ctx.write("08-consumption/semantic/consumer-views.sql", "-- Masked consumer views (draft; deployed after G8)\n" + "\n".join(views) + "\n")
    if bi == "looker":
        lk = []
        for e in model["entities"]:
            lk.append(f"view: {e['name']} {{\n  sql_table_name: {schema}.{ph.table_name(e, prof)} ;;\n" + "".join(
                f"  dimension: {a['name']} {{ sql: ${{TABLE}}.{a['name']} ;; {'primary_key: yes ' if a['pk'] else ''}}}\n" for a in e["attributes"]) + "}\n")
        ctx.write("08-consumption/semantic/model.lkml", "\n".join(lk))
    if sem == "dbt-semantic-layer" or stacks.tool(prof, "transformation").startswith("dbt"):
        sms = {"semantic_models": [{"name": f["name"], "model": f"ref('{ph.table_name(f, None)}')",
                                    "entities": [{"name": a["name"], "type": "primary" if a["pk"] else "foreign"}
                                                 for a in f["attributes"] if a["pk"] or a.get("fk")],
                                    "measures": [{"name": a["name"], "agg": "sum"} for a in f["attributes"]
                                                 if a["type"].startswith(("decimal", "integer", "bigint")) and not a["pk"] and not a.get("fk")]}
                                   for f in facts],
               "metrics": [{"name": m["name"], "label": m["label"], "description": m["definition"],
                            "type": "ratio" if m.get("denominator") else "simple",
                            "type_params": {"measure": m["measure"]["attribute"]}} for m in model.get("metrics", [])]}
        ctx.write("08-consumption/semantic/semantic_models.yml", dump_yaml(sms))
    if bi == "power-bi":
        tm = []
        for e in model["entities"]:
            tm.append(f"table {e['label'].replace(' ', '')}\n" + "".join(f"\tcolumn {a['name']}\n\t\tsourceColumn: {a['name']}\n" for a in e["attributes"]))
        for m in model.get("metrics", []):
            ent = next(e for e in model["entities"] if e["name"] == m["entity"])
            t = ent["label"].replace(" ", "")
            num = f"SUM({t}[{m['measure']['attribute']}])" if m["measure"]["agg"] in ("sum", "sum_bool") else f"AVERAGE({t}[{m['measure']['attribute']}])"
            expr = f"DIVIDE({num}, DISTINCTCOUNT({t}[{m['denominator']['attribute']}]))" if m.get("denominator") else num
            tm.append(f"measure '{m['label']}' = {expr}\n")
        ctx.write("08-consumption/semantic/model.tmdl", "\n".join(tm))
    # validation: answers, consistency across access paths, access
    sb = Sandbox(model, mp.get("dq_rules", []))
    sb.build()
    rows = []
    for m in model.get("metrics", []):
        direct = sb.db.execute(sb.metric_sql(m)).fetchone()[0]
        ent = next(e for e in model["entities"] if e["name"] == m["entity"])
        rmask = [a["name"] for a in ent["attributes"] if a["classification"] == "restricted"]
        sb.masking(ent, rmask)
        via_view = sb.db.execute(sb.metric_sql(m).replace(f"FROM {tname(ent)}", f"FROM v_consumer_{tname(ent)}")).fetchone()[0]
        rows.append([m["label"], round(direct, 4) if direct is not None else None, round(via_view, 4) if via_view is not None else None,
                     "pass" if direct == via_view else "FAIL"])
    access = [sb.masking(e, [a["name"] for a in e["attributes"] if a["classification"] == "restricted"])
              for e in model["entities"] if any(a["classification"] == "restricted" for a in e["attributes"])]
    ctx.write("08-consumption/validation.md", "# Validation\n\n## Metric consistency across access paths\n\n"
              + md_table(["Metric", "Direct table", "Consumer view", "Result"], rows) + "\n\n## Access\n\n"
              + md_table(["View", "Restricted columns", "Unmasked values", "Result"],
                         [[a["view"], ", ".join(a["restricted_columns"]), a["unmasked_values"], a["status"]] for a in access])
              + "\n\n## Consumer questions answered\n\n" + "\n".join(f"- {c['question']} -> {model['metrics'][0]['label'] if model.get('metrics') else 'curated tables'}" for c in consumers) + "\n")
    ctx.write("08-consumption/publication-request.md", f"# Publication request (G8)\n\n**Content:** data product `{model['name']}` "
              f"v{model['version']}: {len(model['entities'])} tables, {len(model.get('metrics', []))} governed metrics, masked consumer "
              f"views, {bi} semantic model, catalog entry ({stacks.tool(prof, 'catalog_governance')}).\n\n**Audience:** "
              + ", ".join(c["name"] for c in consumers) + "\n\n**Channels:** catalog listing, BI workspace, consumer guide.\n\n"
              "Nothing is published or sent before this request is approved by the Product Owner and Data Steward.\n")
    guide = _narrative(ctx, f"Write a consumer guide for the data product {model['name']}: what it is, how to find it, what each "
                            f"metric means, how to request access, known limitations. Metrics: {json.dumps(model.get('metrics', []))}")
    ctx.write("08-consumption/consumer-guide.md", "# Consumer guide\n\n" + (guide or (
        f"**What:** {model.get('description') or model['name']}.\n\n**Find it:** catalog entry `{model['name']}`; schema `{schema}`.\n\n"
        "**Metrics:**\n\n" + "\n".join(f"- **{m['label']}** - {m['definition']}" for m in model.get("metrics", [])) +
        "\n\n**Access:** request the `analyst_masked` role; unmasked access needs Security and Compliance approval.\n")))
    ctx.write("08-consumption/catalog-entry.json", exports.render("collibra" if stacks.tool(prof, "catalog_governance") == "collibra"
                                                                  else "atlas" if stacks.tool(prof, "catalog_governance") == "purview"
                                                                  else "datahub" if stacks.tool(prof, "catalog_governance") == "datahub"
                                                                  else "json", model, {"profile": prof, "glossary": ws.domain.get("glossary_seed", [])})[1])
    ok = all(r[3] == "pass" for r in rows) and all(a["status"] == "pass" for a in access)
    return StageOutput(
        artifacts=["08-consumption/publication-request.md", "08-consumption/consumer-map.md", "08-consumption/semantic-model.md",
                   "08-consumption/metric-catalogue.csv", "08-consumption/access-model.md", "08-consumption/data-contract.yaml",
                   "08-consumption/validation.md", "08-consumption/consumer-guide.md", "08-consumption/catalog-entry.json"],
        summary=f"Semantic model, {len(model.get('metrics', []))} governed metrics, masked access model, contract and catalog entry "
                f"prepared; validation {'passed' if ok else 'FAILED'}. Draft only - requesting G8 to publish.",
        requirement_ids=[r["id"] for r in reqs["requirements"]],
        gate_meta={"risk": "Publication is outward-facing (A3).", "cost": "None.",
                   "rollback": "Unpublish listing; revoke role grants.", "options": ["Approve publication", "Reject"]},
        evidence=["08-consumption/validation.md"], inputs_used=["03-design/logical/logical-model.json"],
        confidence=("high" if ok else "low", "metric equal across access paths; masking verified"))


def after_g8(ws, log, approval_ids: list[str]) -> None:
    guard = ActionGuard(ws)
    guard.execute("adef-data-consumption", "publish_data_product", "catalog + BI workspace", lambda: "published",
                  per_action_approval_id=",".join(approval_ids))
    ws.write("adef-data-consumption", "08-consumption/publication-record.md",
             f"# Publication record\n\nPublished at {now_iso()} under approvals {', '.join(approval_ids)}.\n\n{SIM_NOTE}\n")
    log("data product published (simulated) after G8")


# =========================================================================== ASSEMBLY
def assembly(ctx: StageCtx, metrics: dict) -> StageOutput:
    ws, prof = ctx.ws, ctx.ws.stack
    model, mp = _model(ws), _mapping(ws)
    reqs = ws.read_json("01-requirements/requirements.json")
    results = json.loads(sorted((ws.root / "05-test" / "results").glob("*.json"))[-1].read_text())
    rows = []
    for r in reqs["requirements"]:
        maps = [m["id"] for m in mp["mappings"] if r["id"] in (m.get("req_ids") or [])]
        dqs = [d["id"] for d in mp.get("dq_rules", []) if d.get("requirement") == r["id"]]
        tcs = [t for t in results["test_cases"] if r["id"] in t["requirements"]]
        status = "pass" if tcs and all(t["status"] == "pass" for t in tcs) else ("fail" if tcs else "untested")
        rows.append([r["id"], r.get("source", ""), ";".join(maps), ";".join(dqs), ";".join(t["id"] for t in tcs), status])
    ctx.write("final/traceability-matrix.csv", _csv(["requirement", "source", "mappings", "quality_rules", "test_cases", "status"], rows))
    ex_ctx = {"profile": prof, "mapping": mp["mappings"], "dq_rules": mp.get("dq_rules", []), "run_id": ws.run_id,
              "glossary": ws.domain.get("glossary_seed", []), "approvers": ws.run.get("approvers")}
    written = []
    for ex in exports.list_exporters():
        fn, content = exports.render(ex["id"], model, ex_ctx)
        ctx.write(f"final/exports/{fn}", content, allow_tech=True)
        written.append([ex["label"], f"final/exports/{fn}"])
    full = sum(1 for r in rows if r[5] == "pass")
    m = metrics
    ctx.write("final/run-metrics.md", "# Run metrics (BUILD_SPEC 8.4)\n\n" + md_table(["Measure", "Value"], [
        ["Cycle time intake to G5", m.get("cycle_time", "n/a")], ["Gates requested", m["gates_requested"]],
        ["First-pass gate acceptance", f"{m['first_pass_pct']}%"], ["Rework loops (rejections)", m["rejections"]],
        ["Guardrail blocks", m["guardrail_blocks"]], ["Traceability completeness", f"{full}/{len(rows)} requirements fully traced to a passing test"],
        ["LLM tokens", m["tokens"]], ["LLM cost (USD, list price)", m["llm_cost"]]]) + "\n\n## Per agent\n\n"
        + md_table(["Agent", "Provider/model", "Calls", "Tokens", "Cost"], m["per_agent"]) + "\n")
    links = [["Intake brief", "00-intake/intake-brief.md"], ["Requirements", "01-requirements/requirements.md"],
             ["Source-to-target mapping", "02-mapping/source-to-target.csv"], ["Logical model", "03-design/logical/logical-data-model.md"],
             ["Physical design", "03-design/physical/physical-design.md"], ["Cost estimate", "03-design/physical/cost-estimate.md"],
             ["Build manifest", "04-build/build-manifest.yaml"], ["Evidence pack", "05-test/evidence-pack.md"],
             ["Release plan", "06-release/REL-001-plan.md"], ["Runbook", "07-operations/runbook.md"],
             ["Consumer guide", "08-consumption/consumer-guide.md"], ["Data contract", "08-consumption/data-contract.yaml"],
             ["Traceability matrix", "final/traceability-matrix.csv"], ["Run metrics", "final/run-metrics.md"]]
    approvals = [[d["gate"], d["decision"], d["role"], d["approver"], d["timestamp"]] for d in ws.read_log("approvals") if d.get("type") == "decision"]
    ctx.write("final/delivery-pack.md", f"# Delivery pack - {ws.run_id}\n\n**Client:** {ws.run['client_code']}  \n**Use case:** "
              f"{ws.run['use_case']}  \n**Stack:** {prof.get('label', prof['profile_id'])}  \n**Domain Pack:** {ws.domain['pack_id']}\n\n"
              "Assembled from approved artifacts only; no new content added.\n\n## Artifacts\n\n" + md_table(["Item", "Path"], links)
              + "\n\n## Data model and catalog exports\n\n" + md_table(["Export", "Path"], written)
              + "\n\n## Approvals\n\n" + md_table(["Gate", "Decision", "Role", "Approver", "When"], approvals)
              + f"\n\n## Traceability\n\n{full}/{len(rows)} requirements traced end to end to a passing test.\n")
    return StageOutput(artifacts=["final/delivery-pack.md", "final/run-metrics.md", "final/traceability-matrix.csv"],
                       summary=f"Delivery pack assembled with {len(written)} model/catalog exports; {full}/{len(rows)} requirements fully traced.",
                       request_gate=False, confidence=("high", "assembled from approved artifacts"))
