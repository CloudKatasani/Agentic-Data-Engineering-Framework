"""REST API and web console for the Agentic Data Engineering Framework (ADEF)."""
from __future__ import annotations

import io
import json
import os
import re
import secrets as pysecrets
import zipfile
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..catalog import stacks
from ..catalog.domains import list_packs, load_pack
from ..catalog.providers import EFFORT_LEVELS, PROVIDER_TYPES, SEED_PROVIDERS, TEAM_PRESETS, provider_ready
from ..config import AGENTS_DIR, DEMO_DATA_DIR, WEB_DIR
from ..config import env as config_env
from ..connectors import jira_export
from ..connectors.jira import JiraClient, JiraError
from ..engine.orchestrator import InputRejected, get_engine
from ..engine.stages import GATE_LABELS, STAGES
from ..guardrails.actions import ACTION_TABLE, GuardrailBlocked
from ..guardrails.gt_suite import run_suite
from ..llm.base import LLMError
from ..llm.router import build_provider
from ..modeling import exports, importers
from ..modeling.logical import normalize, validate_model
from ..secrets_store import SecretNotFound, SecretStore
from ..settings_store import AGENT_NAMES, SettingsStore
from ..util import load_yaml
from ..workspace.run import GATE_ROLES, ROLE_LABELS

app = FastAPI(title="ADEF - Agentic Data Engineering Framework", version=__version__)
settings = SettingsStore()
vault = SecretStore()
API_TOKEN = config_env("API_TOKEN")


@app.middleware("http")
async def auth(request: Request, call_next):
    if API_TOKEN and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or request.query_params.get("token", "")
        if not pysecrets.compare_digest(tok, API_TOKEN):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"  # revalidate (ETag) so console updates show up immediately
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.exception_handler(GuardrailBlocked)
async def _gb(_, e: GuardrailBlocked):
    return JSONResponse({"detail": e.message, "rule": e.rule, "guardrail": True}, status_code=409)


@app.exception_handler(InputRejected)
async def _ir(_, e: InputRejected):
    return JSONResponse({"detail": str(e), "guardrail": True}, status_code=422)


@app.exception_handler(KeyError)
async def _ke(_, e: KeyError):
    return JSONResponse({"detail": f"not found: {e}"}, status_code=404)


def engine():
    return get_engine()


# ----------------------------------------------------------------------------- catalog
def _agent_defs() -> list[dict]:
    out = []
    for name in AGENT_NAMES:
        text = (AGENTS_DIR / f"{name}.md").read_text()
        fm = load_yaml(text.split("---")[1])
        out.append({"name": name, "description": fm.get("description", ""), "skills": fm.get("skills", "")})
    return out


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/catalog")
def catalog():
    return {"provider_types": PROVIDER_TYPES, "effort_levels": EFFORT_LEVELS, "team_presets": TEAM_PRESETS,
            "pipeline_slots": stacks.PIPELINE_SLOTS,
            "preset_pipelines": {p["profile_id"]: {"steps": stacks.pipeline_summary(p), "local": stacks.is_local(p)}
                                 for p in stacks.PRESETS}, "slots": stacks.SLOTS,
            "presets": stacks.PRESETS, "domain_packs": list_packs(), "exporters": exports.list_exporters(),
            "dialects": list(exports.ph.DIALECT_LABELS.items()), "stages": STAGES, "gate_labels": GATE_LABELS,
            "gate_roles": GATE_ROLES, "role_labels": ROLE_LABELS, "agents": _agent_defs(),
            "action_table": [{"action": a, "class": c, "gate": g, "per_action": p} for a, (c, g, p) in ACTION_TABLE.items()]}


@app.get("/api/domain-packs/{pack_id}")
def domain_pack(pack_id: str):
    return load_pack(pack_id)


# ----------------------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings():
    return settings.load()


@app.put("/api/settings/providers")
def put_providers(providers: list[dict] = Body(...)):
    seen = set()
    for p in providers:
        if p.get("type") not in PROVIDER_TYPES:
            raise HTTPException(400, f"unknown provider type {p.get('type')}")
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", p.get("id", "")):
            raise HTTPException(400, "provider id must be lowercase letters, digits and dashes")
        if p["id"] in seen:
            raise HTTPException(400, f"duplicate provider id {p['id']}")
        seen.add(p["id"])
        ref = p.get("api_key_ref") or ""
        if ref and not (ref.startswith(("secret:", "env:"))):
            raise HTTPException(400, "api_key_ref must be secret:<vault name> or env:<VAR>; never paste a key here")
    if "demo" not in seen:
        raise HTTPException(400, "the demo simulator provider cannot be removed")
    return settings.update("providers", providers)["providers"]


