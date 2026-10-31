"""Lectura de entregas del origen: esta API nunca escribe en la bandeja."""

import csv
import hashlib
import json
from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import Path

SOURCES = ("train", "stores", "holidays_events", "oil", "transactions")


class IntegrityError(ValueError):
    """Una entrega o su manifiesto no coincide con el contenido publicado."""


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_instant(value):
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("La fecha de disponibilidad/corte debe incluir zona horaria")
    return instant.astimezone(UTC)


def instant_text(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class DeliveryCatalog:
    """Catálogo de la carga inicial y la bandeja; no construye snapshots del producto."""

    def __init__(self, root, *, manifest_bytes=None):
        self.root = Path(root).resolve()
        self.manifest = json.loads(
            manifest_bytes
            if manifest_bytes is not None
            else (self.root / "manifest.json").read_bytes()
        )
        if self.manifest.get("schema_version") != 1:
            raise IntegrityError("Versión de manifiesto no soportada")
        self.records = self.manifest["deliveries"]
        seen = set()
        revisions = {}
        historical_at = parse_instant(self.manifest["historical_at"])
        for record in self.records:
            if record["source"] not in SOURCES or record["area"] not in {
                "historical",
                "source_inbox",
            }:
                raise IntegrityError("Fuente o área desconocida")
            if date.fromisoformat(record["reference_date"]).isoformat() != record["reference_date"]:
                raise IntegrityError("Fecha de referencia inválida")
            if type(record["revision"]) is not int or record["revision"] < 1:
                raise IntegrityError("Revisión inválida")
            if record["delivery_id"] in seen:
                raise IntegrityError("ID de entrega duplicado")
            seen.add(record["delivery_id"])
            available = parse_instant(record["available_at"])
            expected_area = "historical" if available <= historical_at else "source_inbox"
            if record["area"] != expected_area:
                raise IntegrityError("Área incompatible con el corte histórico")
            self._path(record["metadata_path"])
            self._path(record["payload_path"])
            key = record["source"], record["reference_date"]
            revisions.setdefault(key, []).append(record)
        for group in revisions.values():
            group.sort(key=lambda r: r["revision"])
            if [r["revision"] for r in group] != list(range(1, len(group) + 1)):
                raise IntegrityError("Secuencia de revisiones incompleta")
            for previous, current in pairwise(group):
                if parse_instant(current["available_at"]) <= parse_instant(
                    previous["available_at"]
                ):
                    raise IntegrityError("Corrección disponible antes de su versión anterior")
                if current["corrects"] != previous["delivery_id"]:
                    raise IntegrityError("Vínculo de corrección inválido")

    def _path(self, relative):
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise IntegrityError("Ruta de entrega insegura")
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise IntegrityError("Entrega fuera de la raíz del origen")
        return target

    def available(self, as_of, *, area=None, latest=False):
        """Filtra por conocimiento; una referencia futura planificada puede ser conocida."""
        cutoff = parse_instant(as_of)
        if area not in {None, "historical", "source_inbox"}:
            raise ValueError("Área inválida")
        records = [
            r
            for r in self.records
            if parse_instant(r["available_at"]) <= cutoff and (area is None or r["area"] == area)
        ]
        if latest:
            selected = {}
            for record in sorted(records, key=lambda r: r["revision"]):
                selected[record["source"], record["reference_date"]] = record
            records = list(selected.values())
        return [
            dict(r)
            for r in sorted(
                records,
                key=lambda r: (r["available_at"], r["source"], r["reference_date"], r["revision"]),
            )
        ]

    def _verify_delivery(self, record):
        metadata_path = self._path(record["metadata_path"])
        if checksum(metadata_path) != record["metadata_sha256"]:
            raise IntegrityError(f"Metadatos alterados: {record['delivery_id']}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected = {
            k: v for k, v in record.items() if k not in {"metadata_path", "metadata_sha256"}
        }
        if metadata != expected:
            raise IntegrityError("Metadatos distintos del catálogo")
        if checksum(self._path(record["payload_path"])) != record["payload_sha256"]:
            raise IntegrityError(f"CSV alterado: {record['delivery_id']}")

    def read(self, record, *, as_of):
        """Devuelve celdas sin imputación, verificando el recibo y su checksum."""
        if record not in self.records:
            raise IntegrityError("Entrega no registrada")
        if parse_instant(record["available_at"]) > parse_instant(as_of):
            raise IntegrityError("La entrega aún no estaba disponible al corte")
        self._verify_delivery(record)
        with self._path(record["payload_path"]).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, strict=True))
        if len(rows) != record["row_count"]:
            raise IntegrityError("Cantidad de filas incompatible")
        return rows

    def verify_delivery(self, record):
        """Audita una entrega seleccionada sin leer payloads futuros del catálogo."""
        if record not in self.records:
            raise IntegrityError("Entrega no registrada")
        self._verify_delivery(record)

    def verify(self):
        """Audita todo el origen sin modificar archivos ni crear marcas de consumo."""
        expected = {"manifest.json"}
        for record in self.records:
            self._verify_delivery(record)
            expected.update((record["payload_path"], record["metadata_path"]))
        actual = {p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()}
        if actual != expected:
            raise IntegrityError("Archivos extra o faltantes en la generación")
        return len(self.records)
