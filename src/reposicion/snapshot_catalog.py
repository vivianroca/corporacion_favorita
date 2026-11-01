"""Adaptador de snapshots validados; nunca lee la bandeja ni CSV originales."""

import csv
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from reposicion.ingestion import _verify_bundle
from reposicion.source_io import IntegrityError, checksum, parse_instant


class SnapshotCatalog:
    def __init__(self, directory, contracts_path, origin, cutoff):
        self.root = Path(directory)
        self.manifest = _verify_bundle(self.root)
        self.digest = checksum(self.root / "manifest.json")
        if "validation_manifest_sha256" in self.manifest:
            validated = self.root.parent.parent / "validated" / self.root.name
            report = _verify_bundle(validated)
            if (
                checksum(validated / "manifest.json") != self.manifest["validation_manifest_sha256"]
                or report["plan_id"] != self.manifest["plan_id"]
            ):
                raise IntegrityError("Snapshot sin validación correspondiente")
        if self.manifest["contracts_sha256"] != checksum(contracts_path):
            raise IntegrityError("Contratos distintos a los validados")
        if parse_instant(self.manifest["as_of"]) > parse_instant(cutoff):
            raise ValueError("Snapshot posterior al corte: no se filtra un snapshot futuro")
        self.records = self.manifest.get("active_receipts", self.manifest.get("deliveries", []))
        if not self.records:
            raise ValueError("Snapshot sin recibos de trazabilidad")
        if any(
            parse_instant(r["available_at"]) > parse_instant(self.manifest["as_of"])
            for r in self.records
        ):
            raise IntegrityError("Recibo posterior al snapshot")
        self.origin, self.cutoff = origin, cutoff
        self.cache = {}
        days = {r["reference_date"] for r in self.records if r["source"] == "train"}
        required = {str(origin - timedelta(days=i)) for i in range(1, 29)}
        if not required <= days:
            raise ValueError("Snapshot incompleto: se requieren los 28 días previos")

    def available(self, as_of, *, latest=False):
        if parse_instant(as_of) != parse_instant(self.cutoff):
            raise ValueError("Este adaptador solo permite el corte fijado")
        return [
            dict(r)
            for r in self.records
            if parse_instant(r["available_at"]) <= parse_instant(as_of)
        ]

    def read(self, receipt, *, as_of):
        if parse_instant(as_of) < parse_instant(receipt["available_at"]):
            raise ValueError("Entrega no disponible")
        source = receipt["source"]
        if source not in self.cache:
            grouped = defaultdict(list)
            with (self.root / f"{source}.csv").open(newline="") as stream:
                for row in csv.DictReader(stream):
                    reference = row.get("date", receipt["reference_date"])
                    if source == "train" and not str(
                        self.origin - timedelta(days=28)
                    ) <= reference < str(self.origin):
                        continue
                    grouped[reference].append(row)
            self.cache[source] = grouped
        return self.cache[source].get(receipt["reference_date"], [])


def select_snapshot(work_root, cutoff, snapshot_id=None):
    root = Path(work_root)
    candidates = list((root / "snapshots").glob("*/manifest.json"))
    candidates += list((root / "automatic").glob("*/publications/*/manifest.json"))
    found = []
    for path in candidates:
        if snapshot_id and path.parent.name != snapshot_id:
            continue
        manifest = json.loads(path.read_text())
        if parse_instant(manifest["as_of"]) <= parse_instant(cutoff):
            found.append((parse_instant(manifest["as_of"]), path.parent.name, path.parent))
    if not found:
        raise ValueError("No existe snapshot validado disponible al corte solicitado")
    latest = max(t for t, _, _ in found)
    selected = [p for t, _, p in found if t == latest]
    if len(selected) != 1:
        raise ValueError("Snapshots ambiguos: indicar snapshot_id explícitamente")
    return selected[0]


def select_historical_snapshot(work_root, upper_bound, contracts_path, snapshot_id=None):
    """Manual sin corte: último snapshot con historia suficiente en su propio as-of."""
    from zoneinfo import ZoneInfo

    from reposicion.forecast_time import TIMEZONE

    if snapshot_id:
        return select_snapshot(work_root, upper_bound, snapshot_id)
    root = Path(work_root)
    paths = list((root / "snapshots").glob("*/manifest.json"))
    paths += list((root / "automatic").glob("*/publications/*/manifest.json"))
    compatible = []
    for path in paths:
        cutoff = json.loads(path.read_text())["as_of"]
        if parse_instant(cutoff) > parse_instant(upper_bound):
            continue
        origin = parse_instant(cutoff).astimezone(ZoneInfo(TIMEZONE)).date()
        try:
            SnapshotCatalog(path.parent, contracts_path, origin, cutoff)
        except IntegrityError:
            raise
        except ValueError:
            continue
        compatible.append((parse_instant(cutoff), path.parent))
    if not compatible:
        raise ValueError(
            "No hay snapshot histórico con 28 días de historia; indicar un corte y snapshot válidos"
        )
    latest = max(t for t, _ in compatible)
    chosen = [p for t, p in compatible if t == latest]
    if len(chosen) != 1:
        raise ValueError("Snapshots históricos ambiguos: indicar snapshot_id")
    return chosen[0]
