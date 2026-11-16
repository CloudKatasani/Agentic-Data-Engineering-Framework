"""Pipeline 1 for sources that are not a plain database extract.

A client's data does not only sit in a database that can be read over JDBC. This module generates
the ingest code for the other ways data arrives, all landing in the same bronze tables so pipelines
2 and 3 do not change:

    database-cdc    change events from a replication tool, folded into bronze with their operation
    files           CSV, JSON, Parquet, Avro or XML files, each loaded exactly once
    saas-api        application objects landed by a managed connector, or pulled from a REST API
    event-stream    topics read with Spark Structured Streaming, parsed against the declared schema

Every job keeps the bronze contract of the JDBC job: `_ingested_at`, `_batch_id`, `_source_system`,
rows that cannot be parsed go to a quarantine table instead of being dropped, and nothing secret is
in the code. Tool-specific syntax lives here (the adapter layer); nothing here runs in this
environment against a cloud.
"""
from __future__ import annotations

import json

from ..catalog.stacks import source_pattern, tool
from ..modeling import physical as ph
from ..util import dump_yaml

SPARK_TYPE = {"string": "string", "integer": "int", "bigint": "bigint", "boolean": "boolean", "date": "date",
              "timestamp": "timestamp", "timestamp_tz": "timestamp", "time": "string", "json": "string", "array": "string",
              "binary": "binary", "uuid": "string", "geography": "string"}


def spark_ddl(columns: list[dict]) -> str:
    """A Spark schema string for the declared columns (decimal keeps its precision)."""
    out = []
    for c in columns:
        base, args = ph.parse_type(c["type"])
        t = f"decimal({(args + [18, 2])[0]},{(args + [18, 2])[1]})" if base == "decimal" else SPARK_TYPE.get(base, "string")
        out.append(f"{c['name']} {t}")
    return ", ".join(out)


def _fill(template: str, **kw) -> str:
    for k, v in kw.items():
        template = template.replace(f"__{k.upper()}__", str(v))
    return template


def entry_point(profile: dict) -> str:
    """The file an orchestrator runs for pipeline 1 on this stack."""
    pattern, ing = source_pattern(profile), tool(profile, "ingestion")
    if ing == "adef-local-extract":
        return "pipelines/01_ingest/ingest_config.yaml"
    return {"database-batch": "pipelines/01_ingest/ingest_jdbc.py", "database-cdc": "pipelines/01_ingest/fold_landing.py",
            "files": "pipelines/01_ingest/ingest_files.py", "event-stream": "pipelines/01_ingest/ingest_stream.py",
            "saas-api": ("pipelines/01_ingest/ingest_api.py" if ing == "api-extract" else "pipelines/01_ingest/fold_landing.py"),
            }[pattern]


# ----------------------------------------------------------------------------- shared: fold landed files into bronze
FOLD = '''"""Pipeline 1 - fold landed __WHAT__ into bronze (__FMT__) - run __RUN__.

__TOOL__ writes files under the landing area. This job reads only the files it has not folded before
(recorded in the bronze file manifest), keeps the change operation of every row in `_op`
(I insert, U update, D delete), and appends to bronze. Re-running it changes nothing.
Runs on __LAKE__. No credentials are in this file: the job role reads the landing area.
"""
import argparse
import json
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession, functions as F

MANIFEST = "__CATALOG__.bronze._file_manifest"


def new_files(spark, path, fmt):
    files = spark.read.format("binaryFile").option("recursiveFileLookup", "true").load(path).select("path")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {MANIFEST} (path STRING, folded_at TIMESTAMP, batch_id STRING) USING __USING__")
    return [r["path"] for r in files.join(spark.table(MANIFEST), "path", "left_anti").collect()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    ap.add_argument("--batch-id", default=datetime.now(timezone.utc).strftime("B%Y%m%dT%H%M%S"))
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    spark = SparkSession.builder.appName("adef-fold-__RUN__").getOrCreate()
    report = []
    for t in cfg["tables"]:
        paths = new_files(spark, t["landing"], cfg["landing"]["format"])
        if not paths:
            report.append({"table": t["source"], "files": 0, "rows": 0})
            continue
        df = spark.read.format(cfg["landing"]["format"]).load(paths)
        df = df.toDF(*[c.lower() for c in df.columns])
        op = cfg["landing"]["operation_column"]
        df = df.withColumn("_op", F.upper(F.substring(F.coalesce(F.col(op), F.lit("I")), 1, 1)) if op in df.columns else F.lit("I"))
        df = (df.withColumn("_ingested_at", F.current_timestamp())
                .withColumn("_batch_id", F.lit(args.batch_id))
                .withColumn("_source_system", F.lit(cfg["source"]["type"])))
        df.write.format("__USING__").mode("append").option("mergeSchema", "true").saveAsTable(t["bronze"])
        (spark.createDataFrame([(p,) for p in paths], "path string")
              .withColumn("folded_at", F.current_timestamp()).withColumn("batch_id", F.lit(args.batch_id))
              .write.format("__USING__").mode("append").saveAsTable(MANIFEST))
        report.append({"table": t["source"], "files": len(paths), "rows": df.count()})
    print(json.dumps({"batch_id": args.batch_id, "tables": report}))


if __name__ == "__main__":
    main()
'''

