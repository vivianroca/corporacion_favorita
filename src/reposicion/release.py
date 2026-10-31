"""Publicador externo: libera copias de entregas existentes, nunca las regenera."""

import fcntl
import hashlib
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from reposicion.ingestion import _immutable_bytes
from reposicion.source_io import (
    DeliveryCatalog,
    IntegrityError,
    canonical_bytes,
    checksum,
    instant_text,
)


@contextmanager
def _lock(inbox):
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with (inbox.parent / f".{inbox.name}.publisher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _publish_catalog(inbox, document):
    content = canonical_bytes(document)
    digest = hashlib.sha256(content).hexdigest()
    _immutable_bytes(inbox / "catalogs" / f"{digest}.json", content)
    descriptor, temporary = tempfile.mkstemp(prefix=".catalog-", dir=inbox)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, inbox / "manifest.json")
    finally:
        Path(temporary).unlink(missing_ok=True)


def initialize(master_root, inbox_root, stream_name="lab1-live-v1"):
    master, inbox = Path(master_root).resolve(), Path(inbox_root).resolve()
    if master.is_relative_to(inbox) or inbox.is_relative_to(master):
        raise ValueError("La bandeja y la simulación maestra no pueden solaparse")
    parent_hash = checksum(master / "manifest.json")
    parent = DeliveryCatalog(master)
    stream_id = hashlib.sha256(
        canonical_bytes(
            {
                "parent_manifest_sha256": parent_hash,
                "name": stream_name,
            }
        )
    ).hexdigest()
    with _lock(inbox):
        if (inbox / "manifest.json").exists():
            existing = DeliveryCatalog(inbox).manifest
            if existing.get("operational_stream") != stream_id:
                raise IntegrityError("La bandeja existente pertenece a otro stream; usar otra ruta")
            return {"stream_id": stream_id, "released_deliveries": len(existing["deliveries"])}
        if inbox.exists() and any(inbox.iterdir()):
            raise IntegrityError("No se inicializa sobre un directorio con archivos existentes")
        inbox.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 1,
            "generation_id": parent.manifest["generation_id"],
            "historical_at": parent.manifest["historical_at"],
            "parent_manifest_sha256": parent_hash,
            "operational_stream": stream_id,
            "stream_name": stream_name,
            "deliveries": [],
            "release_events": [],
        }
        _publish_catalog(inbox, document)
    return {"stream_id": stream_id, "released_deliveries": 0}


def publish_next(master_root, inbox_root, count=1, delivery_ids=None):
    if type(count) is not int or count < 1:
        raise ValueError("count debe ser un entero positivo")
    master, inbox = Path(master_root).resolve(), Path(inbox_root).resolve()
    if master.is_relative_to(inbox) or inbox.is_relative_to(master):
        raise ValueError("La bandeja y la simulación maestra no pueden solaparse")
    with _lock(inbox):
        current = DeliveryCatalog(inbox).manifest
        if checksum(master / "manifest.json") != current["parent_manifest_sha256"]:
            raise IntegrityError("La simulación maestra cambió; no se mezcla otra generación")
        catalog = DeliveryCatalog(master)
        released = {r["delivery_id"] for r in current["deliveries"]}
        candidates = sorted(
            catalog.records,
            key=lambda r: (
                r["source"] != "stores",
                r["available_at"],
                r["source"],
                r["reference_date"],
                r["revision"],
            ),
        )
        if delivery_ids:
            requested = set(delivery_ids)
            known = {r["delivery_id"] for r in candidates}
            if not requested <= known:
                raise ValueError(f"Entregas desconocidas: {sorted(requested - known)}")
            chosen = [r for r in candidates if r["delivery_id"] in requested - released]
        else:
            chosen = [r for r in candidates if r["delivery_id"] not in released][:count]
        if not chosen:
            return {"published": [], "stream_id": current["operational_stream"]}
        selected_ids = {r["delivery_id"] for r in chosen}
        stores_known = any(r["source"] == "stores" for r in [*current["deliveries"], *chosen])
        for record in chosen:
            if record["revision"] > 1 and record["corrects"] not in released | selected_ids:
                raise IntegrityError("Publicar primero la revisión anterior")
            if record["source"] != "stores" and not stores_known:
                raise IntegrityError("Publicar primero el snapshot de tiendas")
            catalog.verify_delivery(record)
        # Primero archivos inmutables, después el catálogo visible por renombrado atómico.
        for record in chosen:
            for field, digest in (
                ("payload_path", "payload_sha256"),
                ("metadata_path", "metadata_sha256"),
            ):
                content = catalog._path(record[field]).read_bytes()
                if hashlib.sha256(content).hexdigest() != record[digest]:
                    raise IntegrityError("La entrega cambió durante la liberación")
                _immutable_bytes(inbox / record[field], content)
        current["deliveries"] = sorted(
            [*current["deliveries"], *chosen],
            key=lambda r: (r["available_at"], r["source"], r["reference_date"], r["revision"]),
        )
        current["release_events"].append(
            {
                "sequence": len(current["release_events"]) + 1,
                "released_at": instant_text(datetime.now(UTC)),
                "delivery_ids": [r["delivery_id"] for r in chosen],
            }
        )
        _publish_catalog(inbox, current)
    return {
        "published": [r["delivery_id"] for r in chosen],
        "stream_id": current["operational_stream"],
    }
