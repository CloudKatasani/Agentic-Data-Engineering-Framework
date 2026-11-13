"""Local lakehouse runner: executes the three pipelines for real on this machine.

    source database ──(1 ingest)──▶ bronze ──(2 curate)──▶ silver ──▶ gold ──(3 publish)──▶ analytics
    SQLite / Oracle / Db2           Delta or Iceberg on local disk           DuckDB serving database

- Pipeline 1 extracts each source table incrementally on its LAST_UPDATED_TS watermark and writes
  bronze as an open table format. A batch is idempotent: re-running it replaces that batch only.
- Pipeline 2 types, trims and de-duplicates bronze into silver, then builds gold by executing the
  SQL that the Build agent generated (codegen.entity_select), so generated code is really run.
- Pipeline 3 publishes gold into a DuckDB analytics database with masked consumer views, then
  runs the quality rules and reconciles every governed metric between gold and the serving layer.

Cloud stacks get generated Spark / DMS / ADF / Datastream code instead; this runner is the local,
executable equivalent used for rehearsals and for the Local lakehouse stack.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa

from .. import sources
from ..engine.codegen import CodeGen, _src_table
from ..engine.sandbox import Sandbox, tname
from ..modeling import physical as ph
from ..modeling.logical import parse_type


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _arrow(con, sql: str) -> pa.Table:
    """Run a query and return an Arrow table (DuckDB 1.x and 2.x)."""
    r = con.sql(sql)  # relation API: no extra copy of the rows
    for m in ("to_arrow_table", "arrow", "fetch_arrow_table"):
        if hasattr(r, m):
            out = getattr(r, m)()
            return out.read_all() if hasattr(out, "read_all") else out
    raise RuntimeError("this DuckDB version cannot return Arrow tables")


def _one(con, sql: str):
    return con.execute(sql).fetchall()[0][0]


def _columns(con, relation: str) -> list[str]:
    cur = con.execute(f"SELECT * FROM {relation} LIMIT 0")
    cols = [d[0] for d in cur.description]
    cur.fetchall()
    return cols


def silver_name(table: str) -> str:
    return table.lower().replace(".", "__")


class TableStore:
    """Writes and reads Delta or Iceberg tables on local disk."""

    def __init__(self, root: Path, fmt: str):
        self.root, self.fmt = Path(root), fmt
        self.root.mkdir(parents=True, exist_ok=True)
        self._catalog = None

    @property
    def catalog(self):
        if self._catalog is None:
            from pyiceberg.catalog.sql import SqlCatalog
            self._catalog = SqlCatalog("adef", uri=f"sqlite:///{self.root / 'iceberg_catalog.db'}",
                                       warehouse=f"file://{self.root / 'warehouse'}")
        return self._catalog

    def path(self, layer: str, name: str) -> Path:
        return self.root / layer / name

    def write(self, layer: str, name: str, table: pa.Table, mode: str = "overwrite", batch_col: str | None = None,
              batch_id: str | None = None) -> dict:
        if self.fmt == "delta":
            from deltalake import DeltaTable, write_deltalake
            p = self.path(layer, name)
            exists = (p / "_delta_log").exists()
            if exists and batch_col and mode == "append":
                write_deltalake(str(p), table, mode="overwrite", predicate=f"{batch_col} = '{batch_id}'",
                                schema_mode="merge")
            else:
                write_deltalake(str(p), table, mode="overwrite" if not exists or mode == "overwrite" else "append",
                                schema_mode="overwrite" if mode == "overwrite" else "merge")
            dt = DeltaTable(str(p))
            return {"format": "delta", "location": str(p), "version": dt.version()}
        from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchTableError
        try:
            self.catalog.create_namespace(layer)
        except NamespaceAlreadyExistsError:
            pass
        ident = f"{layer}.{name}"
        try:
            tbl = self.catalog.load_table(ident)
            if mode == "overwrite":
                self.catalog.drop_table(ident)
                tbl = self.catalog.create_table(ident, schema=table.schema)
                tbl.append(table)
            elif batch_col:
                from pyiceberg.expressions import EqualTo
                tbl.overwrite(table, overwrite_filter=EqualTo(batch_col, batch_id))
            else:
                tbl.append(table)
        except NoSuchTableError:
            tbl = self.catalog.create_table(ident, schema=table.schema)
            tbl.append(table)
        tbl = self.catalog.load_table(ident)
        snap = tbl.current_snapshot()
        return {"format": "iceberg", "location": tbl.metadata_location, "version": snap.snapshot_id if snap else None}

    def read(self, layer: str, name: str) -> pa.Table:
        if self.fmt == "delta":
            from deltalake import DeltaTable
            return DeltaTable(str(self.path(layer, name))).to_pyarrow_table()
        return self.catalog.load_table(f"{layer}.{name}").scan().to_arrow()

    def exists(self, layer: str, name: str) -> bool:
        if self.fmt == "delta":
            return (self.path(layer, name) / "_delta_log").exists()
        try:
            self.catalog.load_table(f"{layer}.{name}")
            return True
        except Exception:  # noqa: BLE001
            return False


class LocalLakehouse:
    def __init__(self, root: Path, env: str, model: dict, mapping: dict, source_cfg: dict, table_format: str = "delta",
                 profile: dict | None = None, log=None):
        self.root = Path(root)
        self.env = env
        self.model, self.mapping = model, mapping
        self.dq = mapping.get("dq_rules", [])
        self.source_cfg = source_cfg
        self.fmt = table_format if table_format in ("delta", "iceberg") else "delta"
        self.profile = profile
        self.store = TableStore(self.root / "lake" / env, self.fmt)
        self.analytics_path = self.root / "analytics" / f"{env}.duckdb"
        self.state_path = self.root / "lake" / env / "_state.json"
        self.log = log or (lambda t: None)
        self.report: dict = {"env": env, "format": self.fmt, "lake_root": str(self.store.root),
                             "analytics_db": str(self.analytics_path), "source": {k: v for k, v in source_cfg.items()
                                                                                    if k != "password"},
                             "pipelines": {}, "layers": {"source": [], "bronze": [], "silver": [], "gold": [], "serving": []}}

    # ------------------------------------------------------------------ helpers
    def needed_source_tables(self) -> list[str]:
        import re
        out = set()
        for m in self.mapping["mappings"]:
            t = _src_table(m.get("source", ""))
            if t:
                out.add(t)
            out |= set(re.findall(r"\{\{stg:([\w.]+)\}\}", m.get("expression") or ""))
        return sorted(out)

    def source_meta(self) -> dict[str, dict]:
        return {s["table"]: s for s in self.mapping.get("sources", [])}

    def _state(self) -> dict:
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else {"watermarks": {}}

    def _save_state(self, st: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(st, indent=2))

    # ------------------------------------------------------------------ pipeline 1: ingest
    def ingest(self, batch_id: str | None = None) -> dict:
        t0 = time.time()
        batch_id = batch_id or datetime.now(timezone.utc).strftime("B%Y%m%dT%H%M%S")
        st = self._state()
        con = sources.connect(self.source_cfg)
        available = {t.lower() for t in con.tables()}
        results, missing = [], []
        try:
            for t in self.needed_source_tables():
                if t.lower() not in available:
                    missing.append(t)
                    continue
                schema, name = sources.split(t)
                wm = st["watermarks"].get(t)
                where = f" WHERE {sources.WATERMARK.upper()} > {con.placeholder(1)}" if wm else ""
                cols, rows = con.query(f"SELECT * FROM {schema}.{name}{where}", (con.bind_ts(wm),) if wm else ())
                total = con.query(f"SELECT COUNT(*) FROM {schema}.{name}")[1][0][0]
                data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
                data = {c: [str(v) if isinstance(v, (datetime,)) or hasattr(v, "isoformat") else v for v in vals]
                        for c, vals in data.items()}
                n = len(rows)
                tbl = pa.table({**data, "_ingested_at": [_now()] * n, "_batch_id": [batch_id] * n,
                                "_source_system": [self.source_cfg.get("type", "?")] * n})
                # all-empty columns arrive untyped; open table formats need a concrete type
                tbl = tbl.cast(pa.schema([pa.field(f.name, pa.string()) if pa.types.is_null(f.type) else f
                                          for f in tbl.schema]))
                info = {"table": t, "rows_extracted": n, "rows_in_source": total, "incremental": bool(wm),
                        "watermark_from": wm}
                if n:
                    w = self.store.write("bronze", silver_name(t), tbl, mode="append", batch_col="_batch_id",
                                         batch_id=batch_id)
                    info.update(w)
                    if sources.WATERMARK in cols:
                        st["watermarks"][t] = max(str(v) for v in data[sources.WATERMARK] if v is not None)
                elif self.store.exists("bronze", silver_name(t)):
                    info.update({"format": self.fmt, "location": str(self.store.path("bronze", silver_name(t))),
                                 "version": "unchanged"})
                results.append(info)
                self.log(f"Pipeline 1: {t} -> bronze.{silver_name(t)} ({n} rows{', incremental' if wm else ''})")
        finally:
            con.close()
        self._save_state(st)
        self.report["layers"]["source"] = [{"table": r["table"], "rows": r["rows_in_source"]} for r in results]
        self.report["layers"]["bronze"] = results
        self.report["pipelines"]["ingest"] = {"batch_id": batch_id, "seconds": round(time.time() - t0, 2),
                                              "tables": len(results), "missing_sources": missing}
        return self.report["pipelines"]["ingest"]

    # ------------------------------------------------------------------ pipeline 2: curate
    def _cast(self, col: str, ltype: str) -> str:
        base, _ = parse_type(ltype)
        phys = ph.phys_type(ltype, "duckdb")
        if base == "string":
            return f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '') AS {col}"
        if base == "boolean":
            return f"CAST({col} AS BOOLEAN) AS {col}"
        return f"TRY_CAST({col} AS {phys}) AS {col}"

    def curate(self) -> dict:
        t0 = time.time()
        db = duckdb.connect()
        meta = self.source_meta()
        silver = []
        for b in self.report["layers"]["bronze"] or [{"table": t} for t in self.needed_source_tables()]:
            t = b["table"]
            if not self.store.exists("bronze", silver_name(t)):
                continue
            db.register("bronze_src", self.store.read("bronze", silver_name(t)))
            have = set(_columns(db, "bronze_src"))
            cols = [c["name"] for c in meta.get(t, {}).get("columns", [])] or [c for c in have if not c.startswith("_")]
            types = {c["name"]: c["type"] for c in meta.get(t, {}).get("columns", [])}
            pks = [c["name"] for c in meta.get(t, {}).get("columns", []) if c.get("pk")] or cols[:1]
            order = f"{sources.WATERMARK} DESC, _ingested_at DESC" if sources.WATERMARK in have else "_ingested_at DESC"
            sel = ", ".join(self._cast(c, types.get(c, "string")) for c in cols if c in have)
            sql = (f"SELECT {sel} FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY {', '.join(pks)} ORDER BY {order}) AS _rn "
                   f"FROM bronze_src) WHERE _rn = 1")
            out = _arrow(db, sql)
            raw = _one(db, "SELECT COUNT(*) FROM bronze_src")
            w = self.store.write("silver", silver_name(t), out, mode="overwrite")
            silver.append({"table": silver_name(t), "rows": out.num_rows, "duplicates_removed": raw - out.num_rows, **w})
            db.unregister("bronze_src")
            self.log(f"Pipeline 2: bronze.{silver_name(t)} -> silver ({out.num_rows} rows)")
        # gold: execute the generated SQL against silver
        for s in silver:
            db.register(f"silver_{s['table']}", self.store.read("silver", s["table"]))
        gen = CodeGen(self.model, self.mapping["mappings"], self.dq, self.profile or {}, "local",
                      entity_filters=self.mapping.get("entity_filters") or {})
        gen.ref = lambda table: f"silver_{silver_name(table)}"  # type: ignore[method-assign]
        gold, gold_sql, errors = [], {}, []
        for e in self.model["entities"]:
            body = gen.entity_select(e)
            cast = ", ".join(f"CAST({a['name']} AS {ph.phys_type(a['type'], 'duckdb')}) AS {a['name']}" for a in e["attributes"])
            sql = f"SELECT {cast} FROM (\n{body}) g"
            if e.get("history") == "type2":
                sql = (f"SELECT ROW_NUMBER() OVER (ORDER BY {next(a['name'] for a in e['attributes'] if a['pk'])}) AS {e['name']}_sk, "
                       f"CAST('{_now()[:19]}' AS TIMESTAMP) AS valid_from, CAST(NULL AS TIMESTAMP) AS valid_to, "
                       f"TRUE AS is_current, * FROM ({sql}) h")
            gold_sql[tname(e)] = sql
            try:
                out = _arrow(db, sql)
            except duckdb.Error as ex:
                errors.append({"table": tname(e), "error": str(ex).splitlines()[0]})
                self.log(f"Pipeline 2: gold {tname(e)} FAILED: {str(ex).splitlines()[0]}")
                continue
            w = self.store.write("gold", tname(e), out, mode="overwrite")
            gold.append({"table": tname(e), "rows": out.num_rows, **w})
            db.register(tname(e), out)
            self.log(f"Pipeline 2: silver -> gold.{tname(e)} ({out.num_rows} rows)")
        sb = Sandbox(self.model, self.dq)
        sb.db = db
        dq = [sb.run_rule(r) for r in self.dq] if not errors else []
        self.report["layers"]["silver"] = silver
        self.report["layers"]["gold"] = gold
        self.report["gold_sql"] = gold_sql
        self.report["dq"] = [{k: v for k, v in r.items() if k != "sql"} for r in dq]
        self.report["pipelines"]["curate"] = {"seconds": round(time.time() - t0, 2), "silver_tables": len(silver),
                                              "gold_tables": len(gold), "errors": errors}
        self._gold_db = db
        return self.report["pipelines"]["curate"]

    # ------------------------------------------------------------------ pipeline 3: publish
    def publish(self) -> dict:
        t0 = time.time()
        self.analytics_path.parent.mkdir(parents=True, exist_ok=True)
        if self.analytics_path.exists():
            self.analytics_path.unlink()
        an = duckdb.connect(str(self.analytics_path))
        an.execute("CREATE SCHEMA IF NOT EXISTS serving")
        serving = []
        for g in self.report["layers"]["gold"]:
            an.register("gold_src", self.store.read("gold", g["table"]))
            an.execute(f"CREATE OR REPLACE TABLE serving.{g['table']} AS SELECT * FROM gold_src")
            an.unregister("gold_src")
            e = next(x for x in self.model["entities"] if tname(x) == g["table"])
            restricted = {a["name"] for a in e["attributes"] if a["classification"] == "restricted"}
            cols = _columns(an, f"serving.{g['table']}")
            sel = ", ".join(f"'***' AS {c}" if c in restricted else c for c in cols)
            an.execute(f"CREATE OR REPLACE VIEW serving.v_{g['table']} AS SELECT {sel} FROM serving.{g['table']}")
            n = _one(an, f"SELECT COUNT(*) FROM serving.{g['table']}")
            serving.append({"table": f"serving.{g['table']}", "consumer_view": f"serving.v_{g['table']}", "rows": n,
                            "masked_columns": sorted(restricted), "location": str(self.analytics_path)})
            self.log(f"Pipeline 3: gold.{g['table']} -> serving.{g['table']} ({n} rows, {len(restricted)} masked)")
        # metric reconciliation: gold (lake) vs serving (analytics engine)
        metrics = []
        sb_gold, sb_serv = Sandbox(self.model, self.dq), Sandbox(self.model, self.dq)
        sb_gold.db = self._gold_db
        an.execute("SET schema = 'serving'")
        sb_serv.db = an
        for m in self.model.get("metrics", []):
            try:
                a = _one(sb_gold.db, sb_gold.metric_sql(m))
                b = _one(an, sb_serv.metric_sql(m))
                ok = a is not None and b is not None and abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(a)))
                metrics.append({"metric": m["name"], "label": m["label"], "gold": float(a) if a is not None else None,
                                "serving": float(b) if b is not None else None, "status": "pass" if ok else "fail"})
            except duckdb.Error as ex:
                metrics.append({"metric": m["name"], "label": m.get("label"), "status": "fail", "error": str(ex).splitlines()[0]})
        an.close()
        self.report["layers"]["serving"] = serving
        self.report["metrics"] = metrics
        self.report["pipelines"]["publish"] = {"seconds": round(time.time() - t0, 2), "tables": len(serving),
                                               "analytics_db": str(self.analytics_path)}
        return self.report["pipelines"]["publish"]

    def run_all(self, batch_id: str | None = None) -> dict:
        self.report["started"] = _now()
        self.ingest(batch_id)
        self.curate()
        if not self.report["pipelines"]["curate"]["errors"]:
            self.publish()
        self.report["finished"] = _now()
        failed_dq = [d for d in self.report.get("dq", []) if d.get("status") == "fail"]
        failed_m = [m for m in self.report.get("metrics", []) if m.get("status") != "pass"]
        self.report["status"] = ("failed" if self.report["pipelines"]["curate"]["errors"] or failed_m
                                 else "passed-with-dq-findings" if failed_dq else "passed")
        return self.report


def query_serving(analytics_db: Path, table: str, limit: int = 25) -> dict:
    """Read the masked consumer view of a serving table (what an analyst would see)."""
    import re
    if not re.match(r"^[a-z0-9_]+$", table):
        raise ValueError("bad table name")
    con = duckdb.connect(str(analytics_db), read_only=True)
    try:
        cur = con.execute(f"SELECT * FROM serving.v_{table} LIMIT {int(limit)}")
        cols = [d[0] for d in cur.description]
        rows = [[None if v is None else str(v) for v in r] for r in cur.fetchall()]
        total = _one(con, f"SELECT COUNT(*) FROM serving.{table}")
    finally:
        con.close()
    return {"table": table, "columns": cols, "rows": rows, "total_rows": total}
