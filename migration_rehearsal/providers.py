from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Protocol

import duckdb

from .inputs import Inputs
from .query import literal, report_revision, report_sql


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    live: bool

    def read(self, batch: str, scenario: str = "clean") -> "Report": ...
    def smoke(self) -> int: ...


@dataclass
class Report:
    backend: str
    batch: dict
    revision: str
    rows: list[dict]
    live: bool
    binding: str


def identifier(value: str, pattern: str = r"[A-Za-z_][A-Za-z0-9_]*") -> str:
    if not re.fullmatch(pattern, value):
        raise ProviderError("Invalid cloud resource name. Check the local configuration.")
    return value


class SQLProvider:
    dialect = ""
    name = ""
    live = False

    def __init__(self, inputs: Inputs):
        self.inputs = inputs

    def relation(self, item):
        raise NotImplementedError

    def execute(self, statement: str) -> list[dict]:
        raise NotImplementedError

    def read(self, batch: str, scenario: str = "clean") -> Report:
        items = self.inputs.batch(batch)
        try:
            self.inputs.check(items)
            relations = [self.relation(item) for item in items]
            statement = report_sql(items, relations, self.dialect, scenario)
            raw_rows = self.execute(statement)
        except (OSError, ValueError, duckdb.Error):
            raise ProviderError("Could not read the verified local inputs. Check the data manifest and rerun download.") from None
        rows = []
        for raw in raw_rows:
            row = dict(raw)
            for field in ("month_start", "pickup_day"):
                row[field] = str(row[field]) if row[field] is not None else None
            row["fee_cents"] = row.pop("reported_cents")
            rows.append(row)
        binding = relations if self.live else [item.table for item in items]
        binding_id = hashlib.sha256("|".join(binding).encode()).hexdigest()
        return Report(self.name, self.inputs.identity(batch), report_revision(scenario), rows, self.live, binding_id)

    def smoke(self) -> int:
        return self.execute("SELECT 1 AS ok")[0]["ok"]


class DuckDB(SQLProvider):
    dialect = "duckdb"

    def __init__(self, inputs: Inputs, name: str):
        super().__init__(inputs)
        self.name = name

    def relation(self, item):
        path = literal(str(item.path))
        if item.path.suffix == ".parquet":
            return f"read_parquet({path})"
        columns = "{'tpep_pickup_datetime': 'TIMESTAMP', 'PULocationID': 'INTEGER'"
        if item.fee_available:
            columns += ", 'cbd_congestion_fee': 'DECIMAL(20, 2)'"
        return f"read_csv({path}, header=true, columns={columns}}})"

    def execute(self, statement: str) -> list[dict]:
        with duckdb.connect(":memory:", config={"threads": "4"}) as connection:
            cursor = connection.execute(statement)
            columns = [field[0] for field in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


class Databricks(SQLProvider):
    dialect = "databricks"
    name = "Databricks SQL"
    live = True

    @staticmethod
    def resource() -> tuple[str, str]:
        return (identifier(os.getenv("DATABRICKS_CATALOG", "workspace")),
                identifier(os.getenv("DATABRICKS_SCHEMA", "migration_rehearsal")))

    def table(self, item) -> str:
        catalog, schema = self.resource()
        return f"`{catalog}`.`{schema}`.`{item.table}`"

    def relation(self, item):
        version_var = "DATABRICKS_DELTA_VERSION_" + item.start[:7].replace("-", "_")
        version = os.getenv(version_var, "0")
        if not version.isascii() or not version.isdecimal():
            raise ProviderError("Delta table version must be a non-negative integer.")
        return f"{self.table(item)} VERSION AS OF {version}"

    def connect(self, **kwargs):
        host = os.getenv("DATABRICKS_SERVER_HOSTNAME")
        path = os.getenv("DATABRICKS_HTTP_PATH")
        if not host or not path:
            raise ProviderError("Set the Databricks SQL warehouse hostname and HTTP path, then run the connector smoke check.")
        from databricks import sql

        return sql.connect(
            server_hostname=host,
            http_path=path,
            auth_type="databricks-oauth",
            session_configuration={"TIMEZONE": "UTC", "STATEMENT_TIMEOUT": "45"},
            _socket_timeout=50,
            _retry_stop_after_attempts_count=2,
            _retry_stop_after_attempts_duration=50,
            **kwargs,
        )

    def execute(self, statement: str) -> list[dict]:
        try:
            with self.connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement)
                return [row.asDict() for row in cursor.fetchall()] if cursor.description else []
        except ProviderError:
            raise
        except ImportError:
            raise ProviderError("Install the cloud dependency group for Databricks SQL.") from None
        except Exception as error:
            raise cloud_error(error, self.name) from None


class BigQuery(SQLProvider):
    dialect = "bigquery"
    name = "BigQuery"
    live = True

    def resource(self) -> tuple[str, str]:
        project = os.getenv("BIGQUERY_PROJECT")
        if not project:
            raise ProviderError("Set BIGQUERY_PROJECT to your sandbox project and run the connector smoke check.")
        return identifier(project, r"[a-z][a-z0-9-]{4,28}[a-z0-9]"), identifier(
            os.getenv("BIGQUERY_DATASET", "migration_rehearsal")
        )

    def relation(self, item):
        project, dataset = self.resource()
        return f"`{project}.{dataset}.{item.table}`"

    def client(self):
        from google.cloud import bigquery

        project, _ = self.resource()
        return bigquery.Client(project=project, location=os.getenv("BIGQUERY_LOCATION", "US"))

    def execute(self, statement: str) -> list[dict]:
        try:
            from google.cloud import bigquery

            with self.client() as client:
                config = bigquery.QueryJobConfig(
                    use_query_cache=False, maximum_bytes_billed=536_870_912, job_timeout_ms=45000
                )
                job = client.query(statement, job_config=config, timeout=10)
                return [dict(row) for row in job.result(timeout=50, job_retry=None)]
        except ProviderError:
            raise
        except ImportError:
            raise ProviderError("Install the cloud dependency group for BigQuery.") from None
        except Exception as error:
            raise cloud_error(error, self.name) from None


def cloud_error(error: Exception, name: str) -> ProviderError:
    # Only classify vendor messages. They may contain identifiers or request details.
    message = f"{type(error).__name__} {error}".lower()
    if any(term in message for term in ("quota", "limit exceeded", "rate limit", "maximum bytes")):
        detail = "Check the sandbox or warehouse quota and retry after it resets."
    elif any(term in message for term in ("not found", "not_found", "does not exist", "table_or_view")):
        detail = "Check the dedicated schema, versioned tables and warehouse configuration."
    elif "certificate" in message or "ssl" in message:
        detail = "The TLS chain was rejected. Check your OS trust roots and local trust settings."
    elif any(term in message for term in ("credential", "auth", "access denied", "permission", "forbidden")):
        detail = "Refresh local browser authentication and check dataset or warehouse permissions."
    elif any(term in message for term in ("timeout", "timed out", "deadline")):
        detail = "The query timed out. Check warehouse startup or quota, then retry."
    else:
        detail = "Check the SQL warehouse and table schema with the smoke and setup commands."
    return ProviderError(f"{name} query failed. {detail}")
