"""Command line: `python -m adpe.cli serve|demo|suite|validate-stack|export`."""
from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(prog="adpe", description="Agentic Data Engineering Framework")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web console and API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    d = sub.add_parser("demo", help="run a full lifecycle headless, auto-approving as the demo approver")
    d.add_argument("--domain", default="utilities", choices=["utilities", "telco", "financial-services", "retail"])
    d.add_argument("--stack", default="example-a")
    sub.add_parser("suite", help="run guardrail scenarios GT-01..GT-14")
    v = sub.add_parser("validate-stack", help="validate a Stack Profile YAML file")
    v.add_argument("file")
    e = sub.add_parser("export", help="export a run's logical model")
    e.add_argument("run_id")
    e.add_argument("format")
    e.add_argument("--dialect")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("adpe.api.app:app", host=a.host, port=a.port)
        return 0
    from .engine.orchestrator import get_engine
    eng = get_engine()
    if a.cmd == "demo":
        from .connectors.jira import DEMO_PROJECTS, JiraClient
        proj = {v: k for k, v in DEMO_PROJECTS.items()}[a.domain]
        rid = eng.create_run({"client_code": "DEMO", "domain_pack": a.domain, "stack_profile": a.stack,
                              "jira_issues": JiraClient({"mode": "demo"}).search(f"project = {proj}")})["run_id"]
        print(f"{rid} started")
        seen = 0
        while True:
            time.sleep(0.3)
            st = eng.status(rid)
            ev = eng.ws(rid).read_log("events")
            for e_ in ev[seen:]:
                print(f"  [{e_['kind']}] {e_['text']}")
            seen = len(ev)
            if st["status"] == "completed":
                print(f"{rid} completed: runs/{rid}/final/delivery-pack.md")
                return 0
            if any(x["status"] in ("failed", "blocked") for x in st["stages"].values()):
                print("stopped: a stage failed or was blocked")
                return 1
            if any(x["status"] == "running" for x in st["stages"].values()):
                continue
            for g, gd in st["gates_detail"].items():
                if gd["state"] == "pending":
                    for role in gd["pending_roles"]:
                        eng.decide(rid, g, st["run"]["approvers"][role], role, "approved", "demo auto-approval by presenter")
    if a.cmd == "suite":
        from .guardrails.gt_suite import run_suite
        res = run_suite(eng)
        for r in res:
            print(f"{r['id']} {r['result'].upper():4} {r['scenario']}\n      {r['evidence'][:160]}")
        return 0 if all(r["result"] == "pass" for r in res) else 1
    if a.cmd == "validate-stack":
        import yaml
        from .catalog.stacks import validate
        print(json.dumps(validate(yaml.safe_load(open(a.file))), indent=2))
        return 0
    if a.cmd == "export":
        from .modeling.exports import render
        ws = eng.ws(a.run_id)
        from .api.app import _export_ctx
        ctx = _export_ctx(ws)
        if a.dialect:
            ctx["dialect"] = a.dialect
        fn, content = render(a.format, ws.read_json("03-design/logical/logical-model.json"), ctx)
        sys.stdout.write(content)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
