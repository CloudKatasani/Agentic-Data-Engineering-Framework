"""Build and Release hand over a code base: code output choices, release scripts, branches, and push to Git."""
import ast
import io
import os
import subprocess
import sys
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient

from adef.api.app import app
from adef.catalog.stacks import preset
from adef.engine import formats
from adef.engine.gitrepo import Repo
from adef.engine.orchestrator import InputRejected
from adef.guardrails.actions import GuardrailBlocked
from conftest import drive

c = TestClient(app)
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True).stdout.strip()


def test_build_and_release_offer_code_outputs_not_document_formats():
    a = formats.output_options("build", preset("example-a"))
    assert a["kind"] == "code" and set(a["options"]) == {"stack", "pyspark"}
    assert "SnowSQL" in a["options"]["stack"] and "Spark SQL" in a["options"]["stack"] and "PySpark jobs" in a["options"]["pyspark"]
    assert set(formats.output_options("build", preset("local-lakehouse"))["options"]) == {"stack"}
    rel = formats.output_options("release", preset("example-a"))
    assert rel["kind"] == "code" and rel["default"] == "cli" and "SnowSQL" in rel["options"]["cli"] and "deploy.py" in rel["options"]["python"]
    assert formats.output_options("design", preset("example-a"))["kind"] == "documents"
    api = c.post("/api/output-options", json={"stack_profile": "example-b"}).json()
    assert api["build"]["kind"] == "code" and api["requirements"]["options"].keys() == {"markdown", "html", "docx"}


def test_document_formats_are_refused_for_code_stages(engine):
    with pytest.raises(InputRejected):
        engine.create_run({"client_code": "ACME", "output_formats": {"build": "docx"}}, start=False)
    rid = engine.create_run({"client_code": "ACME", "stack_profile": "local-lakehouse"}, start=False)["run_id"]
    assert c.put(f"/api/runs/{rid}/stages/build/output-format", json={"format": "html"}).status_code == 400
    assert c.put(f"/api/runs/{rid}/stages/build/output-format", json={"format": "pyspark"}).status_code == 400   # not on this stack
    assert c.put(f"/api/runs/{rid}/stages/release/output-format", json={"format": "python"}).status_code == 200
    assert engine.status(rid)["output_options"]["release"]["kind"] == "code"


def test_pyspark_build_and_python_release_produce_a_reviewable_code_base(engine):
    rid = engine.create_run({"client_code": "ACME", "domain_pack": "telco", "stack_profile": "example-a",
                             "council_enabled": False, "output_formats": {"build": "pyspark", "release": "python"}})["run_id"]
    st = drive(engine, rid)
    ws = engine.ws(rid)
    manifest = ws.read_yaml("04-build/build-manifest.yaml")
    assert manifest["code_output"] == "pyspark" and manifest["languages"]["Python / PySpark"] >= 4 and manifest["checks"]["lint"] == "pass"
    repo = c.get(f"/api/runs/{rid}/repo").json()
    assert "release/REL-001" in repo["branches"] and repo["ref"] == "main"
    main = set(repo["files"])
    assert {"pipelines/02_curate/silver_to_gold.py", "pipelines/02_curate/run_curate.py", "pipelines/03_publish/publish.sql",
            "pipelines/03_publish/run_publish.sh", "scripts/check_sql.py", "scripts/verify_release_hash.py"} <= main
    assert "pipelines/02_curate/02_silver_to_gold.sql" not in main and not any(f.startswith("deploy/") for f in main)
    job = c.get(f"/api/runs/{rid}/repo/file?path=pipelines/02_curate/silver_to_gold.py").text
    ast.parse(job)
    assert "spark.sql(statement)" in job and "MERGE INTO" in job and "SparkSession" in job
    assert "snowsql --connection" in c.get(f"/api/runs/{rid}/repo/file?path=pipelines/03_publish/run_publish.sh").text
    rel = c.get(f"/api/runs/{rid}/repo?ref=release/REL-001").json()
    bundle = {f for f in rel["files"] if f.startswith("deploy/REL-001/")}
    assert bundle == {f"deploy/REL-001/{n}" for n in ("README.md", "deploy.py", "release-manifest.yaml", "rollback.sql", "verify.sql")}
    deploy = c.get(f"/api/runs/{rid}/repo/file?path=deploy/REL-001/deploy.py&ref=release/REL-001").text
    ast.parse(deploy)
    rm = yaml.safe_load(c.get(f"/api/runs/{rid}/repo/file?path=deploy/REL-001/release-manifest.yaml&ref=release/REL-001").text)
    assert rm["tested_commit"] == rel["heads"]["main"] and rm["deploy_style"] == "python" and rm["steps"]
    assert "06-release/REL-001-bundle.md" in st["gates_detail"]["G6a"]["request"]["artifacts"]
    assert "Release scripts parse" in ws.read("06-release/REL-001-prechecks.md")
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/runs/{rid}/repo/archive.zip?ref=release/REL-001").content))
    assert "deploy/REL-001/deploy.py" in z.namelist() and "pipelines/03_publish/publish.sql" in z.namelist()
    assert c.get(f"/api/runs/{rid}/repo?ref=nope").status_code == 404
    assert c.get(f"/api/runs/{rid}/repo/file?path=../control/run.yaml").status_code == 404


