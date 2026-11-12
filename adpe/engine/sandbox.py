"""Ephemeral SQLite sandbox that executes the approved logical model with synthetic data.

Everything reported as test evidence is computed here, from commands that can be re-run;
nothing is asserted without execution (guardrail: never fabricate evidence). This is the
dev-sandbox proof only; platform-level tests run in the bound engine through the adapter.
"""
from __future__ import annotations

import hashlib
import random
import sqlite3
from datetime import date, timedelta

from ..modeling.logical import parse_type, relationships

SEED = 20260101


def tname(e: dict) -> str:
    return {"dimension": "dim_", "fact": "fct_", "reference": "ref_", "bridge": "brg_"}.get(e["kind"], "") + e["name"]


def _order(model: dict) -> list[dict]:
    ents = {e["name"]: e for e in model["entities"]}
    deps = {n: {a["fk"]["entity"] for a in e["attributes"] if a.get("fk") and a["fk"]["entity"] != n}
            for n, e in ents.items()}
    out, done = [], set()
    while len(out) < len(ents):
        progressed = False
        for n in ents:
            if n not in done and deps[n] <= done:
                out.append(ents[n])
                done.add(n)
                progressed = True
        if not progressed:  # cycle: append the rest
            out += [ents[n] for n in ents if n not in done]
            break
    return out


def _columns(e: dict) -> list[tuple[str, str]]:
    cols = []
    if e.get("history") == "type2":
        cols += [(f"{e['name']}_sk", "INTEGER"), ("valid_from", "TEXT"), ("valid_to", "TEXT"), ("is_current", "INTEGER")]
    for a in e["attributes"]:
        base, _ = parse_type(a["type"])
        cols.append((a["name"], {"string": "TEXT", "integer": "INTEGER", "bigint": "INTEGER", "decimal": "REAL",
                                 "boolean": "INTEGER", "date": "TEXT", "timestamp": "TEXT"}[base]))
    return cols