@app.put("/api/settings/agents")
def put_agents(agents: dict = Body(...)):
    data = settings.load()
    pids = {p["id"] for p in data["providers"]}
    for name, b in agents.items():
        if name not in AGENT_NAMES:
            raise HTTPException(400, f"unknown agent {name}")
        if b.get("provider_id") not in pids:
            raise HTTPException(400, f"{name}: unknown provider {b.get('provider_id')}")
        if not b.get("model"):
            raise HTTPException(400, f"{name}: model is required")
        if b.get("effort") and b["effort"] not in EFFORT_LEVELS:
            raise HTTPException(400, f"{name}: bad effort")
        data["agents"][name] = {"provider_id": b["provider_id"], "model": b["model"].strip(),
                                "effort": b.get("effort", "medium"), "max_tokens": int(b.get("max_tokens") or 16000)}
    return settings.save(data)["agents"]


@app.post("/api/settings/agents/preset")
def apply_team_preset(body: dict = Body(...)):
    preset = TEAM_PRESETS.get(body.get("preset", ""))
    if not preset:
        raise HTTPException(400, "unknown team preset")
    data = settings.load()
    have = {p["id"] for p in data["providers"]}
    for b in preset["agents"].values():
        if b["provider_id"] not in have:
            seed = next(p for p in SEED_PROVIDERS if p["id"] == b["provider_id"])
            data["providers"].append(dict(seed))
            have.add(seed["id"])
    data["agents"] = {k: dict(v) for k, v in preset["agents"].items()}
    data.setdefault("runtime", {})["team_preset"] = body["preset"]
    return settings.save(data)


@app.put("/api/settings/runtime")
def put_runtime(body: dict = Body(...)):
    data = settings.load()
    rt = data.setdefault("runtime", {})
    if "simulate_unavailable_providers" in body:
        rt["simulate_unavailable_providers"] = bool(body["simulate_unavailable_providers"])
    return settings.save(data)["runtime"]


@app.get("/api/providers/readiness")
def providers_readiness():
    return {p["id"]: provider_ready(p) for p in settings.load()["providers"]}


@app.put("/api/settings/approvers")
def put_approvers(approvers: dict = Body(...)):
    if set(approvers) - set(ROLE_LABELS):
        raise HTTPException(400, "unknown role")
    return settings.update("approver_defaults", approvers)["approver_defaults"]


@app.post("/api/providers/{pid}/test")
def test_provider(pid: str, body: dict = Body(default={})):
    p = settings.provider(pid)
    if not p:
        raise HTTPException(404, "provider not found")
    model = body.get("model") or PROVIDER_TYPES[p["type"]]["models"][0]["id"]
    try:
        res = build_provider(p, vault).test(model)
        return {"ok": True, "model": res.model, "reply": res.text[:200], "tokens": res.input_tokens + res.output_tokens}
    except LLMError as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/providers/{pid}/models")
def provider_models(pid: str):
    p = settings.provider(pid)
    if not p:
        raise HTTPException(404, "provider not found")
    try:
        return {"ok": True, "models": build_provider(p, vault).list_models()}
    except LLMError as e:
        return {"ok": False, "error": str(e), "models": []}


# ----------------------------------------------------------------------------- secrets
@app.get("/api/secrets")
def list_secrets():
    return vault.list()


@app.post("/api/secrets")
def put_secret(body: dict = Body(...)):
    try:
        return vault.put(body.get("name", ""), body.get("value", ""), body.get("description", ""))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/secrets/{name}")
def delete_secret(name: str):
    vault.delete(name)
    return {"ok": True}


