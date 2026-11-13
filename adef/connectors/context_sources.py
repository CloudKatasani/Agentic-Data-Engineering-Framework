"""Optional, read-only context sources an approver can pull from at any stage (action class A0).

Each source answers two calls: `search(query)` lists candidate items, `fetch(ref)` returns one
item as plain text. Everything returned is untrusted data: it is scanned, redacted and passed to
agents inside <untrusted_data> tags, never as instructions.

- Confluence: Cloud (`/wiki/rest/api`, email + API token) or Data Center (`/rest/api`, bearer PAT).
- GitHub: REST contents and tree APIs for one configured repository (works with GitHub Enterprise).
- ServiceNow: Table API for change requests, incidents and knowledge articles.
- Jira: the existing Jira connector, so issues (defects, test plans, change tickets) can be attached anywhere.

Every source has a demo mode with content generated from the golden scenario of the run's
Domain Pack, so a demo needs no external system. Tokens are resolved from the vault at call
time and never returned.
"""
from __future__ import annotations

import html
import re

import httpx

from ..engine.scenarios import SCENARIOS, for_domain
from ..secrets_store import SecretNotFound, SecretStore
from .jira import DEMO_PROJECTS, JiraClient, JiraError

MAX_ITEM_CHARS = 20000


class ContextSourceError(Exception):
    pass


SOURCES: dict[str, dict] = {
    "confluence": {"label": "Confluence", "holds": "Project charters, business glossary, standards, runbooks, meeting decisions",
                   "fields": ["mode", "base_url", "deployment", "email", "token_ref", "space"],
                   "query_hint": "Words from the page title or body, for example: glossary"},
    "jira": {"label": "Jira", "holds": "Epics, stories, defects, test plans, change tickets",
             "fields": [], "query_hint": "JQL, for example: project = TEL AND issuetype = Bug"},
    "github": {"label": "GitHub", "holds": "Coding standards, existing pipeline code, CI configuration, CODEOWNERS",
               "fields": ["mode", "base_url", "repo", "branch", "token_ref"],
               "query_hint": "Part of a file path, for example: docs/ or .sql"},
    "servicenow": {"label": "ServiceNow", "holds": "Change calendar and freeze windows, incidents, CAB policy, knowledge articles",
                   "fields": ["mode", "base_url", "user", "token_ref"],
                   "query_hint": "Words from the record, for example: freeze"},
}
DEFAULT_SETTINGS: dict[str, dict] = {
    "confluence": {"mode": "demo", "base_url": "", "deployment": "cloud", "email": "", "token_ref": "", "space": ""},
    "github": {"mode": "demo", "base_url": "https://api.github.com", "repo": "", "branch": "main", "token_ref": ""},
    "servicenow": {"mode": "demo", "base_url": "", "user": "", "token_ref": ""},
}


def html_to_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", body or "")
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li|tr|table|ul|ol)>", "\n", body)
    body = re.sub(r"(?i)<li[^>]*>", "- ", body)
    body = re.sub(r"(?i)</t[dh]>", " | ", body)
    body = html.unescape(re.sub(r"<[^>]+>", "", body))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", body)).strip()


class _Http:
    """Shared plumbing: https only, vault-resolved token, uniform errors."""
    name = "source"

    def __init__(self, cfg: dict, secrets: SecretStore | None = None):
        self.cfg = cfg or {}
        self.mode = self.cfg.get("mode", "demo")
        self.base = (self.cfg.get("base_url") or "").rstrip("/")
        self.secrets = secrets or SecretStore()

    def _token(self) -> str:
        try:
            token = self.secrets.resolve(self.cfg.get("token_ref"))
        except SecretNotFound as e:
            raise ContextSourceError(f"{self.name} token reference `{self.cfg.get('token_ref')}` not found in the vault") from e
        if not token:
            raise ContextSourceError(f"No {self.name} token configured")
        return token

    def _get(self, path: str, *, headers: dict | None = None, auth=None, params: dict | None = None, raw: bool = False):
        if not self.base.startswith("https://") and not self.base.startswith("http://localhost"):
            raise ContextSourceError(f"{self.name} base URL must be https://")
        try:
            r = httpx.get(self.base + path, headers={"Accept": "application/json", **(headers or {})}, auth=auth,
                          params=params, timeout=30, follow_redirects=False)
        except httpx.HTTPError as e:
            raise ContextSourceError(f"Cannot reach {self.name}: {e}") from e
        if r.status_code in (401, 403):
            raise ContextSourceError(f"{self.name} rejected the credentials ({r.status_code})")
        if r.status_code == 404:
            raise ContextSourceError(f"{self.name}: not found")
        if r.status_code >= 400:
            raise ContextSourceError(f"{self.name} error {r.status_code}: {r.text[:200]}")
        return r.text if raw else r.json()


