"""Logical -> physical naming and types per Stack Profile (stack-binding task T3)."""
from __future__ import annotations

from ..catalog.stacks import dialect as stack_dialect
from .logical import parse_type

_BASE = {
    "snowflake": {"string": "VARCHAR({n})", "string_": "VARCHAR", "integer": "NUMBER(38,0)", "bigint": "NUMBER(38,0)",
                  "decimal": "NUMBER({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP_NTZ"},
    "databricks": {"string": "STRING", "string_": "STRING", "integer": "INT", "bigint": "BIGINT",
                   "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "bigquery": {"string": "STRING", "string_": "STRING", "integer": "INT64", "bigint": "INT64",
                 "decimal": "NUMERIC({p},{s})", "boolean": "BOOL", "date": "DATE", "timestamp": "TIMESTAMP"},
    "redshift": {"string": "VARCHAR({n})", "string_": "VARCHAR(256)", "integer": "INTEGER", "bigint": "BIGINT",
                 "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP"},
    "trino": {"string": "VARCHAR({n})", "string_": "VARCHAR", "integer": "INTEGER", "bigint": "BIGINT",
              "decimal": "DECIMAL({p},{s})", "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP(6)"},
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
# Types beyond flat relational data. Where an engine has no native type, the value is kept as text
# (JSON text, WKT for location) so nothing is lost; the design notes say so.
#               timestamp_tz                 time       json             array             binary           uuid                geography
_EXTENDED = {
    "snowflake": ("TIMESTAMP_TZ",             "TIME",    "VARIANT",       "ARRAY",          "BINARY",        "VARCHAR(36)",      "GEOGRAPHY"),
    "databricks": ("TIMESTAMP",               "STRING",  "VARIANT",       "ARRAY<STRING>",  "BINARY",        "STRING",           "STRING"),
    "bigquery": ("TIMESTAMP",                 "TIME",    "JSON",          "ARRAY<STRING>",  "BYTES",         "STRING",           "GEOGRAPHY"),
    "redshift": ("TIMESTAMPTZ",               "TIME",    "SUPER",         "SUPER",          "VARBYTE",       "VARCHAR(36)",      "GEOGRAPHY"),
    "trino": ("TIMESTAMP(6) WITH TIME ZONE",  "TIME(6)", "VARCHAR",       "ARRAY(VARCHAR)", "VARBINARY",     "UUID",             "VARCHAR"),
    "postgres": ("TIMESTAMPTZ",               "TIME",    "JSONB",         "JSONB",          "BYTEA",         "UUID",             "TEXT"),
    "tsql": ("DATETIMEOFFSET(6)",             "TIME(6)", "NVARCHAR(MAX)", "NVARCHAR(MAX)",  "VARBINARY(MAX)", "UNIQUEIDENTIFIER", "NVARCHAR(MAX)"),
    "ansi": ("TIMESTAMP WITH TIME ZONE",      "TIME",    "VARCHAR(4000)", "VARCHAR(4000)",  "VARBINARY(4000)", "CHAR(36)",        "VARCHAR(4000)"),
    "duckdb": ("TIMESTAMPTZ",                 "TIME",    "JSON",          "VARCHAR[]",      "BLOB",          "UUID",             "VARCHAR"),
    "oracle": ("TIMESTAMP WITH TIME ZONE",    "VARCHAR2(18)", "CLOB",     "CLOB",           "BLOB",          "VARCHAR2(36)",     "CLOB"),
    "db2": ("TIMESTAMP",                      "TIME",    "CLOB",          "CLOB",           "BLOB",          "CHAR(36)",         "CLOB"),
    "sqlite": ("TEXT",                        "TEXT",    "TEXT",          "TEXT",           "BLOB",          "TEXT",             "TEXT"),
}
_EXT_NAMES = ("timestamp_tz", "time", "json", "array", "binary", "uuid", "geography")
TYPE_MAP = {d: {**m, **dict(zip(_EXT_NAMES, _EXTENDED[d]))} for d, m in _BASE.items()}
# Kept as text on this dialect (no native type): the physical design must say how it is validated.
KEPT_AS_TEXT = {d: [n for n, t in zip(_EXT_NAMES, _EXTENDED[d])
                    if n in ("json", "array", "geography", "time") and t.split("(")[0] in
                    ("STRING", "VARCHAR", "VARCHAR2", "NVARCHAR", "TEXT", "CLOB")] for d in _BASE}
DIALECT_LABELS = {"snowflake": "Snowflake", "databricks": "Databricks (Delta)", "bigquery": "BigQuery",
                  "redshift": "Redshift", "trino": "Trino / Athena / Starburst", "postgres": "PostgreSQL",
                  "tsql": "SQL Server / Synapse / Fabric",
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
