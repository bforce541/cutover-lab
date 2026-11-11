from __future__ import annotations

import csv
import hashlib
import json
import ssl
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import truststore

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "data/manifest.json").read_text())
BRAND = json.loads((ROOT / "brand.json").read_text())


@dataclass(frozen=True)
class TripFile:
    path: Path
    sha256: str
    start: str
    end: str
    fee_available: bool

    @property
    def table(self) -> str:
        return f"yellow_{self.start[:7].replace('-', '_')}_{self.sha256[:12]}"


def fingerprint(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def verify(path: Path, expected: str, *, name: str | None = None) -> str:
    try:
        actual = fingerprint(path)
    except FileNotFoundError:
        raise ValueError(f"Missing {path.name}. Run the download command.") from None
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {name or path.name}. Expected {expected}, got {actual}.")
    return actual


def download() -> None:
    directory = ROOT / "data/raw"
    directory.mkdir(parents=True, exist_ok=True)
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for item in [*MANIFEST["trips"], MANIFEST["zones"]]:
        destination = directory / item["filename"]
        if not destination.exists():
            with NamedTemporaryFile(dir=directory, delete=False) as file:
                temporary = Path(file.name)
                try:
                    with urlopen(item["url"], timeout=60, context=context) as response:
                        while chunk := response.read(1024 * 1024):
                            file.write(chunk)
                    file.flush()
                    verify(temporary, item["sha256"], name=item["filename"])
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
        print(verify(destination, item["sha256"]), destination.name)


class Inputs:
    def __init__(self, mode: str):
        self.mode = mode
        directory = ROOT / ("data/raw" if mode == "full" else "data/fixture")
        files = []
        for entry, fixture in zip(MANIFEST["trips"], ("dec.csv", "jan.csv"), strict=True):
            path = directory / (entry["filename"] if mode == "full" else fixture)
            digest = verify(path, entry["sha256"]) if mode == "full" else fingerprint(path)
            files.append(TripFile(path, digest, entry["start"], entry["end"], entry["fee_available"]))
        self.files = tuple(files)
        zone = MANIFEST["zones"]
        self.zones_path = directory / (zone["filename"] if mode == "full" else "zones.csv")
        self.zones_hash = verify(self.zones_path, zone["sha256"]) if mode == "full" else fingerprint(self.zones_path)
        with self.zones_path.open(newline="") as file:
            self.zones = {int(row["LocationID"]): row["Zone"] for row in csv.DictReader(file)}
        self.stamps = {item.path: self.stamp(item.path) for item in self.files}

    @staticmethod
    def stamp(path: Path) -> tuple[int, int, int, int]:
        info = path.stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    def check(self, items: tuple[TripFile, ...]) -> None:
        for item in items:
            if self.stamp(item.path) != self.stamps[item.path]:
                verify(item.path, item.sha256)

    def batch(self, name: str) -> tuple[TripFile, ...]:
        return self.files[:1] if name == "december" else self.files

    def identity(self, name: str) -> dict:
        items = self.batch(name)
        return {
            "name": name,
            "mode": self.mode,
            "as_of": items[-1].end,
            "inputs": [
                {"file": item.path.name, "sha256": item.sha256, "start": item.start,
                 "end": item.end, "fee_available": item.fee_available}
                for item in items
            ],
            "zone_lookup_sha256": self.zones_hash,
        }
