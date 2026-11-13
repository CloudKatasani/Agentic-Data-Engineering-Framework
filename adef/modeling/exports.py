"""Data modelling and data catalog exports.

Every exporter renders from the logical model (plus, where useful, the Stack Profile,
the source-to-target mapping and the Domain Pack glossary). Physical exports apply the
Stack Profile's naming and the dialect's type map; logical exports stay neutral.

Catalog payloads follow each product's documented import/bulk format in shape. Field
names for client-specific operating models (Collibra domain/community names, Purview
collections, DataHub platform instance) come from export options; review them with the
catalog owner before loading into a shared catalog (that load is an A2 action).
"""
from __future__ import annotations

import csv
import io
import json
from typing import Callable

from ..util import dump_yaml, now_iso
from . import physical as ph
from .logical import normalize, parse_type, relationships

Ctx = dict


def _all_columns(e: dict, dialect: str, profile: dict | None, with_tech: bool = True):
    cols = []
    for n, t in ph.scd_columns(e) if with_tech else []:
        cols.append({"name": n, "type": t, "nullable": n not in (f"{e['name']}_sk",), "pk": n == f"{e['name']}_sk",
                     "description": "Surrogate key / history column (type 2)", "classification": "internal", "tech": True})
    for a in e["attributes"]:
        cols.append({**a, "tech": False})
    for n, t in ph.audit_columns() if with_tech else []:
        cols.append({"name": n, "type": t, "nullable": True, "pk": False, "description": "Audit column",
                     "classification": "internal", "tech": True})
    return cols