# ----------------------------------------------------------------------------- Confluence
class ConfluenceSource(_Http):
    name = "Confluence"

    def _auth(self) -> dict:
        token = self._token()
        if self.cfg.get("deployment", "cloud") == "cloud":
            if not self.cfg.get("email"):
                raise ContextSourceError("Confluence Cloud needs the account email for API-token auth")
            return {"auth": (self.cfg["email"], token)}
        return {"headers": {"Authorization": f"Bearer {token}"}}

    @property
    def api(self) -> str:
        return "/wiki/rest/api" if self.cfg.get("deployment", "cloud") == "cloud" else "/rest/api"

    def test(self) -> dict:
        if self.mode == "demo":
            return {"ok": True, "mode": "demo", "detail": "Demo space with pages generated for each Domain Pack"}
        d = self._get(f"{self.api}/space", params={"limit": 1}, **self._auth())
        return {"ok": True, "mode": "live", "detail": f"Connected; {d.get('size', 0)} space(s) visible on the first page"}

    def search(self, query: str, domain: str, limit: int = 15) -> list[dict]:
        if self.mode == "demo":
            return _demo_search("confluence", query, domain, limit)
        words = re.sub(r'["\\]', " ", query or "").strip()
        cql = "type = page" + (f' AND text ~ "{words}"' if words else "")
        if self.cfg.get("space"):
            cql += f' AND space = "{self.cfg["space"]}"'
        d = self._get(f"{self.api}/content/search", params={"cql": cql + " ORDER BY lastmodified DESC", "limit": limit,
                                                             "expand": "space,version"}, **self._auth())
        return [{"ref": p["id"], "title": p.get("title", ""), "kind": "page",
                 "excerpt": f"{(p.get('space') or {}).get('key', '')} · updated {(p.get('version') or {}).get('when', '')[:10]}",
                 "url": self._page_url(p)} for p in d.get("results", [])]

    def _page_url(self, p: dict) -> str:
        link = (p.get("_links") or {}).get("webui", "")
        return f"{self.base}{'/wiki' if self.cfg.get('deployment', 'cloud') == 'cloud' else ''}{link}" if link else ""

    def fetch(self, ref: str, domain: str) -> dict:
        if self.mode == "demo":
            return _demo_fetch("confluence", ref, domain)
        if not re.fullmatch(r"\d+", ref or ""):
            raise ContextSourceError("Confluence reference must be a numeric page id")
        p = self._get(f"{self.api}/content/{ref}", params={"expand": "body.storage,version,space"}, **self._auth())
        return {"title": p.get("title", ref), "url": self._page_url(p),
                "content": html_to_text(((p.get("body") or {}).get("storage") or {}).get("value", "")),
                "version": str((p.get("version") or {}).get("number", ""))}