# ----------------------------------------------------------------------------- files
FILES = '''"""Pipeline 1 - load files into bronze (__FMT__) - run __RUN__.

Each feed is a folder of __FORMATS__ files. A file is loaded exactly once (the bronze file manifest
records it), against the schema declared in `ingest_config.yaml`. A row that does not fit the schema
is written to the quarantine table with the file it came from, never dropped silently.
Runs on __LAKE__. No credentials are in this file: the job role reads the landing area.
"""
import argparse
import json
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession, functions as F

MANIFEST = "__CATALOG__.bronze._file_manifest"
QUARANTINE = "__CATALOG__.bronze._quarantine"


def read_feed(spark, feed, paths):
    reader = spark.read.format(feed["format"]).schema(feed["schema"] + ", _corrupt_record string")
    for key, value in (feed.get("options") or {}).items():
        reader = reader.option(key, value)
    if feed["format"] in ("csv", "json"):
        reader = reader.option("mode", "PERMISSIVE").option("columnNameOfCorruptRecord", "_corrupt_record")
    return reader.load(paths).withColumn("_source_file", F.input_file_name())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    ap.add_argument("--batch-id", default=datetime.now(timezone.utc).strftime("B%Y%m%dT%H%M%S"))
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    spark = SparkSession.builder.appName("adef-files-__RUN__").getOrCreate()
    spark.sql(f"CREATE TABLE IF NOT EXISTS {MANIFEST} (path STRING, folded_at TIMESTAMP, batch_id STRING) USING __USING__")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {QUARANTINE} (feed STRING, source_file STRING, record STRING, "
              f"batch_id STRING, quarantined_at TIMESTAMP) USING __USING__")
    report = []
    for feed in cfg["tables"]:
        listed = spark.read.format("binaryFile").option("recursiveFileLookup", "true").load(feed["landing"]).select("path")
        paths = [r["path"] for r in listed.join(spark.table(MANIFEST), "path", "left_anti").collect()]
        if not paths:
            report.append({"feed": feed["source"], "files": 0, "rows": 0, "quarantined": 0})
            continue
        df = read_feed(spark, feed, paths).cache()
        bad = df.filter(F.col("_corrupt_record").isNotNull())
        (bad.select(F.lit(feed["source"]).alias("feed"), F.col("_source_file").alias("source_file"),
                    F.col("_corrupt_record").alias("record"), F.lit(args.batch_id).alias("batch_id"),
                    F.current_timestamp().alias("quarantined_at"))
            .write.format("__USING__").mode("append").saveAsTable(QUARANTINE))
        good = (df.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")
                  .withColumn("_ingested_at", F.current_timestamp())
                  .withColumn("_batch_id", F.lit(args.batch_id))
                  .withColumn("_source_system", F.lit(cfg["source"]["type"])))
        good.write.format("__USING__").mode("append").option("mergeSchema", "true").saveAsTable(feed["bronze"])
        (spark.createDataFrame([(p,) for p in paths], "path string")
              .withColumn("folded_at", F.current_timestamp()).withColumn("batch_id", F.lit(args.batch_id))
              .write.format("__USING__").mode("append").saveAsTable(MANIFEST))
        report.append({"feed": feed["source"], "files": len(paths), "rows": good.count(), "quarantined": bad.count()})
    print(json.dumps({"batch_id": args.batch_id, "feeds": report}))


if __name__ == "__main__":
    main()
'''

