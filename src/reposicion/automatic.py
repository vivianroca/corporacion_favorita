"""Consumo incremental con ledger SQLite y publicación recuperable; sin Airflow."""

import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import yaml

from reposicion.contracts import Contracts, validate_relation
from reposicion.ingestion import (
    PipelineError,
    _identity,
    _immutable_bytes,
    _verify_bundle,
)
from reposicion.source_io import (
    SOURCES,
    DeliveryCatalog,
    IntegrityError,
    canonical_bytes,
    checksum,
    instant_text,
    parse_instant,
)


def settings(path=None):
    from reposicion.ingestion import settings as pipeline_settings

    config_path = path or os.environ.get("LAB1_PIPELINE_CONFIG", "configs/pipeline.yaml")
    config = yaml.safe_load(Path(config_path).read_text())
    common = pipeline_settings(config_path)
    return {
        "inbox_root": os.environ.get("LAB1_OPERATIONAL_INBOX", config["operational_inbox"]),
        "work_root": common["work_root"],
        "contracts_path": common["contracts_path"],
    }


def _code_hash():
    base = Path(__file__).parent
    return _identity(
        {
            n: checksum(base / n)
            for n in ("automatic.py", "contracts.py", "ingestion.py", "source_io.py")
        }
    )


def _open_ledger(root, stream_id, contract_hash, contracts):
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "control.sqlite", timeout=60)
    connection.execute("PRAGMA busy_timeout=60000")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS cycles (
            cycle_id TEXT PRIMARY KEY, as_of TEXT, catalog BLOB, code_hash TEXT, result TEXT
        );
        CREATE TABLE IF NOT EXISTS processed (
            delivery_id TEXT PRIMARY KEY, source TEXT, reference_date TEXT, revision INTEGER,
            payload_sha256 TEXT, metadata_sha256 TEXT, receipt_json TEXT, processed_at TEXT,
            UNIQUE(source,reference_date,revision)
        );
        CREATE TABLE IF NOT EXISTS active (
            source TEXT, reference_date TEXT, revision INTEGER, receipt_json TEXT,
            PRIMARY KEY(source,reference_date)
        );
        CREATE TABLE IF NOT EXISTS publications (id TEXT PRIMARY KEY, status TEXT, manifest_sha256 TEXT);
    """)
    for key, value in (("stream_id", stream_id), ("contracts_sha256", contract_hash)):
        connection.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (key, value))
        if connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0] != value:
            connection.close()
            raise IntegrityError(
                "Stream o contrato incompatible con el ledger; requiere migración explícita"
            )
    for source in SOURCES:
        keys = ",".join(f"key_{i} TEXT UNIQUE" for i in range(len(contracts.keys(source))))
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS rows_{source} (partition_key TEXT, record TEXT,{keys})"
        )
    connection.commit()
    return connection


def _finalize(connection, root):
    """Recupera el caso COMMIT realizado pero publicación todavía no visible."""
    connection.execute("BEGIN IMMEDIATE")
    for publication_id, digest in connection.execute(
        "SELECT id,manifest_sha256 FROM publications WHERE status='prepared'"
    ).fetchall():
        prepared, final = root / "prepared" / publication_id, root / "publications" / publication_id
        if not final.exists():
            final.parent.mkdir(exist_ok=True)
            prepared.rename(final)
        if checksum(final / "manifest.json") != digest:
            raise IntegrityError("Manifiesto de publicación alterado")
        _verify_bundle(final)
        connection.execute(
            "UPDATE publications SET status='published' WHERE id=?", (publication_id,)
        )
    connection.commit()


def _prepare(connection, root, plan, records, cycle_id):
    active = [
        json.loads(r[0])
        for r in connection.execute(
            "SELECT receipt_json FROM active ORDER BY source,reference_date"
        )
    ]
    predecessor = connection.execute(
        "SELECT value FROM meta WHERE key='last_publication'"
    ).fetchone()
    identity = {
        **plan,
        "cycle_id": cycle_id,
        "processed_receipts": records,
        "active_receipts": active,
        "predecessor": predecessor[0] if predecessor else None,
    }
    publication_id = _identity(identity)
    target = root / "prepared" / publication_id
    if target.exists():
        _verify_bundle(target)
        return publication_id, checksum(target / "manifest.json")
    target.parent.mkdir(exist_ok=True)
    contracts = Contracts(root / "contracts.yaml")
    with tempfile.TemporaryDirectory(prefix=".publication-", dir=target.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        counts = {}
        for source in SOURCES:
            count = 0
            with (stage / f"{source}.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=contracts.columns(source), lineterminator="\n"
                )
                writer.writeheader()
                for (raw,) in connection.execute(
                    f"SELECT record FROM rows_{source} ORDER BY key_0"
                ):
                    writer.writerow(json.loads(raw))
                    count += 1
            counts[source] = count
        manifest = {
            **identity,
            "publication_id": publication_id,
            "source_rows": counts,
            "files": {f"{s}.csv": checksum(stage / f"{s}.csv") for s in SOURCES},
        }
        (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
        stage.rename(target)
    return publication_id, checksum(target / "manifest.json")


def _apply(connection, contracts, catalog, record, root, stores):
    catalog.verify_delivery(record)
    landing = root / "landing" / _identity(record)
    content = catalog._path(record["payload_path"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != record["payload_sha256"]:
        raise IntegrityError("Entrega cambió durante la copia")
    _immutable_bytes(landing / "payload.csv", content)
    _immutable_bytes(landing / "receipt.json", canonical_bytes(record))
    source, reference = record["source"], record["reference_date"]
    previous = connection.execute(
        "SELECT revision FROM active WHERE source=? AND reference_date=?", (source, reference)
    ).fetchone()
    apply = previous is None or previous[0] < record["revision"]
    if source == "stores":
        latest = connection.execute(
            "SELECT MAX(reference_date) FROM active WHERE source='stores'"
        ).fetchone()[0]
        apply = apply and (latest is None or reference >= latest)
    if apply:
        if source == "stores":
            connection.execute("DELETE FROM rows_stores")
            connection.execute("DELETE FROM active WHERE source='stores'")
            stores.clear()
        else:
            connection.execute(f"DELETE FROM rows_{source} WHERE partition_key=?", (reference,))
    seen_keys = [set() for _ in contracts.keys(source)]
    count = 0
    for raw, typed in contracts.iter_csv(source, landing / "payload.csv"):
        if "date" in typed and typed["date"].isoformat() != reference:
            raise PipelineError("La fecha del payload no coincide con la referencia")
        validate_relation(source, typed, stores)
        keys = [json.dumps([str(typed[c]) for c in key]) for key in contracts.keys(source)]
        for seen, key in zip(seen_keys, keys, strict=True):
            if key in seen:
                raise PipelineError("Clave duplicada dentro de la entrega")
            seen.add(key)
        if apply:
            connection.execute(
                f"INSERT INTO rows_{source} VALUES ({','.join('?' for _ in range(2 + len(keys)))})",
                (reference, json.dumps(raw, sort_keys=True, ensure_ascii=False), *keys),
            )
            if source == "stores":
                stores[typed["store_nbr"]] = typed
        count += 1
    if count != record["row_count"]:
        raise PipelineError("Cantidad de filas distinta del recibo")
    if apply:
        connection.execute(
            "INSERT OR REPLACE INTO active VALUES (?,?,?,?)",
            (source, reference, record["revision"], canonical_bytes(record).decode()),
        )
    connection.execute(
        "INSERT INTO processed VALUES (?,?,?,?,?,?,?,?)",
        (
            record["delivery_id"],
            source,
            reference,
            record["revision"],
            record["payload_sha256"],
            record["metadata_sha256"],
            canonical_bytes(record).decode(),
            instant_text(datetime.now(UTC)),
        ),
    )
    return apply


def poll_cycle(inbox_root, work_root, contracts_path, as_of, cycle_id):
    """Un ciclo estable por run ID; solo abre los CSV pendientes, nunca modifica inbox."""
    inbox, work = Path(inbox_root).resolve(), Path(work_root).resolve()
    if inbox.is_relative_to(work) or work.is_relative_to(inbox):
        raise PipelineError("Bandeja y estado operativo no pueden solaparse")
    raw_catalog = (inbox / "manifest.json").read_bytes()
    initial = DeliveryCatalog(inbox, manifest_bytes=raw_catalog)
    stream_id = initial.manifest.get("operational_stream")
    if not isinstance(stream_id, str) or not re.fullmatch(r"[a-f0-9]{64}", stream_id):
        raise IntegrityError("Se requiere una bandeja operativa inicializada")
    root = work / "automatic" / stream_id
    contract_hash = checksum(contracts_path)
    contracts = Contracts(contracts_path)
    cutoff = instant_text(parse_instant(as_of))
    with closing(_open_ledger(root, stream_id, contract_hash, contracts)) as connection:
        _immutable_bytes(root / "contracts.yaml", Path(contracts_path).read_bytes())
        _finalize(connection, root)
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT as_of,catalog,code_hash,result FROM cycles WHERE cycle_id=?", (cycle_id,)
        ).fetchone()
        if existing:
            if existing[0] != cutoff:
                connection.rollback()
                raise IntegrityError("El mismo cycle_id no puede usarse con otro corte")
            if existing[3] is not None:
                connection.commit()
                return json.loads(existing[3])
            if existing[2] != _code_hash():
                connection.rollback()
                raise PipelineError("El ciclo pendiente requiere su versión original de código")
            raw_catalog = existing[1]
        else:
            connection.execute(
                "INSERT INTO cycles VALUES (?,?,?,?,NULL)",
                (cycle_id, cutoff, raw_catalog, _code_hash()),
            )
        connection.commit()
        catalog = DeliveryCatalog(inbox, manifest_bytes=raw_catalog)
        connection.execute("BEGIN IMMEDIATE")
        try:
            last = connection.execute("SELECT value FROM meta WHERE key='last_as_of'").fetchone()
            if last and parse_instant(cutoff) < parse_instant(last[0]):
                raise PipelineError(
                    "Para cortes pasados usar el modo backfill, separado del ledger vivo"
                )
            pending = []
            for record in catalog.available(cutoff):
                saved = connection.execute(
                    "SELECT receipt_json FROM processed WHERE delivery_id=?",
                    (record["delivery_id"],),
                ).fetchone()
                if saved:
                    if saved[0] != canonical_bytes(record).decode():
                        raise IntegrityError(
                            "Identificador procesado con revisión/checksum diferente"
                        )
                else:
                    pending.append(record)
            stores = {}
            for (raw,) in connection.execute("SELECT record FROM rows_stores"):
                typed = contracts.validate_row("stores", json.loads(raw))
                stores[typed["store_nbr"]] = typed
            if pending and not stores and not any(r["source"] == "stores" for r in pending):
                result = {
                    "cycle_id": cycle_id,
                    "as_of": cutoff,
                    "new_deliveries": 0,
                    "processed_files": [],
                    "publication_id": None,
                    "reason": "waiting_for_stores",
                    "pending": len(pending),
                }
            else:
                changed = False
                processed = []
                for record in sorted(
                    pending,
                    key=lambda r: (
                        r["source"] != "stores",
                        r["available_at"],
                        r["revision"],
                        r["delivery_id"],
                    ),
                ):
                    try:
                        applied = _apply(connection, contracts, catalog, record, root, stores)
                    except (ValueError, OSError, sqlite3.IntegrityError) as error:
                        evidence = {"cycle_id": cycle_id, "delivery": record, "error": str(error)}
                        _immutable_bytes(
                            root / "quarantine" / f"{_identity(evidence)}.json",
                            canonical_bytes(evidence),
                        )
                        raise PipelineError(
                            f"Entrega inválida: {record['delivery_id']}: {error}"
                        ) from error
                    changed |= applied
                    processed.append(
                        {
                            "delivery_id": record["delivery_id"],
                            "revision": record["revision"],
                            "payload_path": record["payload_path"],
                            "payload_sha256": record["payload_sha256"],
                            "row_count": record["row_count"],
                            "applied": applied,
                        }
                    )
                publication_id = None
                if changed:
                    plan = {
                        "schema_version": 1,
                        "stream_id": stream_id,
                        "as_of": cutoff,
                        "catalog_sha256": hashlib.sha256(raw_catalog).hexdigest(),
                        "contracts_sha256": contract_hash,
                        "code_sha256": _code_hash(),
                    }
                    publication_id, digest = _prepare(connection, root, plan, processed, cycle_id)
                    connection.execute(
                        "INSERT INTO publications VALUES (?,'prepared',?)", (publication_id, digest)
                    )
                    connection.execute(
                        "INSERT OR REPLACE INTO meta VALUES ('last_publication',?)",
                        (publication_id,),
                    )
                result = {
                    "cycle_id": cycle_id,
                    "as_of": cutoff,
                    "new_deliveries": len(processed),
                    "processed_files": processed,
                    "publication_id": publication_id,
                    "reason": "processed" if processed else "no_new_deliveries",
                }
            connection.execute("INSERT OR REPLACE INTO meta VALUES ('last_as_of',?)", (cutoff,))
            connection.execute(
                "UPDATE cycles SET result=? WHERE cycle_id=?",
                (canonical_bytes(result).decode(), cycle_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        _finalize(connection, root)
        return result