# ------------------------------------------------------------------ DDL
def export_ddl(model: dict, ctx: Ctx) -> str:
    d = ctx.get("dialect") or ph.dialect_for(ctx.get("profile"))
    prof = ctx.get("profile")
    schema = ph.schema_name(prof)
    out = [f"-- ADEF physical DDL | model {model['name']} v{model['version']} | dialect {ph.DIALECT_LABELS.get(d, d)}",
           f"-- Generated {ctx.get('generated_at') or now_iso()} from the approved logical model. Review before running (A2).", ""]
    if d == "tsql":
        out.append(f"IF SCHEMA_ID('{schema}') IS NULL EXEC('CREATE SCHEMA {schema}');")
    else:
        out.append(f"CREATE SCHEMA IF NOT EXISTS {schema};")
    out.append("")
    for e in model["entities"]:
        t = ph.table_name(e, prof)
        cols = _all_columns(e, d, prof)
        lines = []
        for c in cols:
            nm = ph.case(c["name"], prof)
            nn = "" if c.get("nullable", True) else " NOT NULL"
            com = ""
            if c.get("description") and d in ("snowflake", "databricks", "bigquery"):
                desc = c["description"].replace("'", "''")
                com = f" OPTIONS(description='{desc}')" if d == "bigquery" else f" COMMENT '{desc}'"
            lines.append(f"    {nm} {ph.phys_type(c['type'], d)}{nn}{com}")
        pk = [ph.case(c["name"], prof) for c in cols if c.get("pk")]
        if e.get("history") == "type2":
            pk = [ph.case(f"{e['name']}_sk", prof)]
        if pk and d not in ("bigquery", "databricks"):
            lines.append(f"    CONSTRAINT pk_{e['name']} PRIMARY KEY ({', '.join(pk)})")
        body = ",\n".join(lines)
        tail = ""
        if d == "databricks":
            tail = " USING DELTA"
            if e.get("description"):
                tail += f"\nCOMMENT '{e['description'][:250].replace(chr(39), chr(39) * 2)}'"
        if d == "snowflake" and e.get("description"):
            tail = f"\nCOMMENT = '{e['description'][:250].replace(chr(39), chr(39) * 2)}'"
        if d == "redshift" and e["kind"] == "fact":
            tail = "\nDISTSTYLE AUTO SORTKEY AUTO"
        out.append(f"-- {e['label']} ({e['kind']}, history: {e['history']}) grain: {e.get('grain') or 'n/a'}")
        if d == "tsql":
            out.append(f"IF OBJECT_ID('{schema}.{t}', 'U') IS NULL\nCREATE TABLE {schema}.{t} (\n{body}\n){tail};\n")
        else:
            out.append(f"CREATE TABLE IF NOT EXISTS {schema}.{t} (\n{body}\n){tail};\n")
    if d not in ("bigquery",):
        for r in relationships(model):
            fe = next(x for x in model["entities"] if x["name"] == r["from_entity"])
            te = next(x for x in model["entities"] if x["name"] == r["to_entity"])
            note = " -- informational (not enforced)" if d in ("snowflake", "databricks", "redshift") else ""
            out.append(f"ALTER TABLE {schema}.{ph.table_name(fe, prof)} ADD CONSTRAINT fk_{fe['name']}_{r['from_attribute']} "
                       f"FOREIGN KEY ({ph.case(r['from_attribute'], prof)}) REFERENCES {schema}.{ph.table_name(te, prof)} "
                       f"({ph.case(r['to_attribute'], prof)}){' NOT ENFORCED' if d == 'databricks' else ''};{note}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ DBML / Mermaid / PlantUML
def export_dbml(model: dict, ctx: Ctx) -> str:
    out = [f"// {model['name']} v{model['version']} - logical model (dbdiagram.io / dbdocs)",
           f"Project {model['name'].replace('-', '_')} {{\n  database_type: 'Logical'\n  Note: '{model.get('description', '').replace(chr(39), '')}'\n}}\n"]
    for e in model["entities"]:
        out.append(f"Table {e['name']} [note: '{e['kind']} | history {e['history']} | grain: {e.get('grain', '')}'] {{")
        for a in e["attributes"]:
            opts = []
            if a["pk"]:
                opts.append("pk")
            if not a["nullable"] and not a["pk"]:
                opts.append("not null")
            if a.get("fk"):
                opts.append(f"ref: > {a['fk']['entity']}.{a['fk']['attribute']}")
            note = f"{a['classification']}: {a.get('description', '')}".replace("'", "")
            opts.append(f"note: '{note}'")
            out.append(f"  {a['name']} {a['type'].replace(' ', '')} [{', '.join(opts)}]")
        out.append("}\n")
    return "\n".join(out)


def export_mermaid(model: dict, ctx: Ctx) -> str:
    out = ["erDiagram"]
    for r in relationships(model):
        out.append(f"    {r['to_entity'].upper()} ||--o{{ {r['from_entity'].upper()} : \"{r['from_attribute']}\"")
    for e in model["entities"]:
        out.append(f"    {e['name'].upper()} {{")
        for a in e["attributes"]:
            base, _ = parse_type(a["type"])
            key = " PK" if a["pk"] else (" FK" if a.get("fk") else "")
            out.append(f"        {base} {a['name']}{key}")
        out.append("    }")
    return "\n".join(out) + "\n"


def export_plantuml(model: dict, ctx: Ctx) -> str:
    out = ["@startuml", "hide circle", "skinparam linetype ortho", ""]
    for e in model["entities"]:
        out.append(f'entity "{e["label"]}" as {e["name"]} {{')
        for a in [x for x in e["attributes"] if x["pk"]]:
            out.append(f"  * {a['name']} : {a['type']}")
        out.append("  --")
        for a in [x for x in e["attributes"] if not x["pk"]]:
            out.append(f"  {'*' if not a['nullable'] else ''}{a['name']} : {a['type']}{' <<FK>>' if a.get('fk') else ''}")
        out.append("}")
    for r in relationships(model):
        out.append(f"{r['to_entity']} ||..o{{ {r['from_entity']}")
    out.append("@enduml")
    return "\n".join(out) + "\n"


def export_json(model: dict, ctx: Ctx) -> str:
    return json.dumps(model, indent=2)


# ------------------------------------------------------------------ dbt / data contract
def export_dbt_schema(model: dict, ctx: Ctx) -> str:
    prof = ctx.get("profile")
    dq = ctx.get("dq_rules") or []
    models = []
    for e in model["entities"]:
        cols = []
        for a in e["attributes"]:
            tests = []
            if a["pk"] and e.get("history") != "type2":
                tests += ["unique", "not_null"]
            elif not a["nullable"]:
                tests.append("not_null")
            if a.get("fk"):
                te = next(x for x in model["entities"] if x["name"] == a["fk"]["entity"])
                tests.append({"relationships": {"to": f"ref('{ph.table_name(te, None)}')", "field": a["fk"]["attribute"]}})
            for r in dq:
                if r.get("entity") == e["name"] and r.get("attribute") == a["name"] and r.get("type") == "accepted_values":
                    tests.append({"accepted_values": {"values": r["params"].get("values", [])}})
            col = {"name": ph.case(a["name"], prof), "description": a.get("description", ""),
                   "meta": {"classification": a["classification"], "business_rule": a.get("business_rule")}}
            if tests:
                col["data_tests"] = tests
            if a["classification"] == "restricted":
                col["tags"] = ["pii", "restricted"]
            cols.append(col)
        models.append({"name": ph.table_name(e, None), "description": e.get("description", ""),
                       "meta": {"grain": e.get("grain"), "history": e.get("history"), "owner": ctx.get("owner", "")},
                       "config": {"contract": {"enforced": True}}, "columns": cols})
    return dump_yaml({"version": 2, "models": models})


def export_odcs(model: dict, ctx: Ctx) -> str:
    """Open Data Contract Standard (ODCS) v3-style contract."""
    prof = ctx.get("profile")
    schema = []
    for e in model["entities"]:
        props = []
        for a in e["attributes"]:
            base, args = parse_type(a["type"])
            p = {"name": a["name"], "logicalType": {"string": "string", "integer": "integer", "bigint": "integer",
                                                    "decimal": "number", "boolean": "boolean", "date": "date",
                                                    "timestamp": "date"}[base],
                 "physicalType": ph.phys_type(a["type"], ph.dialect_for(prof)) if prof else a["type"],
                 "required": not a["nullable"], "primaryKey": a["pk"], "classification": a["classification"],
                 "description": a.get("description", "")}
            if a.get("business_rule"):
                p["businessRule"] = a["business_rule"]
            props.append(p)
        schema.append({"name": e["name"], "physicalName": ph.table_name(e, prof) if prof else e["name"],
                       "logicalType": "object", "description": e.get("description", ""),
                       "dataGranularityDescription": e.get("grain", ""), "properties": props})
    quality = [{"rule": r.get("type"), "id": r.get("id"), "element": f"{r.get('entity')}.{r.get('attribute')}",
                "mustBe": r.get("params"), "threshold": r.get("threshold"), "severity": r.get("severity")}
               for r in (ctx.get("dq_rules") or [])]
    contract = {"apiVersion": "v3.0.2", "kind": "DataContract", "id": f"{ctx.get('run_id', 'adef')}-{model['name']}",
                "name": model["name"], "version": model["version"], "status": ctx.get("contract_status", "draft"),
                "domain": model.get("domain", ""), "description": {"purpose": model.get("description", "")},
                "schema": schema, "quality": quality,
                "slaProperties": ctx.get("sla") or [{"property": "frequency", "value": "daily"},
                                                    {"property": "latency", "value": 6, "unit": "h"}],
                "team": [{"role": k, "username": v} for k, v in (ctx.get("approvers") or {}).items()]}
    return dump_yaml(contract)


# ------------------------------------------------------------------ catalogs
def _qn(ctx, *parts):
    return ".".join([ctx.get("catalog_prefix") or "adef"] + [p for p in parts if p])


def export_collibra(model: dict, ctx: Ctx) -> str:
    community = ctx.get("collibra_community") or "Data Products"
    domain = ctx.get("collibra_domain") or f"{model['name']} - Physical Data Dictionary"
    gdomain = ctx.get("collibra_glossary_domain") or f"{model.get('domain', 'Business')} Glossary"
    prof = ctx.get("profile")
    schema = ph.schema_name(prof)
    items = []
    dom = {"name": domain, "community": {"name": community}}
    for e in model["entities"]:
        tname = f"{schema}.{ph.table_name(e, prof)}"
        items.append({"resourceType": "Asset", "identifier": {"name": tname, "domain": dom},
                      "name": tname, "displayName": e["label"], "type": {"name": "Table"},
                      "attributes": {"Description": [{"value": e.get("description", "")}],
                                     "Note": [{"value": f"grain: {e.get('grain', '')}; history: {e['history']}"}]}})
        for a in e["attributes"]:
            cname = f"{tname}.{ph.case(a['name'], prof)}"
            items.append({"resourceType": "Asset", "identifier": {"name": cname, "domain": dom},
                          "name": cname, "displayName": a["label"], "type": {"name": "Column"},
                          "attributes": {"Description": [{"value": a.get("description", "")}],
                                         "Technical Data Type": [{"value": ph.phys_type(a["type"], ph.dialect_for(prof))}],
                                         "Is Primary Key": [{"value": bool(a["pk"])}],
                                         "Is Nullable": [{"value": bool(a["nullable"])}],
                                         "Security Classification": [{"value": a["classification"].title()}]},
                          "relations": {"00000000-0000-0000-0000-000000007042:SOURCE": [{"name": tname, "domain": dom}]}})
    gdom = {"name": gdomain, "community": {"name": community}}
    for m in model.get("metrics", []):
        items.append({"resourceType": "Asset", "identifier": {"name": m["label"], "domain": gdom}, "name": m["label"],
                      "type": {"name": "Business Term"},
                      "attributes": {"Definition": [{"value": m.get("definition", "")}],
                                     "Note": [{"value": f"Formula: {m.get('expression', '')}"}]}})
    for t in ctx.get("glossary") or []:
        items.append({"resourceType": "Asset", "identifier": {"name": t["term"], "domain": gdom}, "name": t["term"],
                      "type": {"name": "Business Term"}, "attributes": {"Definition": [{"value": t["definition"]}]}})
    return json.dumps(items, indent=2)


def export_atlas(model: dict, ctx: Ctx) -> str:
    """Apache Atlas v2 bulk entity payload (also accepted by Microsoft Purview's Atlas API)."""
    prof = ctx.get("profile")
    schema = ph.schema_name(prof)
    db_qn = _qn(ctx, schema)
    entities, guid = [], -1
    db_guid = str(guid)
    entities.append({"typeName": "rdbms_db", "guid": db_guid,
                     "attributes": {"qualifiedName": db_qn, "name": schema, "description": model.get("description", "")}})
    for e in model["entities"]:
        guid -= 1
        tguid = str(guid)
        tqn = f"{db_qn}.{ph.table_name(e, prof)}"
        entities.append({"typeName": "rdbms_table", "guid": tguid,
                         "attributes": {"qualifiedName": tqn, "name": ph.table_name(e, prof),
                                        "description": e.get("description", ""), "comment": f"grain: {e.get('grain', '')}",
                                        "db": {"guid": db_guid, "typeName": "rdbms_db"}}})
        for a in e["attributes"]:
            guid -= 1
            ent = {"typeName": "rdbms_column", "guid": str(guid),
                   "attributes": {"qualifiedName": f"{tqn}.{ph.case(a['name'], prof)}", "name": ph.case(a["name"], prof),
                                  "data_type": ph.phys_type(a["type"], ph.dialect_for(prof)),
                                  "isPrimaryKey": bool(a["pk"]), "isNullable": bool(a["nullable"]),
                                  "description": a.get("description", ""),
                                  "table": {"guid": tguid, "typeName": "rdbms_table"}}}
            if a["classification"] in ("restricted", "confidential"):
                ent["classifications"] = [{"typeName": ctx.get("atlas_classification_prefix", "ADEF_")
                                           + a["classification"].upper()}]
            entities.append(ent)
    return json.dumps({"entities": entities}, indent=2)


def export_datahub(model: dict, ctx: Ctx) -> str:
    """DataHub metadata change proposals (file source format)."""
    prof = ctx.get("profile")
    platform = ctx.get("datahub_platform") or (prof and (prof.get("slots", {}).get("compute_engine") or {}).get("tool")) or "logical"
    env = ctx.get("datahub_env", "PROD")
    schema = ph.schema_name(prof)
    mcps = []
    for e in model["entities"]:
        name = f"{schema}.{ph.table_name(e, prof)}".lower()
        urn = f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env})"
        mcps.append({"entityType": "dataset", "entityUrn": urn, "changeType": "UPSERT", "aspectName": "datasetProperties",
                     "aspect": {"json": {"name": ph.table_name(e, prof), "description": e.get("description", ""),
                                         "customProperties": {"grain": e.get("grain", ""), "history": e["history"],
                                                              "adef_model": model["name"]}}}})
        fields = []
        for a in e["attributes"]:
            base, _ = parse_type(a["type"])
            dh = {"string": "StringType", "integer": "NumberType", "bigint": "NumberType", "decimal": "NumberType",
                  "boolean": "BooleanType", "date": "DateType", "timestamp": "TimeType"}[base]
            f = {"fieldPath": a["name"], "nativeDataType": ph.phys_type(a["type"], ph.dialect_for(prof)),
                 "type": {"type": {f"com.linkedin.schema.{dh}": {}}}, "nullable": bool(a["nullable"]),
                 "description": a.get("description", ""), "isPartOfKey": bool(a["pk"])}
            if a["classification"] in ("restricted", "confidential"):
                f["globalTags"] = {"tags": [{"tag": f"urn:li:tag:{a['classification']}"}]}
            fields.append(f)
        mcps.append({"entityType": "dataset", "entityUrn": urn, "changeType": "UPSERT", "aspectName": "schemaMetadata",
                     "aspect": {"json": {"schemaName": name, "platform": f"urn:li:dataPlatform:{platform}", "version": 0,
                                         "hash": "", "platformSchema": {"com.linkedin.schema.OtherSchema": {"rawSchema": ""}},
                                         "fields": fields}}})
    for m in model.get("metrics", []):
        mcps.append({"entityType": "glossaryTerm", "entityUrn": f"urn:li:glossaryTerm:{m['name']}", "changeType": "UPSERT",
                     "aspectName": "glossaryTermInfo",
                     "aspect": {"json": {"name": m["label"], "definition": m.get("definition", ""), "termSource": "INTERNAL"}}})
    return json.dumps(mcps, indent=2)