AUTOLOADER = '''"""Pipeline 1 - load files into bronze (delta) with Auto Loader - run __RUN__.

Auto Loader tracks which files it has loaded in the checkpoint, so each file is loaded exactly once.
Data that does not fit the declared schema is kept in `_rescued_data` instead of being dropped.
`availableNow` makes this a batch job: it loads what has arrived and stops. Runs on Databricks.
"""
import argparse
import json

import yaml
from pyspark.sql import SparkSession, functions as F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    spark = SparkSession.builder.appName("adef-autoloader-__RUN__").getOrCreate()
    started = []
    for feed in cfg["tables"]:
        reader = (spark.readStream.format("cloudFiles")
                  .option("cloudFiles.format", feed["format"])
                  .option("cloudFiles.schemaLocation", f"{cfg['checkpoint_root']}/{feed['name']}/schema")
                  .option("cloudFiles.schemaEvolutionMode", "rescue")
                  .schema(feed["schema"]))
        for key, value in (feed.get("options") or {}).items():
            reader = reader.option(key, value)
        df = (reader.load(feed["landing"])
              .withColumn("_source_file", F.col("_metadata.file_path"))
              .withColumn("_ingested_at", F.current_timestamp())
              .withColumn("_batch_id", F.date_format(F.current_timestamp(), "'B'yyyyMMdd'T'HHmmss"))
              .withColumn("_source_system", F.lit(cfg["source"]["type"])))
        query = (df.writeStream.option("checkpointLocation", f"{cfg['checkpoint_root']}/{feed['name']}/checkpoint")
                 .option("mergeSchema", "true").trigger(availableNow=True).toTable(feed["bronze"]))
        started.append((feed["source"], query))
    for name, query in started:
        query.awaitTermination()
    print(json.dumps({"feeds": [name for name, _ in started]}))


if __name__ == "__main__":
    main()
'''

