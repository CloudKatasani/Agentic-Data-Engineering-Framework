"""Command line: `python -m adef.cli serve|demo|suite|validate-stack|export`."""
from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(prog="adef", description="Agentic Data Engineering Framework")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web console and API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--allow-insecure", action="store_true",
                   help="allow a non-local bind without ADEF_API_TOKEN (not recommended)")
    d = sub.add_parser("demo", help="run a full lifecycle headless, auto-approving as the demo approver")
    d.add_argument("--domain", default="utilities", choices=["utilities", "telco", "financial-services", "retail"])
    d.add_argument("--stack", default="example-a")
    sub.add_parser("suite", help="run guardrail scenarios GT-01..GT-18")
    sd = sub.add_parser("source-db", help="build or seed a synthetic source database (SQLite, Oracle, Db2)")
    sd.add_argument("action", choices=["build", "seed", "scripts"])
    sd.add_argument("--domain", default="telco", choices=["utilities", "telco", "financial-services", "retail"])
    sd.add_argument("--type", default="sqlite-local", choices=["sqlite-local", "oracle", "db2", "postgres"])
    sd.add_argument("--dsn", help="Oracle host:port/service or PostgreSQL DSN")
    sd.add_argument("--host", default="localhost")
    sd.add_argument("--port", type=int, default=50000)
    sd.add_argument("--database", default="ADEF")
    sd.add_argument("--user")
    sd.add_argument("--password-env", default="SOURCE_DB_PASSWORD",
                    help="environment variable holding the password (never pass passwords as arguments)")
    sd.add_argument("--out", default="demo-data")
    dd = sub.add_parser("demo-data", help="generate the synthetic demo data packs (Jira, metadata, data, model, catalog, lineage)")
    dd.add_argument("--out", default="demo-data")
    sk = sub.add_parser("synthetic-kit", help="generate a production-grade synthetic data kit (zip) for a domain")
    sk.add_argument("--domain", default="telco")
    sk.add_argument("--scale", default="medium", choices=["small", "medium", "large"])
    sk.add_argument("--out", default="synthetic-kits")
    v = sub.add_parser("validate-stack", help="validate a Stack Profile YAML file")
    v.add_argument("file")
    e = sub.add_parser("export", help="export a run's logical model")
    e.add_argument("run_id")
    e.add_argument("format")
    e.add_argument("--dialect")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        return serve(a)
    if a.cmd == "synthetic-kit":
        from pathlib import Path

        from . import synthetic_kit
        path = synthetic_kit.write(a.domain, a.scale, Path(a.out))
        print(f"{path} ({path.stat().st_size // 1024:,} KB)")
        return 0
    if a.cmd == "source-db":
        import os
        from . import sources
        if a.action == "scripts":
            w = sources.write_seed_scripts(a.out, [a.domain])
            print("\n".join(f"{k} ({v // 1024} KB)" for k, v in w.items()))
            return 0
        if a.action == "build" or a.type == "sqlite-local":
            print(f"SQLite source for {a.domain}: {sources.build_sqlite(a.domain, force=a.action == 'build')}")
            return 0
        pw = os.environ.get(a.password_env)
        if not pw:
            print(f"Set the password in ${a.password_env} first.")
            return 2
        cfg = {"type": a.type, "dsn": a.dsn, "host": a.host, "port": a.port, "database": a.database,
               "user": a.user, "password": pw}
        print(sources.seed(cfg, a.domain))
        return 0
    if a.cmd == "demo-data":
        from .demo_data import generate
        m = generate(a.out)
        print(f"wrote {len(m)} files to {a.out}/ ({sum(v['bytes'] for v in m.values()) // 1024} KB)")
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


def serve(a) -> int:
    import uvicorn

    from .catalog.providers import ENV_KEYS, env_key_for
    from .config import adef_home, env
    from .settings_store import SettingsStore
    public = a.host not in ("127.0.0.1", "localhost", "::1")
    if public and not env("API_TOKEN") and not a.allow_insecure:
        print("Refusing to listen on a public interface without an access token.\n"
              "Set ADEF_API_TOKEN (e.g. export ADEF_API_TOKEN=$(openssl rand -hex 24)) or bind to 127.0.0.1.")
        return 2
    st = SettingsStore().load()
    keys = [f"{pid} ({env_key_for(pid)})" for pid in ENV_KEYS if env_key_for(pid)]
    print(f"ADEF console:  http://{'localhost' if a.host in ('0.0.0.0', '127.0.0.1') else a.host}:{a.port}")
    print(f"Data home:     {adef_home()}")
    print(f"API keys:      {', '.join(keys) if keys else 'none in the environment (agents use the Demo Simulator fallback)'}")
    print(f"Agent team:    {st['runtime'].get('team_preset', 'custom')}")
    print(f"Access token:  {'required' if env('API_TOKEN') else 'not set (local use only)'}")
    uvicorn.run("adef.api.app:app", host=a.host, port=a.port, proxy_headers=True, forwarded_allow_ips="127.0.0.1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
