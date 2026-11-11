import logging
import os

from dotenv import load_dotenv

from .inputs import ROOT


def configure() -> None:
    load_dotenv(ROOT / ".env")
    # Some OS-managed networks require an OS-installed CA. This keeps chain and
    # hostname verification enabled while honoring the machine's trust roots.
    if os.getenv("REHEARSAL_SYSTEM_TRUST") == "1":
        import truststore

        truststore.inject_into_ssl()
    logging.getLogger("databricks").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