# ----------------------------------------------------------------------------- event streams
STREAM = '''"""Pipeline 1 - read __PLATFORM__ topics into bronze (__FMT__) - run __RUN__.

Each topic is parsed against the schema declared in `ingest_config.yaml`. A message that does not
parse is written to the quarantine table with its topic, partition and offset. The checkpoint gives
exactly-once delivery into bronze: after a failure the job resumes from the last committed offset.
`--once` processes what has arrived and stops (for a scheduled job); without it the job keeps running.
Runs on __LAKE__. The connection secret is resolved at run time and is never logged.
"""
import argparse

import yaml
from pyspark.sql import SparkSession, functions as F

QUARANTINE = "__CATALOG__.bronze._quarantine"


def source_options(cfg, topic, secret):
__OPTIONS__


def normalise(df, topic):
    """Give every platform's records the same columns: value, timestamp, topic, partition, offset."""
__NORMALISE__


def write_batch(feed, cfg):
    def write(batch, batch_id):
        parsed = batch.withColumn("r", F.from_json(F.col("value").cast("string"), feed["schema"]))
        bad = parsed.filter(F.col("r").isNull() & F.col("value").isNotNull())
        (bad.select(F.lit(feed["source"]).alias("feed"),
                    F.concat_ws(":", F.col("topic"), F.col("partition"), F.col("offset")).alias("source_file"),
                    F.col("value").cast("string").alias("record"), F.lit(str(batch_id)).alias("batch_id"),
                    F.current_timestamp().alias("quarantined_at"))
            .write.format("__USING__").mode("append").saveAsTable(QUARANTINE))
        (parsed.filter(F.col("r").isNotNull())
               .select("r.*", F.col("timestamp").alias("_event_time"), F.col("partition").alias("_partition"),
                       F.col("offset").alias("_offset"))
               .withColumn("_ingested_at", F.current_timestamp())
               .withColumn("_batch_id", F.lit(str(batch_id)))
               .withColumn("_source_system", F.lit(cfg["source"]["type"]))
               .write.format("__USING__").mode("append").option("mergeSchema", "true").saveAsTable(feed["bronze"]))
    return write


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    ap.add_argument("--connection-secret", required=True, help="secret name; resolved here, never logged")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    spark = SparkSession.builder.appName("adef-stream-__RUN__").getOrCreate()
    spark.sql(f"CREATE TABLE IF NOT EXISTS {QUARANTINE} (feed STRING, source_file STRING, record STRING, "
              f"batch_id STRING, quarantined_at TIMESTAMP) USING __USING__")
    secret = get_secret(args.connection_secret)
    queries = []
    for feed in cfg["tables"]:
        reader = spark.readStream.format(cfg["stream"]["format"])
        for key, value in source_options(cfg, feed["topic"], secret).items():
            reader = reader.option(key, value)
        writer = (normalise(reader.load(), feed["topic"]).writeStream.foreachBatch(write_batch(feed, cfg))
                  .option("checkpointLocation", f"{cfg['checkpoint_root']}/{feed['name']}"))
        writer = writer.trigger(availableNow=True) if args.once else writer.trigger(processingTime=cfg["stream"]["trigger"])
        queries.append(writer.start())
    for query in queries:
        query.awaitTermination()


def get_secret(name):
    """Resolve the stream connection secret from the platform secret store (adapter: secrets slot)."""
__SECRET__


if __name__ == "__main__":
    main()
'''

STREAM_OPTIONS = {
    "kafka": ("kafka", '''    return {"kafka.bootstrap.servers": cfg["stream"]["bootstrap_servers"], "subscribe": topic,
            "startingOffsets": "earliest", "failOnDataLoss": "true", "kafka.security.protocol": "SASL_SSL",
            "kafka.sasl.mechanism": "SCRAM-SHA-512", "kafka.sasl.jaas.config": secret}'''),
    "confluent-cloud": ("kafka", '''    return {"kafka.bootstrap.servers": cfg["stream"]["bootstrap_servers"], "subscribe": topic,
            "startingOffsets": "earliest", "failOnDataLoss": "true", "kafka.security.protocol": "SASL_SSL",
            "kafka.sasl.mechanism": "PLAIN", "kafka.sasl.jaas.config": secret}'''),
    "msk": ("kafka", '''    return {"kafka.bootstrap.servers": cfg["stream"]["bootstrap_servers"], "subscribe": topic,
            "startingOffsets": "earliest", "failOnDataLoss": "true", "kafka.security.protocol": "SASL_SSL",
            "kafka.sasl.mechanism": "AWS_MSK_IAM",   # the job role authenticates; `secret` is not used
            "kafka.sasl.jaas.config": "software.amazon.msk.auth.iam.IAMLoginModule required;",
            "kafka.sasl.client.callback.handler.class": "software.amazon.msk.auth.iam.IAMClientCallbackHandler"}'''),
    "event-hubs": ("kafka", '''    # Event Hubs speaks the Kafka protocol on port 9093; the secret is the JAAS line with the connection string
    return {"kafka.bootstrap.servers": cfg["stream"]["bootstrap_servers"], "subscribe": topic,
            "startingOffsets": "earliest", "failOnDataLoss": "true", "kafka.security.protocol": "SASL_SSL",
            "kafka.sasl.mechanism": "PLAIN", "kafka.sasl.jaas.config": secret}'''),
    "kinesis": ("kinesis", '''    # the job role authenticates; `secret` is not used
    return {"streamName": topic, "region": cfg["stream"]["region"], "initialPosition": "TRIM_HORIZON"}'''),
    "pubsub": ("pubsub", '''    # the job's service account authenticates; `secret` is not used
    return {"subscriptionId": topic, "topicId": topic, "projectId": cfg["stream"]["project"]}'''),
}
KAFKA_SHAPE = "    return df"
STREAM_NORMALISE = {
    "kinesis": '''    return df.select(F.col("data").alias("value"), F.col("approximateArrivalTimestamp").alias("timestamp"),
                     F.lit(topic).alias("topic"), F.col("shardId").alias("partition"),
                     F.col("sequenceNumber").alias("offset"))''',
    "pubsub": '''    return df.select(F.col("payload").alias("value"),
                     (F.col("publishTimestampInMillis") / 1000).cast("timestamp").alias("timestamp"),
                     F.lit(topic).alias("topic"), F.lit("0").alias("partition"), F.col("messageId").alias("offset"))''',
}

