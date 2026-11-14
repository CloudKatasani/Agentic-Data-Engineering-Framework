"""Production-grade synthetic data kit: everything needed to run the application end to end, as one zip.

Unlike the small demo packs, a kit is generated at a chosen scale and behaves like a real delivery:

- full-load extracts for every source table, with referential integrity;
- two days of incremental batches (updates, new rows, duplicate deliveries) on the change watermark;
- data quality defects seeded at a realistic rate, each one listed so tests can prove they are caught;
- control totals to reconcile against, DDL and bulk-load scripts for Oracle and Db2;
- the inputs each agent needs: Jira export, source catalog, glossary, and context documents
  (Confluence pages, repository standards, ServiceNow records);
- a manifest with row counts and hashes.

Everything is synthetic and reproducible from the seed. Nothing is derived from real data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .catalog.domains import load_pack
from .connectors import context_sources as cs
from .demo_data import SEED, SIZES, START, VALUES, SourceData, jira_csv, jira_issues, jira_json
from .engine.scenarios import SCENARIOS
from .modeling import physical as ph
from .modeling.logical import parse_type
from .sources import WATERMARK, ddl, source_tables, split

SCALES = {"small": 1, "medium": 40, "large": 300}
SCALE_NOTES = {"small": "Demo size: loads in seconds", "medium": "Realistic test volume", "large": "Volume and performance testing"}
DEFECT_RATE = 0.002
APPROVERS = [("product_owner", "Priya Raman"), ("data_architect", "Arun Mehta"), ("data_steward", "Dana Okafor"),
             ("tech_lead", "Tom Lindqvist"), ("release_manager", "Rhea Castellanos"), ("platform_owner", "Paul Nakamura"),
             ("security_compliance", "Sam Whitfield")]


def scaled_sizes(scale: str) -> dict:
    """Base tables grow with the scale; small reference tables (catalogs, stores) do not."""
    f = SCALES[scale]
    out = {}
    for t, sz in SIZES.items():
        out[t] = sz * f if isinstance(sz, int) and sz > 10 else sz
    return out


def estimate(pack: str, scale: str) -> dict[str, int]:
    """Row counts per source table without generating anything."""
    sizes = scaled_sizes(scale)
    tables = [s["table"] for s in source_tables(pack)]
    out: dict[str, int] = {}
    for _ in range(4):
        for t in tables:
            sz = sizes.get(t, 20)
            if isinstance(sz, int):
                out[t] = sz
            elif sz[0] in out:
                out[t] = int(out[sz[0]] * (sz[2] if sz[1] == "days" else sz[1]))
    return out


def options() -> dict:
    return {"scales": {k: {"note": SCALE_NOTES[k], "rows": {p: sum(estimate(p, k).values()) for p in SCENARIOS}} for k in SCALES},
            "domains": {p: SCENARIOS[p]["title"] for p in SCENARIOS}}


class _Zip:
    """Writes files into a zip while recording rows, size and hash for the manifest."""

    def __init__(self, target, root: str):
        self.z = zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED)
        self.root, self.files = root, []

    def text(self, path: str, content: str, rows: int | None = None) -> None:
        data = content.encode("utf-8")
        self.z.writestr(f"{self.root}/{path}", data)
        self.files.append({"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                           **({"rows": rows} if rows is not None else {})})

    def table(self, path: str, header: list[str], rows) -> int:
        h, n, size = hashlib.sha256(), 0, 0
        with self.z.open(f"{self.root}/{path}", "w", force_zip64=True) as raw:
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(header)
            for r in rows:
                w.writerow(r)
                n += 1
                if n % 5000 == 0:
                    data = buf.getvalue().encode("utf-8")
                    raw.write(data); h.update(data); size += len(data)
                    buf.seek(0); buf.truncate()
            data = buf.getvalue().encode("utf-8")
            raw.write(data); h.update(data); size += len(data)
        self.files.append({"path": path, "bytes": size, "sha256": h.hexdigest(), "rows": n})
        return n


def _cells(row: dict, header: list[str], kinds: dict[str, str]) -> list:
    out = []
    for c in header:
        v = row.get(c, "")
        if kinds[c] == "timestamp" and v:
            v = str(v).replace("T", " ")[:19]
        elif kinds[c] == "boolean" and v != "":
            v = 1 if (v if isinstance(v, bool) else str(v).lower() in ("1", "true", "t", "y")) else 0
        out.append(v)
    return out


def _generate(pack: str, scale: str, seed: int) -> tuple[SourceData, dict[str, list[dict]]]:
    sd = SourceData(pack, seed=seed, sources=source_tables(pack), sizes=scaled_sizes(scale))
    rows = sd.generate()
    base = datetime(2026, 9, 1, 1, 0, 0)
    for rs in rows.values():
        for i, r in enumerate(rs):
            r[WATERMARK] = (base + timedelta(seconds=(i * 7) % 3600)).isoformat(sep=" ")
    return sd, rows


def _seed_defects(sd: SourceData, rows: dict[str, list[dict]]) -> list[dict]:
    """Plant realistic source defects in place and return the list of what was planted."""
    rng, out = sd.rng, []
    for t, rs in rows.items():
        cols = sd.tables[t]["columns"]
        pks = [c["name"] for c in cols if c.get("pk")]
        refs = [c["name"] for c in cols if sd.parent_of(t, c["name"]) and not c.get("pk")]
        nums = [c["name"] for c in cols if parse_type(c["type"])[0] == "decimal"]
        codes = [c["name"] for c in cols if c["name"] in VALUES or f"{t}.{c['name']}" in VALUES]
        optional = [c["name"] for c in cols if not c.get("pk") and c["name"] not in refs and c["name"] != WATERMARK]
        kinds = [k for k, ok in (("orphan_reference", refs), ("negative_amount", nums), ("untrimmed_code", codes),
                                 ("missing_value", optional)) if ok]
        if not kinds or len(rs) < 20:
            continue
        n = max(1, min(150, int(len(rs) * DEFECT_RATE)))
        for j, i in enumerate(sorted(rng.sample(range(len(rs)), n))):
            r, kind = rs[i], kinds[j % len(kinds)]
            key = "|".join(str(r[p]) for p in pks)
            if kind == "orphan_reference":
                col = refs[j % len(refs)]
                r[col] = re.sub(r"\d+$", "", str(r[col])) + "999999"
                why, rule = f"{col} points to a parent row that does not exist", "referential integrity"
            elif kind == "negative_amount":
                col = nums[j % len(nums)]
                r[col] = -abs(float(r[col] or 1)) or -1.0
                why, rule = f"{col} is negative", "range check"
            elif kind == "untrimmed_code":
                col = codes[j % len(codes)]
                r[col] = f" {str(r[col]).lower()} "
                why, rule = f"{col} has stray spaces and the wrong case", "accepted values"
            else:
                col = optional[j % len(optional)]
                r[col] = ""
                why, rule = f"{col} is empty", "completeness"
            out.append({"defect_id": f"SD-{len(out) + 1:05d}", "table": t, "key": key, "column": col, "defect": kind,
                        "description": why, "rule_that_should_catch_it": rule})
    return out


def _increment(sd: SourceData, rows: dict[str, list[dict]], sizes: dict, day: int) -> dict[str, tuple[list[dict], dict]]:
    """One day of changes per table: updated rows, new rows, and a few rows delivered twice."""
    rng, out = sd.rng, {}
    stamp = datetime(2026, 9, 1, 1, 0, 0) + timedelta(days=day - 1)
    for t, rs in rows.items():
        cols = sd.tables[t]["columns"]
        pks = [c["name"] for c in cols if c.get("pk")]
        sz = sizes.get(t, 20)
        batch: list[dict] = []
        mix = {"updated": 0, "new": 0, "delivered_twice": 0}
        if isinstance(sz, tuple) and sz[1] == "days":
            ppk = next(c["name"] for c in sd.tables[sz[0]]["columns"] if c.get("pk"))
            date_col = next(c for c in pks if c != ppk)
            latest: dict = {}
            for r in rs:
                latest[r[ppk]] = r
            new_date = (START + timedelta(days=sz[2] + day - 2)).isoformat()
            for r in latest.values():
                batch.append({**r, date_col: new_date})
            mix["new"] = len(batch)
        elif len(pks) == 1 and len(rs) >= 20:
            mutable = [c["name"] for c in cols if (c["name"] in VALUES or f"{t}.{c['name']}" in VALUES)]
            for r in rng.sample(rs, max(1, len(rs) // 100)):
                if mutable:
                    col = mutable[rng.randrange(len(mutable))]
                    r[col] = sd._pick(t, col)
                batch.append(dict(r)); mix["updated"] += 1
            start = len(rs) + (day - 2) * max(1, len(rs) // 200)
            for i in range(max(1, len(rs) // 200)):
                batch.append({**rng.choice(rs), pks[0]: sd.key(t, pks[0], start + i)}); mix["new"] += 1
            for r in rng.sample(rs, min(3, len(rs))):
                batch.append(dict(r)); mix["delivered_twice"] += 1
        for i, r in enumerate(batch):
            if mix["delivered_twice"] and i >= len(batch) - mix["delivered_twice"]:
                continue        # an unchanged row sent again keeps its old watermark
            r[WATERMARK] = (stamp + timedelta(seconds=i % 3600)).isoformat(sep=" ")
        if batch:
            out[t] = (batch, mix)
    return out


def _control_totals(sd: SourceData, rows: dict[str, list[dict]]) -> list[list]:
    out = []
    for t, rs in rows.items():
        out.append([t, "*", "row_count", len(rs)])
        for c in sd.tables[t]["columns"]:
            n, base = c["name"], parse_type(c["type"])[0]
            vals = [r.get(n) for r in rs]
            filled = [v for v in vals if v not in ("", None)]
            out.append([t, n, "null_count", len(vals) - len(filled)])
            if c.get("pk") or sd.parent_of(t, n):
                out.append([t, n, "distinct_count", len(set(filled))])
            if base in ("decimal", "integer", "bigint") and filled:
                nums = [float(v) for v in filled]
                out += [[t, n, "sum", round(sum(nums), 4)], [t, n, "min", min(nums)], [t, n, "max", max(nums)]]
    return out


def _loader_scripts(pack: str) -> dict[str, str]:
    files = {"oracle/01-ddl.sql": ddl(pack, "oracle"), "db2/01-ddl.sql": ddl(pack, "db2")}
    db2 = ["-- Db2 bulk load. Run from the kit root after 01-ddl.sql:  db2 -tvf 02-source-database/db2/02-load.sql", ""]
    steps = ["# Oracle bulk load with SQL*Loader. Run from the kit root after 01-ddl.sql.",
             "# Set ORACLE_CONNECT to user/password@host:port/service in your shell; do not write it into this file.", ""]
    for s in source_tables(pack):
        schema, name = split(s["table"])
        f = s["table"].replace(".", "__")
        fields = []
        for c in s["columns"]:
            base = parse_type(c["type"])[0]
            col = c["name"].upper()
            fields.append(f'  {col} TIMESTAMP "YYYY-MM-DD HH24:MI:SS"' if base == "timestamp"
                          else f'  {col} DATE "YYYY-MM-DD"' if base == "date" else f"  {col}")
        files[f"oracle/ctl/{f}.ctl"] = (
            f"OPTIONS (SKIP=1, ERRORS=1000000, DIRECT=FALSE)\nLOAD DATA\nCHARACTERSET UTF8\n"
            f"INFILE '01-source-data/full-load/{f}.csv'\nBADFILE '{f}.bad'\nAPPEND INTO TABLE {schema}.{name}\n"
            "FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' TRAILING NULLCOLS\n(\n" + ",\n".join(fields) + "\n)\n")
        steps.append(f'sqlldr userid="$ORACLE_CONNECT" control=02-source-database/oracle/ctl/{f}.ctl log={f}.log')
        db2.append(f"IMPORT FROM '01-source-data/full-load/{f}.csv' OF DEL MODIFIED BY COLDEL, SKIPCOUNT 1 "
                   f"TIMESTAMPFORMAT=\"YYYY-MM-DD HH:MM:SS\" COMMITCOUNT 5000 INSERT INTO {schema}.{name};")
    files["oracle/02-load.sh"] = "\n".join(steps) + "\n"
    files["db2/02-load.sql"] = "\n".join(db2) + "\n"
    return files


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70]


def build(pack: str, scale: str, target, seed: int = SEED) -> dict:
    """Write the kit for one domain as a zip to `target` (a path or file object). Returns the manifest."""
    if pack not in SCENARIOS:
        raise ValueError(f"Unknown domain `{pack}`")
    if scale not in SCALES:
        raise ValueError(f"Scale must be one of {', '.join(SCALES)}")
    sc = SCENARIOS[pack]
    root = f"datacrew-synthetic-kit-{pack}-{scale}"
    z = _Zip(target, root)
    sizes = scaled_sizes(scale)
    sd, rows = _generate(pack, scale, seed)
    defects = _seed_defects(sd, rows)
    tables = {s["table"]: s for s in source_tables(pack)}
    header = {t: [c["name"] for c in tables[t]["columns"]] for t in rows}
    kinds = {t: {c["name"]: parse_type(c["type"])[0] for c in tables[t]["columns"]} for t in rows}
    counts = {}
    for t, rs in rows.items():
        counts[t] = z.table(f"01-source-data/full-load/{t.replace('.', '__')}.csv", header[t],
                            (_cells(r, header[t], kinds[t]) for r in rs))
    z.table("01-source-data/data-quality/seeded-defects.csv",
            ["defect_id", "table", "key", "column", "defect", "description", "rule_that_should_catch_it"],
            ([d[k] for k in ("defect_id", "table", "key", "column", "defect", "description", "rule_that_should_catch_it")] for d in defects))
    z.table("06-expected-results/control-totals.csv", ["table", "column", "measure", "value"], _control_totals(sd, rows))
    inc_summary = []
    for day in (2, 3):
        for t, (batch, mix) in _increment(sd, rows, sizes, day).items():
            n = z.table(f"01-source-data/incremental/day-{day:02d}/{t.replace('.', '__')}.csv", header[t],
                        (_cells(r, header[t], kinds[t]) for r in batch))
            inc_summary.append([f"day-{day:02d}", t, n, mix["updated"], mix["new"], mix["delivered_twice"]])
    z.table("06-expected-results/incremental-batches.csv", ["batch", "table", "rows", "updated", "new", "delivered_twice"], inc_summary)
    for path, content in _loader_scripts(pack).items():
        z.text(f"02-source-database/{path}", content)

    issues = jira_issues(pack)
    z.text("03-requirements/business-request.md", f"# {sc['title']}\n\n{sc['request']}\n")
    z.text("03-requirements/jira-export.csv", jira_csv(issues), rows=len(issues))
    z.text("03-requirements/jira-export.json", jira_json(issues, f"https://example-{pack}.atlassian.net"), rows=len(issues))
    for src in ("confluence", "github", "servicenow"):
        for item in cs._demo_items(src, pack):
            if src == "confluence":
                z.text(f"04-context/confluence/{_slug(item['title'])}.md",
                       f"<!-- for stages: {', '.join(item['stages'])} -->\n{item['content']}\n")
            elif src == "github":
                z.text(f"04-context/repository/{item['ref']}", item["content"] + "\n")
            else:
                z.text(f"04-context/servicenow/{_slug(item['title'])}.json",
                       json.dumps({"reference": item["ref"], "for_stages": item["stages"], "record": item["content"]}, indent=2))
    cat = [[s["system"], *s["table"].split("."), c["name"], c["type"], ph.phys_type(c["type"], "oracle"), "Y" if c.get("pk") else "",
            c["classification"], c.get("description") or c["name"].replace("_", " "), s.get("owner", ""), s.get("refresh", "")]
           for s in tables.values() for c in s["columns"]]
    z.table("05-metadata/source-catalog.csv", ["system", "schema", "table_name", "column_name", "data_type", "oracle_type",
                                               "primary_key", "classification", "description", "owner", "refresh"], cat)
    pack_def = load_pack(pack)
    z.table("05-metadata/business-glossary.csv", ["term", "definition"],
            [[g.get("term", ""), g.get("definition", "")] for g in pack_def.get("glossary_seed", [])]
            + [[m["label"], m["definition"]] for m in sc["metrics"]])
    z.table("05-metadata/compliance-controls.csv", ["control_id", "control"],
            [[c.get("id", ""), c.get("text", "")] for c in pack_def.get("controls", [])])
    z.table("07-enterprise-setup/approvers.csv", ["role", "named_person"], APPROVERS)
    z.text("07-enterprise-setup/policy.json", json.dumps({"separation_of_duties": True, "approved_providers": ["anthropic"]}, indent=2) + "\n")

    by_kind: dict[str, int] = {}
    for d in defects:
        by_kind[d["defect"]] = by_kind.get(d["defect"], 0) + 1
    total = sum(counts.values())
    z.text("README.md", "\n".join([
        f"# Synthetic data kit: {sc['title']}", "",
        f"Domain `{pack}`, scale `{scale}` ({total:,} source rows), seed {seed}, generator {__version__}. "
        "Every value is synthetic; nothing is derived from real people, accounts or systems.", "",
        "## What is inside", "",
        "| Folder | Contents | Use it for |", "|---|---|---|",
        "| `01-source-data/full-load/` | One CSV per source table, with referential integrity | The first load into your source database |",
        "| `01-source-data/incremental/` | Two daily batches: updated rows, new rows, and rows delivered twice | Proving incremental extraction and safe re-runs |",
        f"| `01-source-data/data-quality/` | The {len(defects):,} defects planted in the full load, one per row | Proving the quality rules catch them |",
        "| `02-source-database/` | DDL and bulk-load scripts for Oracle (SQL*Loader) and Db2 (IMPORT) | Building the source database |",
        "| `03-requirements/` | Business request, Jira export (CSV and JSON) | New run → Requirements source |",
        "| `04-context/` | Confluence pages, repository standards, ServiceNow records | A run's Context tab → Upload a file |",
        "| `05-metadata/` | Source catalog, business glossary, compliance controls | New run → Source metadata; Context tab |",
        "| `06-expected-results/` | Control totals per table and column; the make-up of each incremental batch | Reconciliation in the Test stage |",
        "| `07-enterprise-setup/` | Seven named approvers and an enterprise policy | Approvers step; Guardrails → Enterprise policy |",
        "", "## Source tables", "", "| Table | Rows |", "|---|---|"] + [f"| `{t}` | {n:,} |" for t, n in counts.items()] + [
        "", "## Planted data quality defects", ""] + [f"- {k.replace('_', ' ')}: {v:,}" for k, v in sorted(by_kind.items())] + [
        "", "## How to run the application on this kit", "",
        "1. Create the source database: run `02-source-database/<oracle|db2>/01-ddl.sql`, then the load script next to it.",
        "2. In the console, add the connection under Integrations → Source databases (the password goes in the vault).",
        "3. Start a new run: upload `03-requirements/jira-export.csv`, then `05-metadata/source-catalog.csv` as source metadata,"
        " and enter the approvers from `07-enterprise-setup/approvers.csv`.",
        "4. On the run's Context tab, upload the files from `04-context/` to the stages named at the top of each file.",
        "5. After the first run, load `incremental/day-02` and `day-03` into the source and re-run the rehearsal on the Lakehouse tab.",
        "6. In the Test stage, compare results with `06-expected-results/control-totals.csv` and check every defect in"
        " `seeded-defects.csv` is reported.", "",
        "The Jira export contains one issue with instruction-like text (asking the automation to grant access to everyone)."
        " It is there on purpose: the intake stage must report it and never act on it.", ""]))
    manifest = {"kit": root, "domain": pack, "scale": scale, "seed": seed, "generator_version": __version__,
                "source_rows": total, "tables": counts, "seeded_defects": len(defects), "defects_by_kind": by_kind,
                "files": sorted(z.files, key=lambda f: f["path"])}
    z.z.writestr(f"{root}/manifest.json", json.dumps(manifest, indent=2))
    z.z.close()
    return manifest


def write(pack: str, scale: str, out_dir: Path, seed: int = SEED) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"datacrew-synthetic-kit-{pack}-{scale}.zip"
    build(pack, scale, path, seed)
    return path
