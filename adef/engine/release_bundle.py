"""Release as code: the deploy, verify and rollback scripts for one release, committed to a release branch.

The Release stage used to hand over documents only. A release that can be reviewed in a pull request and
run by the CI/CD pipeline identity needs code: an ordered deploy script, a verification script, a rollback
script and a manifest that pins the tested commit. Two styles are generated on request:

- "cli":    a bash script that drives the platform's own command-line clients (SnowSQL, bq, psql, ...);
- "python": the same steps as a Python script, for pipelines that standardise on Python.

Neither holds credentials: authentication comes from the pipeline identity or a named client connection.
"""
from __future__ import annotations

from ..catalog.stacks import tool
from ..util import dump_yaml

STYLES = {"cli": "Shell deploy script", "python": "Python deploy script"}
ENGINE_CLI = {"snowflake": "SnowSQL", "bigquery": "bq", "redshift": "psql", "databricks": "Databricks CLI",
              "fabric": "sqlcmd", "synapse": "sqlcmd", "duckdb-local": "DuckDB"}


def style_label(style: str, profile: dict) -> str:
    cli = ENGINE_CLI.get(tool(profile, "compute_engine"), "platform CLI")
    return (f"Shell + SQL scripts run with {cli} (deploy.sh, verify.sql, rollback.sql)" if style == "cli"
            else "Python deploy script (deploy.py) + SQL (verify.sql, rollback.sql)")


def _steps(manifest: dict, profile: dict) -> list[dict]:
    """The ordered commands that put the tested commit into an environment, for this stack and code output."""
    files = set(manifest.get("files") or [])
    lake = tool(profile, "lakehouse_compute")
    orch = tool(profile, "orchestration")
    steps: list[dict] = []
    if "databricks.yml" in files:
        steps.append({"name": "deploy bundle", "run": 'databricks bundle deploy --target "$ENVIRONMENT"'})
    if "infra/main.tf" in files:
        steps.append({"name": "apply schema infrastructure", "run": 'terraform -chdir=infra apply -auto-approve -var-file="$ENVIRONMENT.tfvars"'})
    if "dbt_project.yml" in files:
        steps += [{"name": "dbt dependencies", "run": "dbt deps"},
                  {"name": "dbt build", "run": 'dbt build --target "$ENVIRONMENT"'}]
    submit = {"databricks": 'databricks bundle run --target "$ENVIRONMENT"', "aws-glue": "aws glue start-job-run --job-name",
              "emr-spark": "aws emr-serverless start-job-run --name", "dataproc": "gcloud dataproc jobs submit pyspark",
              "fabric-spark": "az synapse spark job submit --name"}.get(lake, "spark-submit")
    for f in ("pipelines/01_ingest/ingest_jdbc.py", "pipelines/02_curate/run_curate.py",
              "pipelines/02_curate/01_bronze_to_silver.sql", "pipelines/02_curate/02_silver_to_gold.sql"):
        if f in files and lake != "duckdb-local":
            how = "spark-sql -f" if f.endswith(".sql") and submit == "spark-submit" else submit
            steps.append({"name": f"register {f.split('/')[-1]}", "run": f"{how} {f}",
                          "note": f"scheduled by {orch}; the first run after release is the initial load and needs its own approval"})
    if "pipelines/03_publish/run_publish.sh" in files:
        steps.append({"name": "publish serving layer", "run": "bash pipelines/03_publish/run_publish.sh"})
    if "orchestration/run_local.sh" in files:
        steps.append({"name": "run the three pipelines locally", "run": 'bash orchestration/run_local.sh "$ENVIRONMENT"'})
    return steps or [{"name": "no deploy step generated", "run": "echo 'No reviewed deploy adapter for this stack' && exit 1"}]