# ----------------------------------------------------------------------------- application APIs
API = '''"""Pipeline 1 - pull __SRC__ objects over its REST API into the landing area - run __RUN__.

For each object: page through the API from the last cursor value, write the pages as JSON lines to the
landing area, then store the new cursor. `fold_landing.py` folds the landed files into bronze.
The job backs off when the API throttles it (HTTP 429) and stops, without moving the cursor, on any
other error. The API token is resolved from the secret store at run time and is never logged.
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml


def call(url, token, attempt=0):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 429 and attempt < 6:
            time.sleep(min(int(error.headers.get("Retry-After", 2 ** attempt)), 120))
            return call(url, token, attempt + 1)
        raise


def pull(cfg, obj, token, landing, state):
    cursor = state.get(obj["name"])
    params = dict(obj.get("params") or {})
    if cursor:
        params[cfg["api"]["cursor_param"]] = cursor
    url = f"{cfg['api']['base_url']}{obj['path']}?{urllib.parse.urlencode(params)}"
    rows, pages = 0, 0
    out = landing / obj["name"] / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        while url:
            page = call(url, token)
            for record in page.get(cfg["api"]["records_key"], []):
                handle.write(json.dumps(record) + "\\n")
                rows += 1
                cursor = max(cursor or "", str(record.get(obj["cursor_field"], "")))
            pages += 1
            url = page.get(cfg["api"]["next_key"])
    if rows == 0:
        out.unlink()
    state[obj["name"]] = cursor
    return {"object": obj["name"], "rows": rows, "pages": pages, "cursor": cursor}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    ap.add_argument("--token-secret", required=True, help="secret name; resolved here, never logged")
    ap.add_argument("--landing", required=True, help="mounted landing folder for this source")
    ap.add_argument("--state", default="cursor_state.json")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    token = get_secret(args.token_secret)
    report = [pull(cfg, obj, token, Path(args.landing), state) for obj in cfg["objects"]]
    state_path.write_text(json.dumps(state, indent=2))
    print(json.dumps({"objects": report}))


def get_secret(name):
    """Resolve the API token from the platform secret store (adapter: secrets slot)."""
__SECRET__


if __name__ == "__main__":
    main()
'''

FILE_FORMATS = {"csv": {"header": "true", "multiLine": "true", "escape": '"'}, "json": {"multiLine": "false"},
                "parquet": {}, "avro": {}, "xml": {"rowTag": "row"}}


