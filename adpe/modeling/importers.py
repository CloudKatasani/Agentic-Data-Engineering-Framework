"""Import source metadata or models exported from modelling tools and data catalogs.

Accepted: CSV data dictionary / catalog export, ADPE JSON model, generic JSON
{"tables": [...]}, DBML, and CREATE TABLE DDL. Output is a neutral metadata structure:
{"tables": [{"name", "schema", "description", "columns": [{"name","type","nullable","pk",
"description","classification"}]}]}. Imported text is untrusted data: it is scanned for
embedded instructions and secrets, and never executed.
"""
from __future__ import annotations

import csv
import io
import json
import re

from ..guardrails.scanners import scan_injection, scan_secrets
from .logical import parse_type

CSV_ALIASES = {
    "table": ["table", "table_name", "tablename", "entity", "key_table", "dataset", "object", "physical_table"],
    "schema": ["schema", "schema_name", "database", "db"],
    "column": ["column", "column_name", "columnname", "attribute", "field", "key_column", "physical_column"],
    "type": ["type", "data_type", "datatype", "logical_type", "physical_type", "technical data type"],
    "nullable": ["nullable", "is_nullable", "null", "optional"],
    "pk": ["pk", "primary_key", "is_primary_key", "key"],
    "description": ["description", "comment", "definition", "notes"],
    "classification": ["classification", "sensitivity", "security classification", "data_classification"],
}


def _pick(row: dict, field: str):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for alias in CSV_ALIASES[field]:
        if alias in low and low[alias] not in (None, ""):
            return low[alias]
    return None


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("y", "yes", "true", "1", "pk", "x")


def from_csv(text: str) -> dict:
    tables: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        t, c = _pick(row, "table"), _pick(row, "column")
        if not t:
            continue
        schema = _pick(row, "schema") or ""
        if "." in t and not schema:
            schema, t = t.rsplit(".", 1)
        tbl = tables.setdefault(t, {"name": t, "schema": schema, "description": "", "columns": []})
        if not c:
            tbl["description"] = _pick(row, "description") or tbl["description"]
            continue
        nullable = _pick(row, "nullable")
        tbl["columns"].append({"name": c, "type": str(_pick(row, "type") or "string"),
                               "nullable": True if nullable is None else _truthy(nullable),
                               "pk": _truthy(_pick(row, "pk") or ""), "description": _pick(row, "description") or "",
                               "classification": (_pick(row, "classification") or "").lower() or None})
    return {"tables": list(tables.values())}


def from_json(text: str) -> dict:
    d = json.loads(text)
    if "entities" in d:
        return {"tables": [{"name": e["name"], "schema": "", "description": e.get("description", ""),
                            "columns": [{"name": a["name"], "type": a.get("type", "string"),
                                         "nullable": a.get("nullable", True), "pk": a.get("pk", False),
                                         "description": a.get("description", ""),
                                         "classification": a.get("classification")} for a in e.get("attributes", [])]}
                           for e in d["entities"]], "model": d}
    if "tables" in d:
        return d
    raise ValueError("JSON must contain `entities` (ADPE model) or `tables`")


def from_dbml(text: str) -> dict:
    tables = []
    for m in re.finditer(r"Table\s+([\w.\"]+)(?:\s+as\s+\w+)?\s*(?:\[[^\]]*\])?\s*\{(.*?)\n\}", text, re.S):
        name = m.group(1).strip('"')
        schema = ""
        if "." in name:
            schema, name = name.rsplit(".", 1)
        cols = []
        for line in m.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith(("//", "Note", "indexes", "}")):
                continue
            cm = re.match(r'"?([\w]+)"?\s+([\w(),\s]+?)(?:\s*\[(.*)\])?$', line)
            if not cm:
                continue
            opts = (cm.group(3) or "").lower()
            note = re.search(r"note:\s*'([^']*)'", cm.group(3) or "")
            cols.append({"name": cm.group(1), "type": cm.group(2).strip(), "pk": "pk" in opts or "primary key" in opts,
                         "nullable": "not null" not in opts and "pk" not in opts,
                         "description": note.group(1) if note else "", "classification": None})
        tables.append({"name": name, "schema": schema, "description": "", "columns": cols})
    if not tables:
        raise ValueError("no Table blocks found in DBML")
    return {"tables": tables}


