"""Logical -> physical naming and types per Stack Profile (stack-binding task T3)."""
from __future__ import annotations

from ..catalog.stacks import dialect as stack_dialect
from .logical import parse_type

TYPE_MAP = {
    "snowflake": {"string": "VARCHAR({n})", "string_": "VARCHAR", "integer": "NUMBER(38,0)", "bigint": "NUMBER(38,0)",
                  "decimal": "NUMBER({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP_NTZ"},
    "databricks": {"string": "STRING", "string_": "STRING", "integer": "INT", "bigint": "BIGINT",
                   "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "bigquery": {"string": "STRING", "string_": "STRING", "integer": "INT64", "bigint": "INT64",
                 "decimal": "NUMERIC({p},{s})", "boolean": "BOOL", "date": "DATE", "timestamp": "TIMESTAMP"},
    "redshift": {"string": "VARCHAR({n})", "string_": "VARCHAR(256)", "integer": "INTEGER", "bigint": "BIGINT",
                 "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "postgres": {"string": "VARCHAR({n})", "string_": "TEXT", "integer": "INTEGER", "bigint": "BIGINT",
                 "decimal": "NUMERIC({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "tsql": {"string": "VARCHAR({n})", "string_": "VARCHAR(4000)", "integer": "INT", "bigint": "BIGINT",
             "decimal": "DECIMAL({p},{s})", "boolean": "BIT", "date": "DATE", "timestamp": "DATETIME2(6)"},
    "ansi": {"string": "VARCHAR({n})", "string_": "VARCHAR(255)", "integer": "INTEGER", "bigint": "BIGINT",
             "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "duckdb": {"string": "VARCHAR", "string_": "VARCHAR", "integer": "INTEGER", "bigint": "BIGINT",
               "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "oracle": {"string": "VARCHAR2({n})", "string_": "VARCHAR2(4000)", "integer": "NUMBER(10)", "bigint": "NUMBER(19)",
               "decimal": "NUMBER({p},{s})", "boolean": "NUMBER(1)", "date": "DATE", "timestamp": "TIMESTAMP"},
    "db2": {"string": "VARCHAR({n})", "string_": "VARCHAR(4000)", "integer": "INTEGER", "bigint": "BIGINT",
            "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "sqlite": {"string": "TEXT", "string_": "TEXT", "integer": "INTEGER", "bigint": "INTEGER",
               "decimal": "REAL", "boolean": "INTEGER", "date": "TEXT", "timestamp": "TEXT"},
}
DIALECT_LABELS = {"snowflake": "Snowflake", "databricks": "Databricks (Delta)", "bigquery": "BigQuery",
                  "redshift": "Redshift", "postgres": "PostgreSQL", "tsql": "SQL Server / Synapse / Fabric",
                  "duckdb": "DuckDB", "ansi": "ANSI SQL"}


def phys_type(logical: str, dialect: str) -> str:
    base, args = parse_type(logical)
    m = TYPE_MAP.get(dialect, TYPE_MAP["ansi"])
    if base == "string":
        return m["string"].format(n=args[0]) if args else m["string_"]
    if base == "decimal":
        p, s = (args + [18, 2])[:2] if args else (18, 2)
        return m["decimal"].format(p=p, s=s)
    return m[base]


def case(name: str, profile: dict | None) -> str:
    style = ((profile or {}).get("standards") or {}).get("naming_case", "lower_snake")
    return name.upper() if style == "upper_snake" else name.lower()


def table_prefix(entity: dict) -> str:
    return {"dimension": "dim_", "fact": "fct_", "reference": "ref_", "bridge": "brg_"}.get(entity.get("kind"), "")


def table_name(entity: dict, profile: dict | None) -> str:
    return case(table_prefix(entity) + entity["name"], profile)


def schema_name(profile: dict | None, layer_index: int = 2) -> str:
    p = profile or {}
    layers = (p.get("standards") or {}).get("layers") or ["raw", "conformed", "curated", "data_product"]
    v = p.get("variables") or {}
    layer = layers[min(layer_index, len(layers) - 1)]
    return case(f"{v.get('org_prefix', 'acme')}_{v.get('domain', 'core')}_{layer}", p)


def dialect_for(profile: dict | None) -> str:
    return stack_dialect(profile) if profile else "ansi"


def scd_columns(entity: dict) -> list[tuple[str, str]]:
    if entity.get("history") == "type2":
        return [(f"{entity['name']}_sk", "bigint"), ("valid_from", "timestamp"), ("valid_to", "timestamp"),
                ("is_current", "boolean")]
    return []


def audit_columns() -> list[tuple[str, str]]:
    return [("load_ts", "timestamp"), ("source_system", "string(64)"), ("batch_id", "string(64)")]