def generate(gen, tables: list[dict]) -> None:
    """Write pipeline 1 for a non-JDBC source pattern into `gen.files` (and note gaps in `gen.gaps`)."""
    pattern, ing, src = source_pattern(gen.p), gen.ing, gen.src
    using, landing_root = gen.using(), f"{gen.root}/landing/{src}"
    base = {"run_id": gen.run_id, "source": {"type": src, "pattern": pattern},
            "target": {"format": gen.fmt, "catalog": gen.catalog, "lake_root": gen.root, "layer": "bronze"}}
    common = dict(run=gen.run_id, fmt=gen.fmt, lake=gen.lake, catalog=gen.catalog, using=using)

    def feeds(extra=None):
        out = []
        for t in tables:
            name = t["bronze"].split(".")[-1]
            out.append({"name": name, "source": t["source"], "bronze": t["bronze"], "landing": f"{landing_root}/{name}/",
                        "primary_key": t["primary_key"], "watermark": t["watermark"], **(extra(t, name) if extra else {})})
        return out

    if pattern == "files":
        fmt = (gen.p.get("variables") or {}).get("file_format", "csv")
        cfg = {**base, "checkpoint_root": f"{gen.root}/_checkpoints/ingest",
               "tables": feeds(lambda t, n: {"format": fmt, "options": FILE_FORMATS.get(fmt, {}),
                                             "schema": spark_ddl(t["columns"]) or "value string"})}
        gen.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml(cfg)
        if ing == "auto-loader":
            gen.files["pipelines/01_ingest/ingest_files.py"] = _fill(AUTOLOADER, **common)
        else:
            gen.files["pipelines/01_ingest/ingest_files.py"] = _fill(FILES, formats="CSV, JSON, Parquet, Avro or XML", **common)
        gen.files["pipelines/01_ingest/README.md"] = (
            f"# Pipeline 1: files into bronze\n\nEach feed is a folder under `{landing_root}/`. Set `format` per feed in "
            "`ingest_config.yaml` to `csv`, `json`, `parquet`, `avro` or `xml`; the reader options for each are in the "
            "same file. The schema of each feed comes from the approved mapping: a file that does not fit it is "
            "quarantined, so a supplier's format change is seen on the first run, not found later in a report.\n")
        return

    if pattern == "event-stream":
        platform = tool(gen.p, "streaming")
        fmt_name, options = STREAM_OPTIONS.get(platform, STREAM_OPTIONS["kafka"])
        if platform not in STREAM_OPTIONS:
            gen.gaps.append(f"streaming `{platform}` has no template; the Kafka reader is generated as the fallback")
        stream = {"platform": platform, "format": fmt_name, "trigger": "1 minute",
                  **({"region": "${AWS_REGION}"} if platform == "kinesis" else {"project": "${GCP_PROJECT}"} if platform == "pubsub"
                     else {"bootstrap_servers": "${STREAM_BOOTSTRAP_SERVERS}"})}
        cfg = {**base, "stream": stream, "checkpoint_root": f"{gen.root}/_checkpoints/ingest",
               "tables": feeds(lambda t, n: {"topic": n.replace("__", "."), "schema": spark_ddl(t["columns"]) or "value string"})}
        gen.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml(cfg)
        gen.files["pipelines/01_ingest/ingest_stream.py"] = _fill(
            STREAM, platform=platform, options=options, normalise=STREAM_NORMALISE.get(platform, KAFKA_SHAPE),
            secret=gen._secret_snippet(), **common)
        gen.files["pipelines/01_ingest/README.md"] = (
            f"# Pipeline 1: {platform} topics into bronze\n\nOne topic per source object, parsed against the schema in "
            "`ingest_config.yaml`. Run with `--once` from the orchestrator for micro-batches, or without it as a "
            "long-running job. Messages that do not parse go to the quarantine table with their offset.\n")
        if ing == "debezium-kafka":
            _debezium(gen, tables)
        return

    # database-cdc and saas-api: a tool lands files; one job folds them into bronze
    landed = {"aws-dms": ("parquet", "op", "landing/dms"), "gcp-datastream": ("avro", "source_metadata.change_type", "landing/datastream"),
              "debezium-kafka": ("json", "op", f"landing/{src}"), "fivetran": ("parquet", "_fivetran_deleted", f"landing/{src}"),
              "airbyte": ("parquet", "_ab_cdc_deleted_at", f"landing/{src}"), "api-extract": ("json", "_op", f"landing/{src}"),
              }.get(ing, ("parquet", "op", f"landing/{src}"))
    cfg = {**base, "landing": {"format": landed[0], "operation_column": landed[1], "written_by": ing},
           "tables": [{**f, "landing": f"{gen.root}/{landed[2]}/{f['name']}/"} for f in feeds()]}
    what = "change events" if pattern == "database-cdc" else "application objects"
    gen.files["pipelines/01_ingest/fold_landing.py"] = _fill(FOLD, what=what, tool=ing, **common)
    if ing == "fivetran":
        gen.files["pipelines/01_ingest/fivetran/connector.json"] = json.dumps({
            "service": src.replace("-", "_"), "group_id": "${FIVETRAN_DESTINATION_GROUP}", "paused": True,
            "sync_frequency": 60, "schedule_type": "auto", "run_setup_tests": True,
            "config": {"schema": f"landing_{src.replace('-', '_')}",
                       "update_method": "TELEPORT" if pattern == "database-cdc" else None,
                       "auth": "resolved by Fivetran from its own vault; set in the Fivetran console, never here"},
            "schema_selection": [{"table": t["source"].split(".")[-1], "enabled": True, "sync_mode": "SOFT_DELETE"} for t in tables],
            "destination": {"service": "managed_data_lake", "table_format": gen.fmt.upper(),
                            "prefix_path": f"landing/{src}"}}, indent=2)
    elif ing == "airbyte":
        gen.files["pipelines/01_ingest/airbyte/connection.yaml"] = dump_yaml({
            "name": f"{src}-to-landing-{gen.run_id.lower()}", "status": "inactive",
            "schedule": {"scheduleType": "cron", "cronExpression": "0 0 * * * ?"},
            "source": {"definition": src, "credentials": "set in Airbyte's secret store, never in this file"},
            "destination": {"definition": {"s3": "s3", "adls": "azure-blob-storage", "gcs": "gcs"}.get(
                tool(gen.p, "object_storage"), "s3"), "format": "parquet", "path": f"landing/{src}"},
            "streams": [{"name": t["source"].split(".")[-1], "syncMode": "incremental_append",
                         "cursorField": [t["watermark"]], "primaryKey": [[k] for k in t["primary_key"]]} for t in tables]})
    elif ing == "debezium-kafka":
        _debezium(gen, tables)
    elif ing == "api-extract":
        cfg["api"] = {"base_url": "${SOURCE_API_BASE_URL}", "records_key": "records", "next_key": "next_page_url",
                      "cursor_param": "modified_since"}
        cfg["objects"] = [{"name": f["name"], "path": f"/{f['source'].split('.')[-1].lower()}",
                           "cursor_field": f["watermark"], "params": {"page_size": 500}} for f in feeds()]
        gen.files["pipelines/01_ingest/ingest_api.py"] = _fill(API, src=src, run=gen.run_id, secret=gen._secret_snippet())
    gen.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml(cfg)