def _csv(rows: list[list], header: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def export_alation(model: dict, ctx: Ctx) -> str:
    prof = ctx.get("profile")
    schema = ph.schema_name(prof)
    rows = []
    for e in model["entities"]:
        t = f"{schema}.{ph.table_name(e, prof)}"
        rows.append([t, "", e["label"], e.get("description", ""), "", ""])
        for a in e["attributes"]:
            rows.append([t, ph.case(a["name"], prof), a["label"], a.get("description", ""),
                         a["classification"].title(), a.get("business_rule") or ""])
    return _csv(rows, ["key_table", "key_column", "title", "description", "classification", "business_rule"])


def export_dictionary(model: dict, ctx: Ctx) -> str:
    prof = ctx.get("profile")
    d = ph.dialect_for(prof)
    rows = []
    for e in model["entities"]:
        for a in e["attributes"]:
            rows.append([e["name"], ph.table_name(e, prof), e["kind"], e["history"], a["name"], ph.case(a["name"], prof),
                         a["type"], ph.phys_type(a["type"], d), "Y" if a["pk"] else "",
                         f"{a['fk']['entity']}.{a['fk']['attribute']}" if a.get("fk") else "",
                         "Y" if a["nullable"] else "N", a["classification"], a.get("business_rule") or "",
                         ";".join(a.get("req_ids") or []), a.get("description", "")])
    return _csv(rows, ["entity", "physical_table", "kind", "history", "attribute", "physical_column", "logical_type",
                       "physical_type", "pk", "fk", "nullable", "classification", "business_rule", "requirements",
                       "description"])


def export_glossary(model: dict, ctx: Ctx) -> str:
    rows = [[t["term"], t["definition"], "domain-pack", ""] for t in ctx.get("glossary") or []]
    rows += [[m["label"], m.get("definition", ""), "metric", m.get("business_rule") or ""] for m in model.get("metrics", [])]
    rows += [[g["term"], g["definition"], "glossary-delta", g.get("owner", "")] for g in ctx.get("glossary_delta") or []]
    return _csv(rows, ["term", "definition", "source", "reference"])


def export_unity_sql(model: dict, ctx: Ctx) -> str:
    prof = ctx.get("profile")
    cat = ctx.get("uc_catalog") or "main"
    schema = ph.schema_name(prof)
    out = [f"-- Unity Catalog governance metadata for {model['name']} (review; applying is A2, grants are A3)", ""]
    restricted = []
    for e in model["entities"]:
        t = f"{cat}.{schema}.{ph.table_name(e, prof)}"
        if e.get("description"):
            out.append(f"COMMENT ON TABLE {t} IS '{e['description'].replace(chr(39), chr(39) * 2)}';")
        out.append(f"ALTER TABLE {t} SET TAGS ('adef_model' = '{model['name']}', 'grain' = '{e.get('grain', '')[:200]}');")
        for a in e["attributes"]:
            c = ph.case(a["name"], prof)
            if a.get("description"):
                out.append(f"ALTER TABLE {t} ALTER COLUMN {c} COMMENT '{a['description'].replace(chr(39), chr(39) * 2)}';")
            out.append(f"ALTER TABLE {t} ALTER COLUMN {c} SET TAGS ('classification' = '{a['classification']}');")
            if a["classification"] == "restricted":
                restricted.append((t, c))
        out.append("")
    if restricted:
        out += ["-- Column masks for Restricted attributes (A3: Security and Compliance approval required)",
                f"CREATE FUNCTION IF NOT EXISTS {cat}.{schema}.mask_restricted(v STRING) RETURNS STRING "
                "RETURN CASE WHEN is_account_group_member('restricted_readers') THEN v ELSE '***' END;"]
        out += [f"-- ALTER TABLE {t} ALTER COLUMN {c} SET MASK {cat}.{schema}.mask_restricted;" for t, c in restricted]
    return "\n".join(out) + "\n"


def export_snowflake_gov(model: dict, ctx: Ctx) -> str:
    prof = ctx.get("profile")
    schema = ph.schema_name(prof)
    out = [f"-- Snowflake governance metadata for {model['name']} (review; applying is A2, policies are A3)", "",
           f"CREATE TAG IF NOT EXISTS {schema}.CLASSIFICATION ALLOWED_VALUES 'public','internal','confidential','restricted';",
           f"CREATE MASKING POLICY IF NOT EXISTS {schema}.MASK_RESTRICTED AS (v VARCHAR) RETURNS VARCHAR ->",
           "  CASE WHEN IS_ROLE_IN_SESSION('RESTRICTED_READER') THEN v ELSE '***MASKED***' END;", ""]
    for e in model["entities"]:
        t = f"{schema}.{ph.table_name(e, prof)}"
        if e.get("description"):
            out.append(f"COMMENT ON TABLE {t} IS '{e['description'].replace(chr(39), chr(39) * 2)}';")
        for a in e["attributes"]:
            c = ph.case(a["name"], prof)
            out.append(f"ALTER TABLE {t} MODIFY COLUMN {c} SET TAG {schema}.CLASSIFICATION = '{a['classification']}';")
            if a["classification"] == "restricted" and parse_type(a["type"])[0] == "string":
                out.append(f"-- ALTER TABLE {t} MODIFY COLUMN {c} SET MASKING POLICY {schema}.MASK_RESTRICTED;")
        out.append("")
    return "\n".join(out)


def export_openlineage(model: dict, ctx: Ctx) -> str:
    """OpenLineage RunEvents (one per target table) with column-lineage facets from the mapping."""
    prof = ctx.get("profile")
    ns = ctx.get("lineage_namespace") or f"adef://{(prof or {}).get('profile_id', 'logical')}"
    schema = ph.schema_name(prof)
    mapping = ctx.get("mapping") or []
    events = []
    for e in model["entities"]:
        rows = [m for m in mapping if m.get("target_entity") == e["name"]]
        if not rows:
            continue
        inputs = sorted({m["source"].rsplit(".", 1)[0] for m in rows if m.get("source") and "." in m["source"]})
        fields = {}
        for m in rows:
            if m.get("source") and "." in m["source"]:
                ds, col = m["source"].rsplit(".", 1)
                fields.setdefault(m["target_attribute"], {"inputFields": [],
                                                          "transformationDescription": m.get("transformation", "")})
                fields[m["target_attribute"]]["inputFields"].append({"namespace": ns, "name": ds, "field": col})
        events.append({"eventType": "COMPLETE", "eventTime": ctx.get("generated_at") or now_iso(), "producer": "https://adef.local/adef-framework",
                       "schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json#/definitions/RunEvent",
                       "run": {"runId": "00000000-0000-4000-8000-000000000000"},
                       "job": {"namespace": ns, "name": f"load_{ph.table_name(e, prof).lower()}"},
                       "inputs": [{"namespace": ns, "name": i} for i in inputs],
                       "outputs": [{"namespace": ns, "name": f"{schema}.{ph.table_name(e, prof)}",
                                    "facets": {"columnLineage": {
                                        "_producer": "https://adef.local/adef-framework",
                                        "_schemaURL": "https://openlineage.io/spec/facets/1-1-0/ColumnLineageDatasetFacet.json",
                                        "fields": fields}}}]})
    return json.dumps(events, indent=2)


EXPORTERS: list[dict] = [
    {"id": "ddl", "label": "Physical DDL (stack dialect)", "category": "Data model", "ext": "sql", "fn": export_ddl,
     "dialects": list(ph.DIALECT_LABELS), "desc": "CREATE TABLE/constraints for the bound compute engine. Imports into erwin, ER/Studio, SqlDBM, PowerDesigner via reverse-engineering."},
    {"id": "dbml", "label": "DBML (dbdiagram.io / dbdocs)", "category": "Data model", "ext": "dbml", "fn": export_dbml,
     "desc": "Logical model with keys, refs and classification notes."},
    {"id": "mermaid", "label": "Mermaid ER diagram", "category": "Data model", "ext": "mmd", "fn": export_mermaid,
     "desc": "Renders in GitHub, GitLab, Confluence and most markdown tools."},
    {"id": "plantuml", "label": "PlantUML ER diagram", "category": "Data model", "ext": "puml", "fn": export_plantuml,
     "desc": "Information-engineering notation ER diagram."},
    {"id": "json", "label": "ADEF logical model (JSON)", "category": "Data model", "ext": "json", "fn": export_json,
     "desc": "Canonical technology-neutral model; re-importable."},
    {"id": "dbt", "label": "dbt schema.yml", "category": "Data model", "ext": "yml", "fn": export_dbt_schema,
     "desc": "Model contracts, column docs, classification meta and data tests."},
    {"id": "odcs", "label": "Data contract (ODCS v3)", "category": "Contract", "ext": "yaml", "fn": export_odcs,
     "desc": "Open Data Contract Standard: schema, quality, SLA, team."},
    {"id": "dictionary", "label": "Data dictionary (CSV)", "category": "Catalog", "ext": "csv", "fn": export_dictionary,
     "desc": "Logical-to-physical dictionary for any catalog or spreadsheet."},
    {"id": "collibra", "label": "Collibra Import API (JSON)", "category": "Catalog", "ext": "json", "fn": export_collibra,
     "desc": "Tables, columns and business terms with relations."},
    {"id": "atlas", "label": "Microsoft Purview / Apache Atlas (JSON)", "category": "Catalog", "ext": "json", "fn": export_atlas,
     "desc": "Atlas v2 bulk entities (rdbms_db/table/column) with classifications."},
    {"id": "datahub", "label": "DataHub MCPs (JSON)", "category": "Catalog", "ext": "json", "fn": export_datahub,
     "desc": "datasetProperties, schemaMetadata and glossary terms."},
    {"id": "alation", "label": "Alation bulk metadata (CSV)", "category": "Catalog", "ext": "csv", "fn": export_alation,
     "desc": "Titles, descriptions and classification per table/column."},
    {"id": "glossary", "label": "Business glossary (CSV)", "category": "Catalog", "ext": "csv", "fn": export_glossary,
     "desc": "Domain Pack terms, metrics and glossary delta."},
    {"id": "unity", "label": "Unity Catalog governance SQL", "category": "Governance", "ext": "sql", "fn": export_unity_sql,
     "desc": "Comments, classification tags and column masks."},
    {"id": "snowflake-gov", "label": "Snowflake governance SQL", "category": "Governance", "ext": "sql",
     "fn": export_snowflake_gov, "desc": "Classification tags and masking policy for Restricted columns."},
    {"id": "openlineage", "label": "OpenLineage events (JSON)", "category": "Lineage", "ext": "json",
     "fn": export_openlineage, "desc": "Table and column lineage from the source-to-target mapping."},
]


def list_exporters() -> list[dict]:
    return [{k: v for k, v in e.items() if k != "fn"} for e in EXPORTERS]


def render(fmt: str, model: dict, ctx: Ctx | None = None) -> tuple[str, str]:
    ctx = dict(ctx or {})
    ex = next((e for e in EXPORTERS if e["id"] == fmt), None)
    if not ex:
        raise KeyError(f"unknown export format {fmt}")
    model = normalize(json.loads(json.dumps(model)))
    fn: Callable = ex["fn"]
    content = fn(model, ctx)
    suffix = f"-{ctx['dialect']}" if fmt == "ddl" and ctx.get("dialect") else ""
    return f"{model['name']}-{fmt}{suffix}.{ex['ext']}", content
