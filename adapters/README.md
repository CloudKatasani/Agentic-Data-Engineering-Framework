# Adapters

Adapters are the only place tool-specific knowledge lives (contract:
`skills/adpe-stack-binding/references/adapter-contract.md`). Layout:
`adapters/<slot>/<tool>-<major-version>.md` plus `<tool>-<major-version>.conformance.md`.

Status in this release:

- The runtime ships **built-in generator templates** (`adpe/engine/codegen.py`) for dbt, Spark SQL
  pipelines, Dataform and portable SQL; Airflow, Databricks Workflows, ADF, Snowflake tasks and
  Dagster; GitHub Actions, GitLab CI, Azure Pipelines and Jenkins; Terraform schema resources.
- Stack validation reports these as warnings ("built-in template, adapter not yet reviewed") until a
  reviewed adapter file exists here. Backlog task E3-2: write and conformance-test the adapter for each
  bound slot of the launch stack before using the framework on client metadata.
- A tool with neither an adapter nor a template is a binding gap; agents do not improvise its syntax.