# ----------------------------------------------------------------------------- GitHub
class GitHubSource(_Http):
    name = "GitHub"

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}", "X-GitHub-Api-Version": "2022-11-28"}

    def _repo(self) -> str:
        repo = self.cfg.get("repo") or ""
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ContextSourceError("Set the repository as owner/name")
        return repo

    def test(self) -> dict:
        if self.mode == "demo":
            return {"ok": True, "mode": "demo", "detail": "Demo repository with engineering standards and CI configuration"}
        d = self._get(f"/repos/{self._repo()}", headers=self._h())
        return {"ok": True, "mode": "live", "detail": f"{d.get('full_name')} · default branch {d.get('default_branch')}"}

    def search(self, query: str, domain: str, limit: int = 15) -> list[dict]:
        if self.mode == "demo":
            return _demo_search("github", query, domain, limit)
        branch = self.cfg.get("branch") or "main"
        d = self._get(f"/repos/{self._repo()}/git/trees/{branch}", params={"recursive": "1"}, headers=self._h())
        q = (query or "").lower().strip()
        files = [t for t in d.get("tree", []) if t.get("type") == "blob" and (not q or q in t["path"].lower())
                 and re.search(r"\.(md|sql|ya?ml|json|py|toml|cfg|txt|tf)$|CODEOWNERS$", t["path"])]
        return [{"ref": t["path"], "title": t["path"], "kind": "file", "excerpt": f"{t.get('size', 0):,} bytes · {branch}",
                 "url": ""} for t in files[:limit]]

    def fetch(self, ref: str, domain: str) -> dict:
        if self.mode == "demo":
            return _demo_fetch("github", ref, domain)
        if ".." in ref or ref.startswith("/"):
            raise ContextSourceError("Invalid file path")
        text = self._get(f"/repos/{self._repo()}/contents/{ref}", params={"ref": self.cfg.get("branch") or "main"},
                         headers={**self._h(), "Accept": "application/vnd.github.raw+json"}, raw=True)
        return {"title": f"{self._repo()}:{ref}", "url": "", "content": text, "version": self.cfg.get("branch") or "main"}


# ----------------------------------------------------------------------------- ServiceNow
SNOW_TABLES = {"change_request": ("Change", ["number", "short_description", "description", "state", "start_date", "end_date", "risk"]),
               "incident": ("Incident", ["number", "short_description", "description", "state", "priority", "close_notes"]),
               "kb_knowledge": ("Knowledge", ["number", "short_description", "text"])}


