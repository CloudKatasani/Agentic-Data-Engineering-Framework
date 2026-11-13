# ADEF demo data packs

Synthetic, deterministic demo files for each Domain Pack. Regenerate with:

```bash
python -m adef demo-data --out demo-data
```

| Domain | Jira project | Reference stack | Folder |
|---|---|---|---|
| utilities | UTIL | Oracle → AWS S3 Iceberg → Snowflake | [`utilities/`](utilities/README.md) |
| telco | TEL | DB2 → Azure ADLS Delta → Databricks | [`telco/`](telco/README.md) |
| financial-services | FIN | DB2 → OneLake Delta → Microsoft Fabric | [`financial-services/`](financial-services/README.md) |
| retail | RET | DB2 → AWS S3 Iceberg → Redshift | [`retail/`](retail/README.md) |

Each pack has `jira/`, `source-metadata/`, `source-data/`, `model/`, `catalog/` and `lineage/` folders. `manifest.json` lists every file with its SHA-256.

No real people, customers or accounts: names come from fixed word lists, phone numbers use the fictional 555 range, emails use example.com, IDs are prefixed SYN- where sensitive.
