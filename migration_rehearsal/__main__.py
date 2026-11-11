import argparse
from urllib.error import URLError

from .config import configure
from .inputs import Inputs, download
from .loaders import prepare_bigquery, prepare_databricks
from .providers import BigQuery, Databricks, ProviderError, cloud_error


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the migration rehearsal inputs and providers.")
    parser.add_argument("command", choices=("download", "smoke", "prepare"))
    parser.add_argument("target", nargs="?", choices=("databricks", "bigquery"))
    args = parser.parse_args()
    if args.command == "download":
        try:
            download()
        except (OSError, ValueError, URLError) as error:
            parser.exit(1, f"{error}\n")
        return
    if not args.target:
        parser.error("Choose databricks or bigquery.")
    configure()
    adapter, prepare = {
        "databricks": (Databricks, prepare_databricks),
        "bigquery": (BigQuery, prepare_bigquery),
    }[args.target]
    provider = adapter(Inputs("full" if args.command == "prepare" else "fixture"))
    try:
        if args.command == "smoke":
            print(f"{provider.name} SELECT 1 → {provider.smoke()}")
        else:
            prepare(provider)
    except ProviderError as error:
        parser.exit(1, f"{error}\n")
    except Exception as error:
        parser.exit(1, f"{cloud_error(error, provider.name)}\n")


if __name__ == "__main__":
    main()