def _balanced(text: str, start: int) -> tuple[str, int]:
    """Return the text inside the parenthesis opening at `start`, and the index after it."""
    depth, i, quote = 0, start, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def _split_top(body: str) -> list[str]:
    parts, cur, depth, quote = [], "", 0, None
    for ch in body:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def from_ddl(text: str) -> dict:
    tables = []
    head = re.compile(r"create\s+(?:or\s+replace\s+)?(?:transient\s+|external\s+)?table\s+"
                      r"(?:if\s+not\s+exists\s+)?([\w.\"`\[\]]+)\s*\(", re.I)
    for m in head.finditer(text):
        full = re.sub(r"[\"`\[\]]", "", m.group(1))
        schema, name = (full.rsplit(".", 1) if "." in full else ("", full))
        body, _ = _balanced(text, m.end() - 1)
        cols, pks = [], set()
        for p in _split_top(body):
            p = p.strip()
            pk = re.search(r"primary\s+key\s*\(([^)]*)\)", p, re.I)
            if pk:
                pks |= {c.strip().strip('"`').lower() for c in pk.group(1).split(",")}
                continue
            if re.match(r"(constraint|foreign|unique|index|key|check)\b", p, re.I):
                continue
            cm = re.match(r'["`\[]?(\w+)["`\]]?\s+([\w]+(?:\s*\([\d,\s]+\))?)(.*)$', p, re.S)
            if cm:
                rest = cm.group(3)
                com = re.search(r"comment\s+'((?:[^']|'')*)'", rest, re.I)
                cols.append({"name": cm.group(1), "type": cm.group(2), "nullable": not re.search(r"not\s+null", rest, re.I),
                             "pk": bool(re.search(r"primary\s+key", rest, re.I)),
                             "description": com.group(1).replace("''", "'") if com else "", "classification": None})
        for c in cols:
            if c["name"].lower() in pks:
                c["pk"] = True
                c["nullable"] = False
        tables.append({"name": name, "schema": schema, "description": "", "columns": cols})
    if not tables:
        raise ValueError("no CREATE TABLE statements found")
    return {"tables": tables}


def detect_and_parse(filename: str, text: str) -> dict:
    fn = filename.lower()
    if fn.endswith(".csv"):
        meta = from_csv(text)
    elif fn.endswith(".json"):
        meta = from_json(text)
    elif fn.endswith(".dbml"):
        meta = from_dbml(text)
    elif fn.endswith((".sql", ".ddl")):
        meta = from_ddl(text)
    else:
        s = text.lstrip()
        if s.startswith("{"):
            meta = from_json(text)
        elif re.search(r"create\s+table", text, re.I):
            meta = from_ddl(text)
        elif re.search(r"^Table\s", text, re.M):
            meta = from_dbml(text)
        else:
            meta = from_csv(text)
    findings = {"injection": scan_injection(text), "secrets": len(scan_secrets(text))}
    meta["source_file"] = filename
    meta["stats"] = {"tables": len(meta["tables"]), "columns": sum(len(t["columns"]) for t in meta["tables"])}
    meta["untrusted_content_findings"] = findings
    return meta


def to_logical_model(meta: dict, name: str = "imported-model", domain: str = "") -> dict:
    """Turn imported tables into a draft logical model (classification unknown -> restricted)."""
    if meta.get("model"):
        return meta["model"]
    ents = []
    for t in meta["tables"]:
        en = re.sub(r"^(dim|fct|fact|stg|ref)_", "", t["name"].lower())
        en = re.sub(r"[^a-z0-9_]", "_", en)
        attrs = []
        for c in t["columns"]:
            base, args = parse_type(c.get("type", "string"))
            lt = f"{base}({','.join(map(str, args))})" if args and base in ("string", "decimal") else base
            attrs.append({"name": re.sub(r"[^a-z0-9_]", "_", c["name"].lower()), "type": lt,
                          "nullable": c.get("nullable", True), "pk": c.get("pk", False),
                          "classification": c.get("classification") or "restricted",
                          "description": c.get("description", "")})
        kind = "fact" if t["name"].lower().startswith(("fct", "fact")) else "dimension"
        ents.append({"name": en, "kind": kind, "description": t.get("description", ""), "attributes": attrs})
    names = {e["name"] for e in ents}
    for e in ents:  # infer FKs by <entity>_id naming
        for a in e["attributes"]:
            if a["name"].endswith("_id") and not a["pk"]:
                target = a["name"][:-3]
                if target in names and target != e["name"]:
                    te = next(x for x in ents if x["name"] == target)
                    pk = next((x["name"] for x in te["attributes"] if x["pk"]), None)
                    if pk:
                        a["fk"] = {"entity": target, "attribute": pk}
    return {"name": name, "version": "0.1.0", "domain": domain,
            "description": f"Imported from {meta.get('source_file', 'metadata')}", "entities": ents, "metrics": []}