def test_release_scripts_refuse_unsafe_use(engine, tmp_path):
    rid = engine.create_run({"client_code": "ACME", "domain_pack": "retail", "stack_profile": "aws-redshift", "council_enabled": False})["run_id"]
    drive(engine, rid)
    src = engine.ws(rid).root / "repo"
    work = tmp_path / "checkout"
    _git(tmp_path, "clone", "-q", "--branch", "release/REL-001", str(src), str(work))
    script = work / "deploy" / "REL-001" / "deploy.sh"
    run = lambda *a, **env: subprocess.run(["bash", str(script), *a], cwd=work, env={**GIT_ENV, **env}, capture_output=True, text=True)  # noqa: E731
    assert run("staging").returncode == 2                                        # unknown environment
    assert run("prod").returncode == 3 and "change record" in run("prod").stdout  # production needs a change record
    (work / "pipelines" / "03_publish" / "publish.sql").write_text("-- tampered\n")
    _git(work, "commit", "-qam", "tamper with tested code")
    out = run("test")
    assert out.returncode == 5 and "differs from the tested commit" in out.stdout   # only the tested code is deployed
    tested = yaml.safe_load((work / "deploy" / "REL-001" / "release-manifest.yaml").read_text())["tested_commit"]
    check = lambda commit: subprocess.run([sys.executable, "scripts/verify_release_hash.py", commit], cwd=work, capture_output=True, text=True)  # noqa: E731
    assert check(tested).returncode == 0 and check("deadbeef").returncode == 1
    sql = subprocess.run([sys.executable, "scripts/check_sql.py", "."], cwd=work, capture_output=True, text=True)
    assert sql.returncode == 0 and "0 problem(s)" in sql.stdout


def test_git_repository_settings_are_validated():
    for bad in ({"url": "http://git.example.com/acme/data.git"}, {"url": "https://user:tok@git.example.com/acme/data.git"},
                {"url": "https://git.example.com/acme/data.git", "token_ref": "ghp_literaltoken"}, {"url": "file:///tmp/x.git"}):
        assert c.put("/api/settings/git-remote", json=bad).status_code == 400, bad
    ok = c.put("/api/settings/git-remote", json={"url": "https://git.example.com/acme/data.git", "token_ref": "secret:git-token"})
    assert ok.status_code == 200 and ok.json()["username"] == "x-access-token"
    c.put("/api/settings/git-remote", json={"url": ""})
    assert c.post("/api/git-remote/test").json() == {"ok": False, "error": "No repository URL is set"}


def test_branch_is_based_on_the_client_repository_and_pushed_without_touching_main(engine, tmp_path, monkeypatch):
    # the client's repository: a main branch with its own README and CI workflow
    seed, bare = tmp_path / "seed", tmp_path / "client.git"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    (seed / ".github" / "workflows").mkdir(parents=True)
    (seed / ".github" / "workflows" / "ci.yml").write_text("name: client-ci\non: [pull_request]\njobs: {}\n")
    (seed / "README.md").write_text("# Client data platform\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "client baseline")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    client_main = _git(bare, "rev-parse", "main")
    monkeypatch.setenv("ADEF_ALLOW_LOCAL_GIT_REMOTE", "1")
    assert c.put("/api/settings/git-remote", json={"url": f"file://{bare}"}).status_code == 200
    try:
        assert c.post("/api/git-remote/test").json()["ok"] is True
        rid = engine.create_run({"client_code": "ACME", "domain_pack": "telco", "stack_profile": "example-a", "council_enabled": False})["run_id"]
        drive(engine, rid)
        ws = engine.ws(rid)
        manifest = ws.read_yaml("04-build/build-manifest.yaml")
        assert manifest["based_on_remote_main"] is True and manifest["base_commit"] == client_main
        assert ".github/workflows/ci.yml" in manifest["kept_existing_files"]            # the client's own CI is not overwritten
        assert "client-ci" in Repo(ws.root / "repo").show("main", ".github/workflows/ci.yml")
        who = ws.run["approvers"]["tech_lead"]
        assert c.post(f"/api/runs/{rid}/repo/push", json={"by": "Stranger"}).status_code == 409
        r = c.post(f"/api/runs/{rid}/repo/push", json={"by": who})
        assert r.status_code == 200, r.text
        pushed = set(r.json()["branches"])
        assert pushed == {f"adef/{rid}/WP-001", "release/REL-001"}
        heads = _git(bare, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
        assert pushed <= set(heads) and _git(bare, "rev-parse", "main") == client_main    # main untouched
        assert _git(bare, "merge-base", "main", f"adef/{rid}/WP-001") == client_main      # opens as a normal pull request
        assert "deploy/REL-001/deploy.sh" in _git(bare, "ls-tree", "-r", "--name-only", "release/REL-001").splitlines()
        assert c.get(f"/api/runs/{rid}/repo").json()["pushes"][0]["by"] == who
        log = [a for a in ws.read_log("action-log") if a.get("action") == "push_branch_remote"]
        assert [a["phase"] for a in log] == ["before", "after"] and log[0]["class"] == "A2"
        with pytest.raises(RuntimeError, match="protected"):
            Repo(ws.root / "repo").push(f"file://{bare}", ["main"], GIT_ENV)
        with pytest.raises(GuardrailBlocked):
            engine.push_repo(rid, "adef-pipeline-build")                                   # an agent can never push
    finally:
        c.put("/api/settings/git-remote", json={"url": ""})