# ----------------------------------------------------------------------------- jira
@app.put("/api/settings/jira")
def put_jira(cfg: dict = Body(...)):
    ref = cfg.get("token_ref") or ""
    if ref and not ref.startswith(("secret:", "env:")):
        raise HTTPException(400, "token_ref must be secret:<vault name> or env:<VAR>")
    keep = {k: cfg.get(k, "") for k in ("mode", "base_url", "deployment", "email", "token_ref", "default_jql", "acceptance_field")}
    return settings.update("jira", keep)["jira"]


@app.post("/api/jira/test")
def jira_test():
    try:
        return JiraClient(settings.load()["jira"], vault).test()
    except JiraError as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/jira/projects")
def jira_projects():
    try:
        return JiraClient(settings.load()["jira"], vault).projects()
    except JiraError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/jira/search")
def jira_search(body: dict = Body(...)):
    try:
        return JiraClient(settings.load()["jira"], vault).search(body.get("jql", ""), int(body.get("max_results", 50)))
    except JiraError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/jira/import")
async def jira_import(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 10_000_000:
        raise HTTPException(413, "file larger than 10 MB")
    try:
        return jira_export.parse(file.filename or "export.csv", raw.decode("utf-8-sig", errors="replace"))
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        raise HTTPException(400, f"could not read the Jira export: {e}") from e


# ----------------------------------------------------------------------------- demo data packs
@app.get("/api/demo-files")
def demo_files():
    if not DEMO_DATA_DIR.exists():
        return []
    out = []
    for p in sorted(DEMO_DATA_DIR.rglob("*")):
        if p.is_file():
            rel = p.relative_to(DEMO_DATA_DIR)
            parts = rel.parts
            out.append({"path": str(rel), "domain": parts[0] if len(parts) > 1 else "", "folder": parts[1] if len(parts) > 2 else "",
                        "name": p.name, "bytes": p.stat().st_size})
    return out


def _demo_path(path: str) -> Path:
    p = (DEMO_DATA_DIR / path).resolve()
    if not (str(p) + "/").startswith(str(DEMO_DATA_DIR.resolve()) + "/") or p == DEMO_DATA_DIR.resolve():
        raise HTTPException(404, "no such demo file")
    return p


@app.get("/api/demo-files/file")
def demo_file(path: str):
    p = _demo_path(path)
    if not p.is_file():
        raise HTTPException(404, "no such demo file")
    return Response(p.read_bytes(), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


@app.get("/api/demo-files/zip")
def demo_folder_zip(folder: str):
    """Download a demo folder (e.g. telco/client-demo-kit) as one zip."""
    d = _demo_path(folder)
    if not d.is_dir():
        raise HTTPException(404, "no such demo folder")
    buf = io.BytesIO()
    name = "-".join(d.relative_to(DEMO_DATA_DIR.resolve()).parts)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                z.write(f, f"{name}/{f.relative_to(d)}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


# ----------------------------------------------------------------------------- stacks
@app.post("/api/stacks/validate")
def validate_stack(profile: dict = Body(...)):
    return stacks.validate(profile)


@app.post("/api/stacks")
def save_stack(profile: dict = Body(...)):
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", profile.get("profile_id", "")):
        raise HTTPException(400, "profile_id must be lowercase letters, digits and dashes")
    if stacks.preset(profile["profile_id"]):
        raise HTTPException(400, "choose a profile_id that differs from the built-in presets")
    v = stacks.validate(profile)
    data = settings.load()
    data["stack_profiles"] = [p for p in data["stack_profiles"] if p["profile_id"] != profile["profile_id"]] + [profile]
    settings.save(data)
    return {"saved": True, "validation": v}


@app.delete("/api/stacks/{pid}")
def delete_stack(pid: str):
    data = settings.load()
    data["stack_profiles"] = [p for p in data["stack_profiles"] if p["profile_id"] != pid]
    settings.save(data)
    return {"ok": True}


# ----------------------------------------------------------------------------- metadata + model studio
@app.post("/api/metadata/import")
async def import_metadata(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(413, "file larger than 5 MB")
    try:
        meta = importers.detect_and_parse(file.filename or "upload", raw.decode("utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(400, f"could not parse: {e}") from e
    meta["logical_model"] = importers.to_logical_model(meta, re.sub(r"\W+", "-", Path(file.filename or "model").stem).lower())
    return meta


@app.post("/api/models/export")
def export_model(body: dict = Body(...)):
    model = normalize(body["model"])
    problems = validate_model(model)
    if problems:
        raise HTTPException(400, "; ".join(problems[:5]))
    prof = engine().stack_by_id(body["profile_id"]) if body.get("profile_id") else None
    ctx = {"profile": prof, "dialect": body.get("dialect"), "glossary": []}
    fn, content = exports.render(body["format"], model, ctx)
    return Response(content, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


# ----------------------------------------------------------------------------- runs
@app.get("/api/runs")
def runs():
    return engine().list_runs()


@app.post("/api/runs")
def create_run(body: dict = Body(...)):
    return engine().create_run(body)


@app.get("/api/runs/{rid}")
def run_status(rid: str):
    return engine().status(rid)


@app.delete("/api/runs/{rid}")
def delete_run(rid: str):
    import shutil
    ws = engine().ws(rid)
    shutil.rmtree(ws.root)
    return {"ok": True}


@app.get("/api/runs/{rid}/events")
def run_events(rid: str, after: int = 0):
    ev = engine().ws(rid).read_log("events")
    return {"events": [{"i": i, "ts": e["ts"], "kind": e["kind"], "text": e["text"]} for i, e in enumerate(ev) if i >= after],
            "next": len(ev)}


@app.get("/api/runs/{rid}/files")
def run_files(rid: str):
    return engine().ws(rid).files()


@app.get("/api/runs/{rid}/file")
def run_file(rid: str, path: str):
    ws = engine().ws(rid)
    p = ws.path(path)
    if not p.is_file():
        raise HTTPException(404, "no such file")
    return Response(p.read_text(errors="replace"), media_type="text/plain; charset=utf-8")


@app.put("/api/runs/{rid}/file")
def edit_file(rid: str, body: dict = Body(...)):
    return engine().human_edit(rid, body["path"], body["content"], body.get("editor", "human"))


@app.post("/api/runs/{rid}/gates/{gate}/decision")
def gate_decision(rid: str, gate: str, body: dict = Body(...)):
    return engine().decide(rid, gate, body["approver"], body["role"], body["decision"], body.get("comment", ""),
                           [c for c in body.get("conditions", []) if c])


@app.post("/api/runs/{rid}/gates/{gate}/review")
def gate_review(rid: str, gate: str, body: dict = Body(...)):
    """Approve or reject every artifact of a gate individually; the gate decision follows from the reviews."""
    roles = body.get("roles") or ([body["role"]] if body.get("role") else [])
    try:
        return engine().review_gate(rid, gate, body["approver"], roles, body.get("reviews") or [],
                                    [c for c in body.get("conditions", []) if c])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/runs/{rid}/gates/{gate}/rerequest")
def gate_rerequest(rid: str, gate: str):
    return engine().rerequest(rid, gate)


@app.post("/api/runs/{rid}/stages/{key}/rework")
def stage_rework(rid: str, key: str, body: dict = Body(default={})):
    engine().rework(rid, key, body.get("feedback", ""))
    return {"ok": True}


@app.post("/api/runs/{rid}/stages/{key}/start")
def stage_start(rid: str, key: str):
    engine().start_stage(rid, key)
    return {"ok": True}


@app.post("/api/runs/{rid}/resume")
def run_resume(rid: str):
    """Continue a run that is not waiting on a person (after a restart, or with autopilot off)."""
    try:
        return engine().resume(rid)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/runs/{rid}/logs/{name}")
def run_log(rid: str, name: str):
    if name not in ("approvals", "action-log", "decision-log", "events"):
        raise HTTPException(404, "unknown log")
    return engine().ws(rid).read_log(name)


@app.get("/api/runs/{rid}/handoffs")
def run_handoffs(rid: str):
    ws = engine().ws(rid)
    out = []
    for f in sorted((ws.root / "control" / "handoffs").glob("*.yaml")):
        out.append({"file": f"control/handoffs/{f.name}", **load_yaml(f.read_text())})
    return out


@app.get("/api/runs/{rid}/integrity")
def run_integrity(rid: str):
    return engine().integrity(rid)


@app.get("/api/runs/{rid}/model")
def run_model(rid: str):
    ws = engine().ws(rid)
    if not ws.has("03-design/logical/logical-model.json"):
        raise HTTPException(404, "no logical model yet (design stage not complete)")
    return ws.read_json("03-design/logical/logical-model.json")


def _export_ctx(ws):
    mp = ws.read_json("02-mapping/mapping.json") if ws.has("02-mapping/mapping.json") else {"mappings": [], "dq_rules": []}
    return {"profile": ws.stack, "mapping": mp.get("mappings", []), "dq_rules": mp.get("dq_rules", []), "run_id": ws.run_id,
            "glossary": ws.domain.get("glossary_seed", []), "approvers": ws.run.get("approvers")}


@app.get("/api/runs/{rid}/exports/{fmt}")
def run_export(rid: str, fmt: str, dialect: str | None = None):
    ws = engine().ws(rid)
    model = run_model(rid)
    ctx = _export_ctx(ws)
    if dialect:
        ctx["dialect"] = dialect
    fn, content = exports.render(fmt, model, ctx)
    ws.log_action({"agent": "human", "action": "export_metadata", "class": "A0", "target": fn, "phase": "done"})
    return Response(content, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.get("/api/runs/{rid}/repo")
def run_repo(rid: str):
    ws = engine().ws(rid)
    root = ws.root / "repo"
    if not root.exists():
        return {"files": [], "log": ""}
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git/" not in str(p.relative_to(root)) + "/"
                   and not str(p.relative_to(root)).startswith(".git"))
    from ..engine.gitrepo import Repo
    try:
        log = Repo(root).git("log", "--oneline", "--graph", "--all", "-n", "20")
    except RuntimeError:
        log = ""
    return {"files": files, "log": log}


@app.get("/api/runs/{rid}/repo/file")
def run_repo_file(rid: str, path: str):
    ws = engine().ws(rid)
    p = ws.path(f"repo/{path}")
    if not p.is_file() or "/.git/" in str(p):
        raise HTTPException(404, "no such file")
    return Response(p.read_text(errors="replace"), media_type="text/plain; charset=utf-8")


@app.get("/api/runs/{rid}/bundle.zip")
def run_bundle(rid: str):
    ws = engine().ws(rid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in ws.root.rglob("*"):
            if p.is_file() and "/.git/" not in str(p):
                z.write(p, f"{rid}/{p.relative_to(ws.root)}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{rid}.zip"'})


# ----------------------------------------------------------------------------- lakehouse (real pipeline runs)
LAKE_REPORTS = {"rehearsal": "05-test/rehearsal/lakehouse-report.json", "test": "06-release/lakehouse-test.json",
                "prod": "06-release/lakehouse-prod.json"}


@app.get("/api/runs/{rid}/lakehouse")
def run_lakehouse(rid: str):
    ws = engine().ws(rid)
    out = {}
    for env_, path in LAKE_REPORTS.items():
        if ws.has(path):
            rep = ws.read_json(path)
            rep.pop("gold_sql", None)
            out[env_] = rep
    return {"executable_locally": stacks.is_local(ws.stack), "pipelines": stacks.pipeline_summary(ws.stack),
            "source": ws.run.get("source_connection"), "reports": out}


@app.get("/api/runs/{rid}/lakehouse/query")
def run_lakehouse_query(rid: str, env: str, table: str, limit: int = 25):
    from ..lakehouse.runner import query_serving
    ws = engine().ws(rid)
    if env not in LAKE_REPORTS:
        raise HTTPException(400, "unknown environment")
    db = ws.root / "lakehouse" / "analytics" / f"{env}.duckdb"
    if not db.exists():
        raise HTTPException(404, f"no analytics database for {env} yet")
    try:
        return query_serving(db, table, min(max(limit, 1), 200))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/runs/{rid}/lakehouse/rehearse")
def run_lakehouse_rehearse(rid: str):
    """Re-run the three pipelines in the rehearsal environment (incremental on the source watermark)."""
    from ..engine.agents_back import run_lakehouse as _run
    ws = engine().ws(rid)
    if not ws.has("03-design/logical/logical-model.json"):
        raise HTTPException(409, "the design stage must be complete first")
    try:
        rep = _run(ws, "rehearsal", lambda t: engine().event(ws, t, "action"))
    except Exception as e:  # noqa: BLE001 - source unreachable, driver missing, ...
        raise HTTPException(502, f"Pipeline run failed: {type(e).__name__}: {str(e).splitlines()[0][:300]}") from e
    ws.log_action({"agent": "human", "action": "run_sandbox_tests", "class": "A1", "target": "lakehouse:rehearsal",
                   "phase": "done", "status": rep["status"]})
    ws._raw_write(LAKE_REPORTS["rehearsal"], json.dumps(rep, indent=2, default=str))
    rep.pop("gold_sql", None)
    return rep


# ----------------------------------------------------------------------------- source databases
def _source_list() -> list[dict]:
    from ..engine.scenarios import SCENARIOS
    built_in = [{"id": f"synthetic-{p}", "type": "sqlite-local", "pack": p, "label": f"Synthetic {p} (SQLite, built in)",
                 "built_in": True} for p in SCENARIOS]
    return built_in + settings.load().get("sources", [])


@app.get("/api/sources")
def list_sources():
    return _source_list()


@app.put("/api/settings/sources")
def put_sources(items: list[dict] = Body(...)):
    clean = []
    for it in items:
        if it.get("built_in"):
            continue
        if it.get("type") not in ("oracle", "db2", "postgres"):
            raise HTTPException(400, "type must be oracle, db2 or postgres")
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", it.get("id", "")):
            raise HTTPException(400, "id must be lowercase letters, digits and dashes")
        ref = it.get("password_ref") or ""
        if ref and not ref.startswith(("secret:", "env:")):
            raise HTTPException(400, "password_ref must be secret:<vault name> or env:<VAR>")
        clean.append({k: it.get(k) for k in ("id", "type", "label", "dsn", "host", "port", "database", "user", "password_ref")})
    return settings.update("sources", clean)["sources"]


def _source_cfg(sid: str) -> dict:
    cfg = next((x for x in _source_list() if x["id"] == sid), None)
    if not cfg:
        raise HTTPException(404, "unknown source")
    return cfg


@app.post("/api/sources/{sid}/test")
def test_source(sid: str):
    from .. import sources as src
    try:
        con = src.connect(_source_cfg(sid), vault)
        tables = con.tables()
        counts = {}
        for t in tables[:40]:
            schema, name = t.split(".", 1)
            counts[t] = con.query(f"SELECT COUNT(*) FROM {schema}.{name}")[1][0][0]
        con.close()
        return {"ok": True, "tables": counts}
    except Exception as e:  # noqa: BLE001 - surface driver errors without secrets
        return {"ok": False, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"}


@app.post("/api/sources/{sid}/seed")
def seed_source(sid: str, body: dict = Body(...)):
    from .. import sources as src
    cfg = _source_cfg(sid)
    if cfg["type"] == "sqlite-local":
        return {"ok": True, "path": str(src.build_sqlite(cfg["pack"], force=True))}
    try:
        return {"ok": True, **src.seed(cfg, body.get("domain", "telco"), vault, log=lambda t: None)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"}


# ----------------------------------------------------------------------------- platform status
@app.get("/api/status")
def platform_status():
    from ..catalog.providers import ENV_KEYS, env_key_for
    st = settings.load()
    # "live" means a provider that can really answer: it has a key, or it is a local endpoint the operator pointed us at
    ready = {p["id"]: bool(p.get("api_key_ref")) or (p["type"] == "openai_compatible" and bool(os.environ.get("OLLAMA_BASE_URL")))
             for p in st["providers"]}
    ready["demo"] = True
    bound = {b["provider_id"] for b in st["agents"].values()}
    return {"keys_from_environment": [f"{pid}:{env_key_for(pid)}" for pid in ENV_KEYS if env_key_for(pid)],
            "team_preset": st.get("runtime", {}).get("team_preset"),
            "agents_with_live_model": sum(1 for b in st["agents"].values() if b["provider_id"] != "demo" and ready.get(b["provider_id"])),
            "agents_total": len(st["agents"]), "bound_providers_without_key": sorted(p for p in bound if not ready.get(p)),
            "demo_fallback": st.get("runtime", {}).get("simulate_unavailable_providers", True),
            "sources": len(_source_list()), "token_required": bool(API_TOKEN)}


# ----------------------------------------------------------------------------- guardrails
@app.post("/api/guardrails/suite")
def guardrail_suite():
    return run_suite(engine())


# ----------------------------------------------------------------------------- web console
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
_ = (SecretNotFound,)
