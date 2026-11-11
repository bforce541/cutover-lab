from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .providers import BigQuery, Databricks, ProviderError, cloud_error
from .query import literal


def prepare_databricks(provider: Databricks) -> None:
    catalog, schema = provider.resource()
    directory = f"`{catalog}`.`{schema}`"
    provider.inputs.check(provider.inputs.files)
    stage = provider.inputs.files[0].path.parent
    try:
        with provider.connect(staging_allowed_local_path=str(stage)) as connection, connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {directory}")
            cursor.execute(f"CREATE VOLUME IF NOT EXISTS {directory}.`tlc_inputs`")
            cursor.execute(f"SHOW TABLES IN {directory}")
            existing = {row.asDict()["tableName"] for row in cursor.fetchall()}
            for item in provider.inputs.files:
                if item.table in existing:
                    print(f"Reusing {item.table}; verification still required.", flush=True)
                    continue
                file = f"/Volumes/{catalog}/{schema}/tlc_inputs/{item.sha256[:12]}_{item.path.name}"
                print(f"Staging {item.path.name}.", flush=True)
                cursor.execute(f"PUT {literal(str(item.path))} INTO {literal(file)} OVERWRITE")
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {provider.table(item)} USING DELTA "
                               f"AS SELECT * FROM parquet.`{file}`")
                print(f"Created managed Delta table {item.table}.", flush=True)
    except ProviderError:
        raise
    except Exception as error:
        raise cloud_error(error, provider.name) from None


def prepare_bigquery(provider: BigQuery) -> None:
    import google.auth
    from google.api_core.exceptions import NotFound
    from google.auth.transport.requests import AuthorizedSession
    from google.cloud import bigquery

    project, dataset_id = provider.resource()
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    with AuthorizedSession(credentials) as session:
        response = session.get(f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo", timeout=10)
        if not response.ok or response.json().get("billingEnabled") is not False:
            raise ProviderError("Could not verify billing is disabled. Choose a BigQuery Sandbox project.")
    provider.inputs.check(provider.inputs.files)
    with provider.client() as client:
        dataset = bigquery.Dataset(f"{project}.{dataset_id}")
        dataset.location = client.location
        dataset.default_table_expiration_ms = 60 * 24 * 60 * 60 * 1000
        client.create_dataset(dataset, exists_ok=True, timeout=20)
        for item in provider.inputs.files:
            resource = f"{project}.{dataset_id}.{item.table}"
            try:
                table = client.get_table(resource, timeout=20)
            except NotFound:
                table = None
            if table:
                print(f"Reusing {item.table}; verification still required.", flush=True)
                continue
            config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.PARQUET,
                write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,
            )
            print(f"Batch loading {item.path.name}.", flush=True)
            with item.path.open("rb") as file:
                job = client.load_table_from_file(file, resource, job_config=config, timeout=120)
                job.result(timeout=180)
            table = client.get_table(resource)
            table.description = f"Original TLC Parquet {item.path.name}. SHA-256 {item.sha256}."
            table.expires = datetime.now(timezone.utc) + timedelta(days=60)
            client.update_table(table, ["description", "expires"])
            timestamp = next(field.field_type for field in table.schema if field.name.lower() == "tpep_pickup_datetime")
            print(f"Loaded {item.table}: {table.num_rows:,} raw rows, pickup type {timestamp}.", flush=True)