def build(release_id: str, run_id: str, model: dict, profile: dict, manifest: dict, tested_commit: str,
          style: str = "cli") -> dict[str, str]:
    """Files for deploy/<release_id>/ on the release branch."""
    if style not in STYLES:
        raise ValueError(f"Unknown release style `{style}`")
    engine = tool(profile, "compute_engine")
    objects = manifest.get("objects") or []
    steps = _steps(manifest, profile)
    root = f"deploy/{release_id}"
    files: dict[str, str] = {}
    files[f"{root}/release-manifest.yaml"] = (
        f"# {release_id} for {model['name']} ({run_id}). Pins the commit that passed testing (G5).\n"
        f"tested_commit: {tested_commit}\n"
        + dump_yaml({"release": release_id, "run_id": run_id, "data_product": model["name"],
                     "stack_profile": profile.get("profile_id"), "compute_engine": engine, "code_output": manifest.get("code_output", "stack"),
                     "deploy_style": style, "objects": objects, "environments": ["test", "prod"],
                     "approvals_required": {"test": "G6a (Release Manager)", "prod": "G6b (Release Manager and Platform Owner)"},
                     "steps": [{"name": s["name"], "run": s["run"]} for s in steps]}))
    drop = {"snowflake": "DROP TABLE IF EXISTS", "bigquery": "DROP TABLE IF EXISTS", "redshift": "DROP TABLE IF EXISTS",
            "databricks": "DROP TABLE IF EXISTS", "fabric": "DROP TABLE IF EXISTS", "synapse": "DROP TABLE IF EXISTS"}.get(engine, "DROP TABLE IF EXISTS")
    files[f"{root}/verify.sql"] = (
        f"-- {release_id} post-deployment verification. Read-only. Every query must return rows_ok = 1.\n"
        + "\n".join(f"SELECT '{o}' AS object, CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END AS rows_ok, COUNT(*) AS row_count FROM {o};"
                    for o in objects) + "\n")
    files[f"{root}/rollback.sql"] = (
        f"-- {release_id} rollback. This release only adds new objects, so rollback removes them, newest first.\n"
        "-- Dropping objects is an irreversible action: run it only with its own recorded approval, through the\n"
        "-- release pipeline identity. Rehearsed in the sandbox; see 06-release/REL-001-rollback.md in the run.\n"
        + "\n".join(f"{drop} {o};" for o in reversed(objects)) + "\n")
    guard = ('case "$ENVIRONMENT" in test|prod) ;; *) echo "usage: deploy.sh <test|prod>"; exit 2 ;; esac\n'
             'if [ "$ENVIRONMENT" = "prod" ] && [ -z "${CHANGE_RECORD_ID:-}" ]; then\n'
             '  echo "REFUSED: production needs the approved change record in CHANGE_RECORD_ID"; exit 3\nfi\n')
    if style == "cli":
        body = "".join(f'echo "== {s["name"]}"\n{s["run"]}\n' for s in steps)
        files[f"{root}/deploy.sh"] = (
            "#!/usr/bin/env bash\n"
            f"# {release_id}: deploy {model['name']} to an environment. Run by the CI/CD pipeline identity only,\n"
            "# after the release gate for that environment is approved. Holds no credentials.\n"
            "set -euo pipefail\n"
            'ENVIRONMENT="${1:-}"\n' + guard +
            f'TESTED_COMMIT="{tested_commit}"\n'
            'cd "$(git rev-parse --show-toplevel)"\n'
            'if ! git merge-base --is-ancestor "$TESTED_COMMIT" HEAD; then\n'
            '  echo "REFUSED: this checkout does not contain the tested commit $TESTED_COMMIT"; exit 4\nfi\n'
            'if ! git diff --quiet "$TESTED_COMMIT" HEAD -- . ":(exclude)deploy"; then\n'
            '  echo "REFUSED: pipeline code differs from the tested commit $TESTED_COMMIT"; exit 5\nfi\n'
            'export ENVIRONMENT\n' + body +
            f'echo "== deployed {release_id} to $ENVIRONMENT; now run {root}/verify.sql and record the result"\n')
    else:
        items = ",\n".join(f"    ({s['name']!r}, {s['run']!r})" for s in steps)
        files[f"{root}/deploy.py"] = (
            f'"""{release_id}: deploy {model["name"]} to an environment.\n\n'
            "Run by the CI/CD pipeline identity only, after the release gate for that environment is approved.\n"
            'Holds no credentials. Usage: python ' + f"{root}/deploy.py <test|prod>\n" + '"""\n'
            "import os\nimport subprocess\nimport sys\n\n"
            f'TESTED_COMMIT = "{tested_commit}"\n'
            f"STEPS = [\n{items},\n]\n\n\n"
            "def git(*args: str) -> subprocess.CompletedProcess:\n"
            "    return subprocess.run([\"git\", *args], capture_output=True, text=True)\n\n\n"
            "def main(argv: list[str]) -> int:\n"
            "    if len(argv) != 1 or argv[0] not in (\"test\", \"prod\"):\n"
            "        print(\"usage: deploy.py <test|prod>\")\n        return 2\n"
            "    environment = argv[0]\n"
            "    if environment == \"prod\" and not os.environ.get(\"CHANGE_RECORD_ID\"):\n"
            "        print(\"REFUSED: production needs the approved change record in CHANGE_RECORD_ID\")\n        return 3\n"
            "    os.chdir(git(\"rev-parse\", \"--show-toplevel\").stdout.strip())\n"
            "    if git(\"merge-base\", \"--is-ancestor\", TESTED_COMMIT, \"HEAD\").returncode != 0:\n"
            "        print(f\"REFUSED: this checkout does not contain the tested commit {TESTED_COMMIT}\")\n        return 4\n"
            "    if git(\"diff\", \"--quiet\", TESTED_COMMIT, \"HEAD\", \"--\", \".\", \":(exclude)deploy\").returncode != 0:\n"
            "        print(f\"REFUSED: pipeline code differs from the tested commit {TESTED_COMMIT}\")\n        return 5\n"
            "    env = {**os.environ, \"ENVIRONMENT\": environment}\n"
            "    for name, command in STEPS:\n"
            "        print(f\"== {name}\")\n"
            "        subprocess.run(command, shell=True, check=True, env=env)\n"
            f"    print(f\"== deployed {release_id} to {{environment}}; now run {root}/verify.sql and record the result\")\n"
            "    return 0\n\n\n"
            "if __name__ == \"__main__\":\n    sys.exit(main(sys.argv[1:]))\n")
    entry = "deploy.sh" if style == "cli" else "deploy.py"
    files[f"{root}/README.md"] = (
        f"# {release_id} - release bundle\n\n"
        f"Data product `{model['name']}`, run `{run_id}`, tested commit `{tested_commit[:12]}`.\n\n"
        "| File | Purpose |\n|---|---|\n"
        f"| `release-manifest.yaml` | Pins the tested commit, the objects and the ordered steps |\n"
        f"| `{entry}` | Deploys to `test` or `prod`; refuses if the code differs from the tested commit, and refuses `prod` without a change record |\n"
        "| `verify.sql` | Read-only checks to run after each deployment |\n"
        "| `rollback.sql` | Removes the objects this release adds; needs its own approval |\n\n"
        "## How it is used\n\n"
        f"1. Open a pull request from this branch. Reviewers check the steps against the release plan.\n"
        f"2. After G6a, the pipeline runs `{root}/{entry} test`, then `verify.sql`.\n"
        f"3. After G6b, with `CHANGE_RECORD_ID` set, the pipeline runs `{root}/{entry} prod`, then `verify.sql`.\n\n"
        "No person and no agent runs these scripts against shared or production environments by hand.\n\n"
        "## Steps\n\n" + "\n".join(f"{i}. **{s['name']}**: `{s['run']}`" + (f" ({s['note']})" if s.get("note") else "")
                                  for i, s in enumerate(steps, start=1)) + "\n")
    return files
