"""Production-grade synthetic data kit: complete, consistent, reproducible and downloadable."""
import csv
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from adef import synthetic_kit
from adef.api.app import app
from adef.engine.scenarios import SCENARIOS


def _kit(pack, scale="small"):
    buf = io.BytesIO()
    manifest = synthetic_kit.build(pack, scale, buf)
    z = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    root = manifest["kit"]
    read = lambda p: list(csv.DictReader(io.StringIO(z.read(f"{root}/{p}").decode())))  # noqa: E731
    return manifest, z, root, read


@pytest.mark.parametrize("pack", sorted(SCENARIOS))
def test_kit_is_complete_and_self_consistent(pack):
    manifest, z, root, read = _kit(pack)
    names = {n.split("/", 1)[1] for n in z.namelist()}
    for needed in ("README.md", "manifest.json", "01-source-data/data-quality/seeded-defects.csv",
                   "02-source-database/oracle/01-ddl.sql", "02-source-database/db2/02-load.sql",
                   "03-requirements/jira-export.csv", "05-metadata/source-catalog.csv",
                   "06-expected-results/control-totals.csv", "07-enterprise-setup/approvers.csv"):
        assert needed in names, needed
    assert any(n.startswith("04-context/confluence/") for n in names) and any(n.startswith("04-context/servicenow/") for n in names)
    assert any(n.startswith("01-source-data/incremental/day-03/") for n in names)
    # manifest row counts and hashes match the files
    import hashlib
    for f in manifest["files"]:
        data = z.read(f"{root}/{f['path']}")
        assert hashlib.sha256(data).hexdigest() == f["sha256"] and len(data) == f["bytes"]
    totals = {(r["table"], r["column"], r["measure"]): r["value"] for r in read("06-expected-results/control-totals.csv")}
    for table, n in manifest["tables"].items():
        rows = read(f"01-source-data/full-load/{table.replace('.', '__')}.csv")
        assert len(rows) == n == int(totals[(table, "*", "row_count")])
        assert f"02-source-database/oracle/ctl/{table.replace('.', '__')}.ctl" in names
    # every planted defect is really in the data
    data = {t: {} for t in manifest["tables"]}
    for d in read("01-source-data/data-quality/seeded-defects.csv"):
        rows = data[d["table"]] or data[d["table"]].update(
            {i: r for i, r in enumerate(read(f"01-source-data/full-load/{d['table'].replace('.', '__')}.csv"))}) or data[d["table"]]
        hits = [r for r in rows.values() if d["key"].split("|")[0] in r.values()]
        assert hits, d
        value = [r[d["column"]] for r in hits]
        if d["defect"] == "missing_value":
            assert "" in value
        elif d["defect"] == "negative_amount":
            assert any(v.startswith("-") for v in value)
        elif d["defect"] == "orphan_reference":
            assert any(v.endswith("999999") for v in value)
    assert manifest["seeded_defects"] >= 3
    assert len(read("07-enterprise-setup/approvers.csv")) == 7


def test_kit_is_reproducible_and_scales():
    a, b = io.BytesIO(), io.BytesIO()
    m1, m2 = synthetic_kit.build("telco", "small", a), synthetic_kit.build("telco", "small", b)
    assert [f["sha256"] for f in m1["files"]] == [f["sha256"] for f in m2["files"]]
    est = synthetic_kit.estimate("telco", "small")
    assert est == m1["tables"]
    medium = synthetic_kit.estimate("telco", "medium")
    assert medium["crm.subscriber"] == synthetic_kit.SCALES["medium"] * est["crm.subscriber"] and medium["bss.product_catalog"] == est["bss.product_catalog"]
    with pytest.raises(ValueError):
        synthetic_kit.build("telco", "huge", io.BytesIO())


def test_incremental_batches_are_newer_and_include_duplicate_deliveries():
    manifest, z, root, read = _kit("telco")
    full = {r["subscriber_id"]: r for r in read("01-source-data/full-load/crm__subscriber.csv")}
    day2 = read("01-source-data/incremental/day-02/crm__subscriber.csv")
    mix = next(r for r in read("06-expected-results/incremental-batches.csv") if r["batch"] == "day-02" and r["table"] == "crm.subscriber")
    assert len(day2) == int(mix["rows"]) == int(mix["updated"]) + int(mix["new"]) + int(mix["delivered_twice"])
    newer = [r for r in day2 if r["last_updated_ts"] >= "2026-09-02"]
    assert len(newer) == int(mix["updated"]) + int(mix["new"])
    assert sum(1 for r in day2 if r["subscriber_id"] not in full) == int(mix["new"])


def test_kit_download_endpoint():
    c = TestClient(app)
    opts = c.get("/api/synthetic-kit/options").json()
    assert set(opts["scales"]) == {"small", "medium", "large"} and opts["scales"]["large"]["rows"]["telco"] > 100000
    r = c.get("/api/synthetic-kit?domain=retail&scale=small")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "datacrew-synthetic-kit-retail-small.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert json.loads(z.read("datacrew-synthetic-kit-retail-small/manifest.json"))["domain"] == "retail"
    assert c.get("/api/synthetic-kit?domain=nope").status_code == 400