class Sandbox:
    def __init__(self, model: dict, dq_rules: list[dict], seed: int = SEED, fact_rows: int = 240, dim_rows: int = 30):
        self.model = model
        self.dq = dq_rules or []
        self.rng = random.Random(seed)
        self.fact_rows, self.dim_rows = fact_rows, dim_rows
        self.db = sqlite3.connect(":memory:")
        self.commands: list[str] = []

    # ---------------- schema + synthetic data
    def build(self) -> None:
        for e in _order(self.model):
            cols = ", ".join(f"{c} {t}" for c, t in _columns(e))
            sql = f"CREATE TABLE {tname(e)} ({cols})"
            self.db.execute(sql)
            self.commands.append(sql)
            self._populate(e)
        self.db.commit()

    def _rule(self, e, a, typ):
        return next((r for r in self.dq if r.get("entity") == e["name"] and r.get("attribute") == a["name"]
                     and r.get("type") == typ), None)

    def _value(self, e, a, i, parents):
        base, args = parse_type(a["type"])
        if a.get("fk"):
            pool = parents.get(a["fk"]["entity"]) or [None]
            return self.rng.choice(pool)
        if a["pk"]:
            if base in ("integer", "bigint"):
                return i + 1
            prefix = "".join(w[0] for w in e["name"].split("_")).upper()
            return f"{prefix}{i + 1:06d}"
        av = self._rule(e, a, "accepted_values")
        if av:
            vals = av["params"].get("values") or ["X"]
            return vals[0] if self.rng.random() < 0.6 else self.rng.choice(vals)
        rg = self._rule(e, a, "range")
        if base == "boolean":
            return 1 if self.rng.random() < 0.08 else 0
        if base == "date":
            return (date(2026, 1, 1) + timedelta(days=self.rng.randint(0, 300))).isoformat()
        if base == "timestamp":
            return (date(2026, 1, 1) + timedelta(days=self.rng.randint(0, 300))).isoformat() + "T02:00:00"
        if base in ("integer", "bigint", "decimal"):
            lo, hi = (0, 1000)
            if rg:
                lo, hi = rg["params"].get("min", 0), rg["params"].get("max", 1000)
                lo, hi = max(lo, 0) if hi > 0 else lo, min(hi, max(lo, 0) + 1000) if hi > 1 else hi
            v = self.rng.uniform(lo, hi)
            if base == "decimal":
                scale = args[1] if len(args) > 1 else 2
                return round(v, min(scale, 4))
            return int(v)
        n = args[0] if args else 40
        word = a["name"].replace("_", " ").title().replace(" ", "")
        return f"{word[:max(1, n - 5)]}-{self.rng.randint(1, 999):03d}"[:n]

    def _populate(self, e):
        parents = self._parents()
        n = self.fact_rows if e["kind"] == "fact" else self.dim_rows
        cols = [c for c, _ in _columns(e)]
        rows, sk = [], 0
        for i in range(n):
            vals = {a["name"]: self._value(e, a, i, parents) for a in e["attributes"]}
            for a in e["attributes"]:
                if a.get("nullable") and not a["pk"] and not a.get("fk") and self.rng.random() < 0.02 \
                        and not self._rule(e, a, "not_null"):
                    vals[a["name"]] = None
            if e.get("history") == "type2":
                versions = 2 if self.rng.random() < 0.2 else 1
                for v in range(versions):
                    sk += 1
                    cur = v == versions - 1
                    row = {f"{e['name']}_sk": sk, "valid_from": f"2025-{6 + v:02d}-01T00:00:00",
                           "valid_to": None if cur else "2025-07-01T00:00:00", "is_current": 1 if cur else 0, **vals}
                    rows.append([row[c] for c in cols])
            else:
                rows.append([vals[c] for c in cols])
        self.db.executemany(f"INSERT INTO {tname(e)} VALUES ({', '.join('?' * len(cols))})", rows)

    def _parents(self) -> dict:
        out = {}
        for e in self.model["entities"]:
            pk = next((a["name"] for a in e["attributes"] if a["pk"]), None)
            try:
                where = " WHERE is_current = 1" if e.get("history") == "type2" else ""
                out[e["name"]] = [r[0] for r in self.db.execute(f"SELECT {pk} FROM {tname(e)}{where}")]
            except sqlite3.OperationalError:
                pass
        return out

    # ---------------- DQ rules
    def rule_sql(self, r: dict) -> tuple[str, str]:
        e = next(x for x in self.model["entities"] if x["name"] == r["entity"])
        t, c, p = tname(e), r.get("attribute"), r.get("params") or {}
        where = f" WHERE {p['where']}" if p.get("where") else ""
        total = f"SELECT COUNT(*) FROM {t}{where}"
        typ = r["type"]
        if typ == "not_null":
            return f"SELECT COUNT(*) FROM {t} WHERE {c} IS NULL", total
        if typ == "unique":
            return f"SELECT COUNT(*) - COUNT(DISTINCT {c}) FROM {t}{where}", total
        if typ == "accepted_values":
            vals = ", ".join("'" + str(v).replace("'", "''") + "'" for v in p.get("values", []))
            return f"SELECT COUNT(*) FROM {t} WHERE {c} IS NOT NULL AND {c} NOT IN ({vals})", total
        if typ == "range":
            return f"SELECT COUNT(*) FROM {t} WHERE {c} < {p.get('min', 0)} OR {c} > {p.get('max', 0)}", total
        if typ == "referential":
            pe = next(x for x in self.model["entities"] if x["name"] == p["to_entity"])
            return (f"SELECT COUNT(*) FROM {t} s LEFT JOIN (SELECT DISTINCT {p['to_attribute']} k FROM {tname(pe)}) r "
                    f"ON s.{c} = r.k WHERE s.{c} IS NOT NULL AND r.k IS NULL"), total
        if typ == "row_count_min":
            return f"SELECT CASE WHEN COUNT(*) >= {p.get('min', 1)} THEN 0 ELSE 1 END FROM {t}", "SELECT 1"
        raise ValueError(f"unsupported rule type {typ}")

    def run_rule(self, r: dict, db=None) -> dict:
        db = db or self.db
        try:
            fsql, tsql = self.rule_sql(r)
        except (ValueError, StopIteration, KeyError) as ex:
            return {"id": r["id"], "status": "not-executable", "reason": str(ex)}
        failures = db.execute(fsql).fetchone()[0] or 0
        total = db.execute(tsql).fetchone()[0] or 0
        ratio = 1.0 if total == 0 else max(0.0, 1 - failures / total)
        passed = ratio >= float(r.get("threshold", 1.0)) and not (r["type"] == "row_count_min" and failures)
        return {"id": r["id"], "status": "pass" if passed else "fail", "failures": failures, "rows": total,
                "pass_ratio": round(ratio, 6), "threshold": r.get("threshold", 1.0), "sql": fsql}

    def _clone(self) -> sqlite3.Connection:
        c = sqlite3.connect(":memory:")
        self.db.backup(c)
        return c

    def seed_defect(self, r: dict) -> dict:
        """Mutation check: inject one violation and confirm the rule catches it."""
        db = self._clone()
        e = next((x for x in self.model["entities"] if x["name"] == r["entity"]), None)
        if not e:
            return {"id": r["id"], "detected": False, "reason": "unknown entity"}
        t, c, p = tname(e), r.get("attribute"), r.get("params") or {}
        typ = r["type"]
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        k = max(1, int(n * (1 - float(r.get("threshold", 1.0)))) + 1)
        try:
            if typ == "not_null":
                db.execute(f"UPDATE {t} SET {c} = NULL WHERE rowid IN (SELECT rowid FROM {t} LIMIT {k})")
            elif typ == "unique":
                cond = f" AND {p['where']}" if p.get("where") else ""
                src_id, src_val = db.execute(f"SELECT rowid, {c} FROM {t} WHERE {c} IS NOT NULL{cond} LIMIT 1").fetchone()
                db.execute(f"UPDATE {t} SET {c} = ? WHERE rowid IN (SELECT rowid FROM {t} WHERE rowid <> {src_id} "
                           f"AND {c} <> ?{cond} LIMIT {k})", (src_val, src_val))
            elif typ == "accepted_values":
                db.execute(f"UPDATE {t} SET {c} = 'ZZ' WHERE rowid IN (SELECT rowid FROM {t} LIMIT {k})")
            elif typ == "range":
                db.execute(f"UPDATE {t} SET {c} = {p.get('max', 0)} + 1 WHERE rowid IN (SELECT rowid FROM {t} LIMIT {k})")
            elif typ == "referential":
                db.execute(f"UPDATE {t} SET {c} = 'ORPHAN-KEY' WHERE rowid IN (SELECT rowid FROM {t} LIMIT {k})")
            elif typ == "row_count_min":
                db.execute(f"DELETE FROM {t}")
            else:
                return {"id": r["id"], "detected": False, "reason": f"no mutation for {typ}"}
        except sqlite3.Error as ex:
            return {"id": r["id"], "detected": False, "reason": str(ex)}
        res = self.run_rule(r, db)
        return {"id": r["id"], "defect": f"{typ} violation x{k}", "detected": res["status"] == "fail"}

    # ---------------- metrics
    def metric_sql(self, m: dict) -> str:
        e = next(x for x in self.model["entities"] if x["name"] == m["entity"])

        def agg(spec):
            a, f = spec["attribute"], spec["agg"]
            return {"sum": f"SUM({a})", "avg": f"AVG({a})", "count": "COUNT(*)",
                    "count_distinct": f"COUNT(DISTINCT {a})", "sum_bool": f"SUM(CASE WHEN {a} = 1 THEN 1 ELSE 0 END)",
                    "min": f"MIN({a})", "max": f"MAX({a})"}[f]
        num = agg(m["measure"])
        expr = f"CAST({num} AS REAL) / NULLIF({agg(m['denominator'])}, 0)" if m.get("denominator") else num
        return f"SELECT {expr} FROM {tname(e)}"

    def metric_python(self, m: dict) -> float | None:
        """Independent computation path: fetch rows and compute in Python."""
        e = next(x for x in self.model["entities"] if x["name"] == m["entity"])
        cur = self.db.execute(f"SELECT * FROM {tname(e)}")
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]

        def agg(spec):
            vals = [r[spec["attribute"]] for r in rows] if spec["agg"] != "count" else rows
            nn = [v for v in vals if v is not None]
            f = spec["agg"]
            if f == "sum":
                return sum(nn) if nn else None
            if f == "avg":
                return sum(nn) / len(nn) if nn else None
            if f == "count":
                return len(rows)
            if f == "count_distinct":
                return len(set(nn))
            if f == "sum_bool":
                return sum(1 for v in nn if v == 1)
            return (min if f == "min" else max)(nn) if nn else None
        num = agg(m["measure"])
        if m.get("denominator"):
            den = agg(m["denominator"])
            return None if not den or num is None else num / den
        return num

    def reconcile(self, m: dict) -> dict:
        sql = self.metric_sql(m)
        a = self.db.execute(sql).fetchone()[0]
        b = self.metric_python(m)
        ok = a is not None and b is not None and abs(a - b) <= 1e-6 * max(1.0, abs(b))
        return {"metric": m["name"], "sql_value": a, "independent_value": b, "status": "pass" if ok else "fail",
                "sql": sql}

    # ---------------- idempotency, masking, checksum, rollback
    def checksum(self, table: str, db=None) -> str:
        db = db or self.db
        rows = db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        return hashlib.sha256(repr(rows).encode()).hexdigest()

    def idempotency(self, e: dict) -> dict:
        t = tname(e)
        pk = next(a["name"] for a in e["attributes"] if a["pk"])
        db = self._clone()
        cols = [c for c, _ in _columns(e)]
        db.execute(f"CREATE TABLE stage_{t} AS SELECT * FROM {t}")
        db.execute(f"CREATE TABLE tgt_{t} AS SELECT * FROM {t} WHERE 0")
        key = f"{e['name']}_sk" if e.get("history") == "type2" else pk
        db.execute(f"CREATE UNIQUE INDEX ux_tgt_{t} ON tgt_{t} ({key})")
        load = f"INSERT OR REPLACE INTO tgt_{t} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM stage_{t}"
        db.execute(load)
        c1, n1 = self.checksum(f"tgt_{t}", db), db.execute(f"SELECT COUNT(*) FROM tgt_{t}").fetchone()[0]
        db.execute(load)
        c2, n2 = self.checksum(f"tgt_{t}", db), db.execute(f"SELECT COUNT(*) FROM tgt_{t}").fetchone()[0]
        return {"table": t, "rows_run1": n1, "rows_run2": n2, "checksum_equal": c1 == c2,
                "status": "pass" if (c1 == c2 and n1 == n2) else "fail", "load_sql": load}

    def masking(self, e: dict, restricted: list[str]) -> dict:
        t = tname(e)
        sel = ", ".join(f"'***' AS {a['name']}" if a["name"] in restricted else a["name"] for a in e["attributes"])
        self.db.execute(f"CREATE VIEW IF NOT EXISTS v_consumer_{t} AS SELECT {sel} FROM {t}")
        leaks = 0
        for c in restricted:
            leaks += self.db.execute(f"SELECT COUNT(*) FROM v_consumer_{t} WHERE {c} <> '***'").fetchone()[0]
        return {"view": f"v_consumer_{t}", "restricted_columns": restricted, "unmasked_values": leaks,
                "status": "pass" if leaks == 0 else "fail"}

    def rollback_rehearsal(self, e: dict) -> dict:
        t = tname(e)
        db = self._clone()
        before = self.checksum(t, db)
        db.execute(f"CREATE TABLE {t}__rollback AS SELECT * FROM {t}")
        db.execute(f"ALTER TABLE {t} ADD COLUMN adpe_release_marker TEXT")
        db.execute(f"UPDATE {t} SET adpe_release_marker = 'REL-001'")
        after_deploy = self.checksum(t, db)
        db.execute(f"DROP TABLE {t}")
        db.execute(f"ALTER TABLE {t}__rollback RENAME TO {t}")
        after_rb = self.checksum(t, db)
        return {"table": t, "checksum_before": before[:16], "checksum_after_deploy": after_deploy[:16],
                "checksum_after_rollback": after_rb[:16], "restored": before == after_rb,
                "status": "pass" if before == after_rb and after_deploy != before else "fail"}

    def row_counts(self) -> dict:
        return {tname(e): self.db.execute(f"SELECT COUNT(*) FROM {tname(e)}").fetchone()[0] for e in self.model["entities"]}

    def attribute_population(self, e: dict, attrs: list[str]) -> dict:
        t = tname(e)
        res = {}
        for a in attrs:
            res[a] = self.db.execute(f"SELECT COUNT({a}) FROM {t}").fetchone()[0]
        return res

    def relationships(self):
        return relationships(self.model)
