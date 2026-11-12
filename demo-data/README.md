# ADEF demo data packs

Synthetic, deterministic demo files for each Domain Pack. Regenerate with:

```bash
python -m adef demo-data --out demo-data
```

| Domain | Jira project | Reference stack | Folder |
|---|---|---|---|
| utilities | UTIL | AWS + Snowflake + dbt + Airflow | [`utilities/`](utilities/README.md) |
| telco | TEL | Azure + Databricks Lakehouse | [`telco/`](telco/README.md) |
| financial-services | FIN | Microsoft Fabric + Purview + Power BI | [`financial-services/`](financial-services/README.md) |
| retail | RET | AWS + Redshift + Glue + Tableau | [`retail/`](retail/README.md) |

Each pack has `jira/`, `source-metadata/`, `source-data/`, `model/`, `catalog/` and `lineage/` folders. `manifest.json` lists every file with its SHA-256.

No real people, customers or accounts: names come from fixed word lists, phone numbers use the fictional 555 range, emails use example.com, IDs are prefixed SYN- where sensitive.
