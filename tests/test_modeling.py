import copy

import pytest

from adpe.catalog.stacks import PRESETS, preset, validate
from adpe.engine.scenarios import SCENARIOS
from adpe.modeling import exports, importers
from adpe.modeling.logical import normalize, validate_model


def model_for(pack):
    sc = SCENARIOS[pack]
    return normalize({"name": sc["id"], "domain": pack, "entities": copy.deepcopy(sc["entities"]), "metrics": sc["metrics"]})


@pytest.mark.parametrize("pack", list(SCENARIOS))
def test_scenario_models_valid(pack):
    assert validate_model(model_for(pack)) == []


@pytest.mark.parametrize("profile", [p["profile_id"] for p in PRESETS])
def test_presets_validate(profile):
    assert validate(preset(profile))["ok"]


def test_incompatible_stack_is_blocking():
    p = preset("example-a")
    p["slots"]["transformation"] = {"tool": "spark-sql-pipelines"}
    v = validate(p)
    assert not v["ok"] and any("Incompatible" in b for b in v["blocking"])


@pytest.mark.parametrize("fmt", [e["id"] for e in exports.list_exporters()])
def test_every_exporter_renders(fmt):
    fn, content = exports.render(fmt, model_for("utilities"), {"profile": preset("example-a"), "dq_rules": SCENARIOS["utilities"]["dq"],
                                                               "mapping": [{"target_entity": "billed_consumption", "target_attribute": "bill_id",
                                                                            "source": "cis.bill.bill_id"}]})
    assert fn and content.strip()


@pytest.mark.parametrize("dialect", ["snowflake", "databricks", "bigquery", "redshift", "postgres", "tsql"])
def test_ddl_round_trip(dialect):
    m = model_for("retail")
    ddl = exports.render("ddl", m, {"profile": preset("example-a"), "dialect": dialect})[1]
    meta = importers.detect_and_parse("m.sql", ddl)
    assert meta["stats"]["tables"] == len(m["entities"])
    names = {c["name"].lower() for t in meta["tables"] for c in t["columns"]}
    assert {"order_line_id", "net_amount", "loyalty_tier"} <= names


def test_dbml_and_csv_import_to_logical_model():
    m = model_for("telco")
    for fmt, fn in (("dbml", "x.dbml"), ("dictionary", "x.csv")):
        meta = importers.detect_and_parse(fn, exports.render(fmt, m, {})[1])
        lm = importers.to_logical_model(meta)
        assert len(lm["entities"]) == 3
        assert validate_model(normalize(lm)) == []