def _debezium(gen, tables: list[dict]) -> None:
    connector = {"oracle": "io.debezium.connector.oracle.OracleConnector", "db2": "io.debezium.connector.db2.Db2Connector",
                 "sqlserver": "io.debezium.connector.sqlserver.SqlServerConnector",
                 "postgres": "io.debezium.connector.postgresql.PostgresConnector",
                 "mysql": "io.debezium.connector.mysql.MySqlConnector",
                 "mongodb": "io.debezium.connector.mongodb.MongoDbConnector"}.get(gen.src)
    if not connector:
        gen.gaps.append(f"Debezium has no connector for `{gen.src}`; the connector class is left to fill in")
    gen.files["pipelines/01_ingest/debezium/connector.json"] = json.dumps({
        "name": f"adef-{gen.run_id.lower()}-{gen.src}",
        "config": {"connector.class": connector or "<connector class>", "tasks.max": "1",
                   "database.hostname": "${SOURCE_HOST}", "database.user": "${file:/opt/secrets/source.properties:user}",
                   "database.password": "${file:/opt/secrets/source.properties:password}",
                   "topic.prefix": gen.src, "table.include.list": ",".join(t["source"] for t in tables),
                   "snapshot.mode": "initial", "tombstones.on.delete": "false",
                   "transforms": "unwrap", "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
                   "transforms.unwrap.add.fields": "op,source.ts_ms", "transforms.unwrap.delete.handling.mode": "rewrite",
                   "key.converter": "org.apache.kafka.connect.json.JsonConverter",
                   "value.converter": "org.apache.kafka.connect.json.JsonConverter",
                   "value.converter.schemas.enable": "false"}}, indent=2)