class ServiceNowSource(_Http):
    name = "ServiceNow"

    def _a(self) -> dict:
        token = self._token()
        return {"auth": (self.cfg["user"], token)} if self.cfg.get("user") else {"headers": {"Authorization": f"Bearer {token}"}}

    def test(self) -> dict:
        if self.mode == "demo":
            return {"ok": True, "mode": "demo", "detail": "Demo instance with a change calendar, incidents and CAB policy"}
        self._get("/api/now/table/incident", params={"sysparm_limit": 1, "sysparm_fields": "number"}, **self._a())
        return {"ok": True, "mode": "live", "detail": "Connected to the Table API"}

    def search(self, query: str, domain: str, limit: int = 15) -> list[dict]:
        if self.mode == "demo":
            return _demo_search("servicenow", query, domain, limit)
        words = re.sub(r"[\^=]", " ", query or "").strip()
        out = []
        for table, (label, _fields) in SNOW_TABLES.items():
            d = self._get(f"/api/now/table/{table}", **self._a(), params={
                "sysparm_limit": max(1, limit // 3), "sysparm_fields": "sys_id,number,short_description,state",
                "sysparm_query": (f"short_descriptionLIKE{words}^" if words else "") + "ORDERBYDESCsys_updated_on"})
            out += [{"ref": f"{table}:{r['sys_id']}", "title": f"{r.get('number', '')} {r.get('short_description', '')}".strip(),
                     "kind": label.lower(), "excerpt": f"{label} · state {r.get('state', '')}", "url": ""} for r in d.get("result", [])]
        return out[:limit]

    def fetch(self, ref: str, domain: str) -> dict:
        if self.mode == "demo":
            return _demo_fetch("servicenow", ref, domain)
        table, _, sys_id = ref.partition(":")
        if table not in SNOW_TABLES or not re.fullmatch(r"[0-9a-f]{32}", sys_id):
            raise ContextSourceError("ServiceNow reference must be <table>:<sys_id>")
        label, fields = SNOW_TABLES[table]
        r = self._get(f"/api/now/table/{table}/{sys_id}", params={"sysparm_fields": ",".join(fields)}, **self._a()).get("result", {})
        body = "\n".join(f"{f}: {html_to_text(str(r.get(f, '')))}" for f in fields if r.get(f))
        return {"title": f"{label} {r.get('number', sys_id)}: {r.get('short_description', '')}", "url": "", "content": body, "version": ""}


# ----------------------------------------------------------------------------- Jira (reuses the Jira connector)
class JiraSource:
    name = "Jira"

    def __init__(self, cfg: dict, secrets: SecretStore | None = None):
        self.client = JiraClient(cfg, secrets)
        self.mode = self.client.mode

    def test(self) -> dict:
        try:
            return self.client.test()
        except JiraError as e:
            raise ContextSourceError(str(e)) from e

    def _jql(self, query: str, domain: str) -> str:
        q = (query or "").strip()
        if not q and self.mode == "demo":
            return f"project = {next((k for k, v in DEMO_PROJECTS.items() if v == domain), 'UTIL')}"
        if re.search(r"[=~]|\bin\b", q, re.I):
            return q
        return f'text ~ "{re.sub(chr(34), " ", q)}" ORDER BY updated DESC' if q else "ORDER BY updated DESC"

    def search(self, query: str, domain: str, limit: int = 15) -> list[dict]:
        try:
            issues = self.client.search(self._jql(query, domain), limit)
        except JiraError as e:
            raise ContextSourceError(str(e)) from e
        return [{"ref": i["key"], "title": f"{i['key']} {i['summary']}", "kind": i.get("type", "issue").lower(),
                 "excerpt": f"{i.get('type', '')} · {i.get('status', '')}", "url": i.get("url", "")} for i in issues]

    def fetch(self, ref: str, domain: str) -> dict:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", ref or ""):
            raise ContextSourceError("Jira reference must be an issue key")
        try:
            issues = self.client.search(f"key in ({ref.upper()})", 1)
        except JiraError as e:
            raise ContextSourceError(str(e)) from e
        if not issues:
            raise ContextSourceError(f"Jira issue {ref} not found")
        i = issues[0]
        body = (f"{i['key']} ({i.get('type', '')}, {i.get('status', '')}, priority {i.get('priority', '')})\n{i['summary']}\n\n"
                f"{i.get('description', '')}\n" + ("\nAcceptance criteria:\n" + "\n".join(f"- {a}" for a in i["acceptance_criteria"])
                                                  if i.get("acceptance_criteria") else ""))
        return {"title": f"{i['key']} {i['summary']}", "url": i.get("url", ""), "content": body, "version": ""}


def source_for(source_id: str, settings: dict, secrets: SecretStore | None = None):
    integ = settings.get("integrations") or {}
    if source_id == "jira":
        return JiraSource(settings.get("jira") or {"mode": "demo"}, secrets)
    cls = {"confluence": ConfluenceSource, "github": GitHubSource, "servicenow": ServiceNowSource}.get(source_id)
    if not cls:
        raise ContextSourceError(f"Unknown context source `{source_id}`")
    return cls({**DEFAULT_SETTINGS[source_id], **(integ.get(source_id) or {})}, secrets)


# ----------------------------------------------------------------------------- demo content
def _demo_items(source_id: str, domain: str) -> list[dict]:
    sc = for_domain(domain if domain in SCENARIOS else "utilities")
    title = sc["title"]
    metrics = "\n".join(f"- {m['label']} ({m['name']}): {m['definition']} Grain: {m.get('grain', 'n/a')}. Unit: {m.get('unit', 'n/a')}."
                        for m in sc["metrics"])
    rules = "\n".join(f"- {i}: {t} Example: {e}" for i, t, e in sc["business_rules"])
    nfrs = "\n".join(f"- {i}: {t} (measure: {m})" for i, t, m in sc["nfrs"])
    consumers = "\n".join(f"- {n}: {q}" for n, q in sc["consumers"])
    sources = "\n\n".join(
        f"{s['table']} (system {s['system']}, owner {s['owner']}, refresh {s['refresh']}): {s.get('description', '')}\n"
        + "\n".join(f"  - {c['name']} {c['type']} [{c['classification']}]{' PK' if c.get('pk') else ''} {c.get('description', '')}".rstrip()
                    for c in s["columns"]) for s in sc["sources"])
    owners = sorted({s["owner"] for s in sc["sources"]})
    if source_id == "confluence":
        return [
            {"ref": "1001", "kind": "page", "stages": ["intake", "requirements"], "title": f"Project charter: {title}",
             "content": f"Project charter: {title}\n\nBusiness goal\n{sc['request']}\n\nStakeholders and their questions\n{consumers}\n\n"
                        "Delivery approach\nDeliver a first thin slice in one release, batch only. Streaming and write-back to source systems "
                        f"are out of scope for this phase.\n\nSource system owners\n" + "\n".join(f"- {o}" for o in owners)},
            {"ref": "1002", "kind": "page", "stages": ["requirements", "consumption", "design"], "title": "Business glossary and KPI definitions",
             "content": f"Business glossary and KPI definitions\n\nAgreed metric definitions (owner: Data Steward)\n{metrics}\n\n"
                        "A metric definition may only change through the glossary change process; reports must use these definitions."},
            {"ref": "1003", "kind": "page", "stages": ["requirements", "mapping", "test"], "title": "Business rules agreed with the business",
             "content": f"Business rules agreed with the business\n\n{rules}\n\nService levels\n{nfrs}"},
            {"ref": "1004", "kind": "page", "stages": ["mapping", "design"], "title": "Source system data dictionary",
             "content": f"Source system data dictionary\n\n{sources}\n\nAll source tables carry LAST_UPDATED_TS for incremental extraction."},
            {"ref": "1005", "kind": "page", "stages": ["design", "build"], "title": "Data platform architecture standards",
             "content": "Data platform architecture standards\n\n- Layers: bronze (raw, append-only), silver (cleaned, conformed), gold (business entities and metrics).\n"
                        "- Open table format in the lake; no proprietary formats in bronze or silver.\n- Naming: snake_case; dimensions dim_<entity>, "
                        "facts fct_<process>, staging stg_<source>_<table>.\n- Every table has load_ts and batch_id audit columns.\n"
                        "- Restricted columns are masked in every consumer-facing view.\n- Slowly changing dimensions use type 2 only when "
                        "history is a stated requirement.\n- New compute above the approved monthly estimate needs Platform Owner approval."},
            {"ref": "1006", "kind": "page", "stages": ["test"], "title": "Test strategy and data quality thresholds",
             "content": "Test strategy and data quality thresholds\n\n- Every business rule has at least one positive and one negative test.\n"
                        "- Primary keys: 100% unique and not null.\n- Referential integrity: 100% for conformed dimensions.\n"
                        "- Reconciliation to the trusted report: within 0.5% for monetary measures, exact for counts.\n"
                        "- Tests run on synthetic data only; production data is never copied to test.\n- A release needs zero open severity 1 or 2 defects."},
            {"ref": "1007", "kind": "page", "stages": ["release"], "title": "Release and change management policy",
             "content": "Release and change management policy\n\n- Production changes need an approved change request and a rehearsed rollback.\n"
                        "- Standard release windows: Tuesday and Thursday 18:00-22:00 local time.\n- No production changes during month-end close "
                        "(last 2 and first 3 business days).\n- Deploy to the shared test environment first; verify before production.\n"
                        "- The Release Manager and the Platform Owner both approve production."},
            {"ref": "1008", "kind": "page", "stages": ["operations"], "title": "On-call runbook and service levels",
             "content": f"On-call runbook and service levels\n\nService levels\n{nfrs}\n\n- Severity 1: data product unavailable or wrong for consumers; "
                        "respond in 30 minutes.\n- Severity 2: late data beyond the freshness target; respond in 2 hours.\n"
                        "- Never re-run a load without checking for duplicates first.\n- Pre-approved actions: retry a failed batch once; "
                        "pause a schedule. Everything else needs the Platform Owner."},
            {"ref": "1009", "kind": "page", "stages": ["consumption"], "title": "BI and data access standards",
             "content": f"BI and data access standards\n\nConsumers\n{consumers}\n\n- Analysts get masked views by default; unmasked access needs "
                        "Data Steward approval per person.\n- Metrics are published once in the semantic layer; dashboards must not redefine them.\n"
                        "- Every published data product has an owner, a contract and a catalog entry."},
        ]
    if source_id == "github":
        return [
            {"ref": "docs/sql-style-guide.md", "kind": "file", "stages": ["build", "design"], "title": "docs/sql-style-guide.md",
             "content": "# SQL style guide\n\n- Lowercase keywords are not allowed; use UPPERCASE keywords and snake_case identifiers.\n"
                        "- One column per line; trailing commas.\n- CTEs over nested subqueries; name each CTE for what it holds.\n"
                        "- No SELECT * outside staging models.\n- Every model is idempotent: MERGE on the business key, never blind INSERT.\n"
                        "- Incremental models filter on the watermark column and tolerate late-arriving rows."},
            {"ref": "CONTRIBUTING.md", "kind": "file", "stages": ["build"], "title": "CONTRIBUTING.md",
             "content": "# Contributing\n\n- Work on a feature branch named <run-id>/<work-package>; never commit to main.\n"
                        "- Every pull request needs lint, unit tests and an idempotency check to pass.\n- One reviewer from CODEOWNERS approves.\n"
                        "- No credentials in code or config; reference secrets by name."},
            {"ref": ".github/workflows/ci.yml", "kind": "file", "stages": ["build", "test", "release"], "title": ".github/workflows/ci.yml",
             "content": "name: ci\non: [pull_request]\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                        "      - run: make lint\n      - run: make unit\n      - run: make idempotency\n      - run: make dq-smoke\n"},
            {"ref": "CODEOWNERS", "kind": "file", "stages": ["build", "release"], "title": "CODEOWNERS",
             "content": "pipelines/   @data-platform/tech-leads\nmodels/gold/ @data-platform/data-architects\ndeploy/      @data-platform/release-managers\n"},
            {"ref": "docs/pipeline-template.md", "kind": "file", "stages": ["build", "design"], "title": "docs/pipeline-template.md",
             "content": "# Pipeline template\n\nThree pipelines per data product: 01_ingest (source to bronze, incremental on the watermark), "
                        "02_curate (bronze to silver to gold), 03_publish (gold to the analytics layer with masked views).\n"
                        "Each pipeline writes a run record with batch_id, row counts and duration."},
        ]
    if source_id == "servicenow":
        return [
            {"ref": "change_request:demo-chg-0042", "kind": "change", "stages": ["release"], "title": "CHG0042 Month-end change freeze",
             "content": "number: CHG0042\nshort_description: Month-end change freeze\ndescription: No production deployments to finance or "
                        "customer data products from the last 2 business days of the month to the 3rd business day of the next month.\nstate: Scheduled\nrisk: High"},
            {"ref": "kb_knowledge:demo-kb-0007", "kind": "knowledge", "stages": ["release", "operations"], "title": "KB0007 CAB policy for data platform changes",
             "content": "number: KB0007\nshort_description: CAB policy for data platform changes\ntext: Normal changes need CAB approval 2 business days "
                        "ahead. Standard changes (pre-approved, rehearsed rollback, no schema break) may deploy in a release window with "
                        "Release Manager approval. Emergency changes need the Platform Owner."},
            {"ref": "incident:demo-inc-0113", "kind": "incident", "stages": ["operations", "test"], "title": "INC0113 Duplicate rows after a manual re-run",
             "content": "number: INC0113\nshort_description: Duplicate rows after a manual re-run\ndescription: A failed nightly load was re-run by hand "
                        "without clearing the partial batch; the fact table held duplicates for 6 hours.\nstate: Closed\npriority: 2\n"
                        "close_notes: Loads made idempotent (MERGE on business key). Runbook updated: check batch status before any re-run."},
            {"ref": "incident:demo-inc-0127", "kind": "incident", "stages": ["operations"], "title": "INC0127 Source extract arrived 5 hours late",
             "content": "number: INC0127\nshort_description: Source extract arrived 5 hours late\ndescription: The upstream extract missed its window; "
                        "the freshness target was breached and consumers were not told.\nstate: Closed\npriority: 3\n"
                        "close_notes: Freshness monitor and consumer notification added."},
        ]
    return []


def _demo_search(source_id: str, query: str, domain: str, limit: int) -> list[dict]:
    q = (query or "").lower().strip()
    items = [i for i in _demo_items(source_id, domain) if not q or q in i["title"].lower() or q in i["content"].lower()]
    return [{"ref": i["ref"], "title": i["title"], "kind": i["kind"], "url": "",
             "excerpt": "demo · " + re.sub(r"\s+", " ", i["content"])[:110]} for i in items[:limit]]


def _demo_fetch(source_id: str, ref: str, domain: str) -> dict:
    item = next((i for i in _demo_items(source_id, domain) if i["ref"] == ref), None)
    if not item:
        raise ContextSourceError(f"{SOURCES[source_id]['label']} demo item `{ref}` not found")
    return {"title": item["title"], "url": "", "content": item["content"], "version": "demo"}


def demo_suggestions(source_id: str, domain: str, stage: str) -> list[dict]:
    """Demo items that fit a stage, so the console can offer a one-click example."""
    return [{"ref": i["ref"], "title": i["title"]} for i in _demo_items(source_id, domain) if stage in i["stages"]]
