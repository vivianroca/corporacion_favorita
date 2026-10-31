"""Ingesta, validación y snapshots por conocimiento; independiente de Airflow/MLflow."""

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from reposicion.contracts import ContractError, Contracts, validate_relation
from reposicion.source_io import (
    SOURCES,
    DeliveryCatalog,
    IntegrityError,
    canonical_bytes,
    checksum,
    instant_text,
    parse_instant,
)

PIPELINE_VERSION = 1


class PipelineError(ValueError):
    """Falla que impide publicar; el detalle queda fuera del origen, en cuarentena."""


def settings(path=None):
    config = yaml.safe_load(
        Path(path or os.environ.get("LAB1_PIPELINE_CONFIG", "configs/pipeline.yaml")).read_text(
            encoding="utf-8"
        )
    )
    if config.get("schema_version") != 1:
        raise PipelineError("Versión de configuración no soportada")
    return {
        "source_root": os.environ.get("LAB1_SOURCE_ROOT", config["source_root"]),
        "work_root": os.environ.get("LAB1_WORK_ROOT", config["work_root"]),
        "contracts_path": os.environ.get("LAB1_CONTRACTS", config["contracts"]),
    }


def _code_hash():
    root = Path(__file__).parent
    return hashlib.sha256(
        canonical_bytes(
            {
                name: checksum(root / name)
                for name in ("ingestion.py", "contracts.py", "source_io.py")
            }
        )
    ).hexdigest()


def _identity(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _immutable_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise IntegrityError(f"Artefacto inmutable alterado: {path}")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _root(work_root):
    return Path(work_root).resolve()


def _plan_path(root, plan_id):
    if not re.fullmatch(r"[a-f0-9]{64}", plan_id):
        raise PipelineError("Identificador de plan inválido")
    return root / "plans" / f"{plan_id}.json"


def _load_plan(work_root, plan_id):
    root = _root(work_root)
    plan = json.loads(_plan_path(root, plan_id).read_text())
    if _identity(plan) != plan_id:
        raise IntegrityError("Plan alterado")
    if plan["code_sha256"] != _code_hash():
        raise PipelineError(
            "El plan requiere su versión de código original; descubrir un plan nuevo"
        )
    contract_path = root / "contracts" / f"{plan['contracts_sha256']}.yaml"
    if checksum(contract_path) != plan["contracts_sha256"]:
        raise IntegrityError("Contrato archivado alterado")
    return root, plan, Contracts(contract_path)


def discover(
    source_root, work_root, contracts_path, as_of, reference_start=None, reference_end=None
):
    """Congela recibos conocidos. La ventana opcional queda explícita en la identidad."""
    source = Path(source_root).resolve()
    root = _root(work_root)
    if source.is_relative_to(root) or root.is_relative_to(source):
        raise PipelineError("Origen y almacenamiento operativo no pueden solaparse")
    cutoff = instant_text(parse_instant(as_of))
    for boundary in (reference_start, reference_end):
        if boundary is not None and date.fromisoformat(boundary).isoformat() != boundary:
            raise PipelineError("La ventana debe usar YYYY-MM-DD")
    if reference_start and reference_end and reference_start > reference_end:
        raise PipelineError("Ventana invertida")
    contracts = Contracts(contracts_path)
    if set(contracts.sources) != set(SOURCES):
        raise ContractError("Faltan contratos de fuentes")
    catalog = DeliveryCatalog(source)
    manifest_hash = checksum(source / "manifest.json")
    records = catalog.available(cutoff, latest=True)
    # stores es un snapshot de dimensión; conservar solo el último conocido.
    stores = [r for r in records if r["source"] == "stores"]
    selected_store = (
        max(stores, key=lambda r: (r["reference_date"], r["available_at"])) if stores else None
    )
    selected = []
    for record in records:
        if record["source"] == "stores":
            if record == selected_store:
                selected.append(record)
            continue
        reference = record["reference_date"]
        if reference_start and reference < reference_start:
            continue
        if reference_end and reference > reference_end:
            continue
        selected.append(record)
    if checksum(source / "manifest.json") != manifest_hash:
        raise IntegrityError("Manifiesto cambió durante el descubrimiento")
    contract_bytes = Path(contracts_path).read_bytes()
    contract_hash = hashlib.sha256(contract_bytes).hexdigest()
    plan = {
        "schema_version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "code_sha256": _code_hash(),
        "source_generation_id": catalog.manifest["generation_id"],
        "source_manifest_sha256": manifest_hash,
        "contracts_sha256": contract_hash,
        "as_of": cutoff,
        "reference_start": reference_start,
        "reference_end": reference_end,
        "deliveries": selected,
    }
    plan_id = _identity(plan)
    _immutable_bytes(root / "contracts" / f"{contract_hash}.yaml", contract_bytes)
    _immutable_bytes(_plan_path(root, plan_id), canonical_bytes(plan))
    return plan_id


def _landing(root, record):
    return root / "landing" / _identity(record)


def _quarantine(root, plan_id, record, stage, error):
    content = {"plan_id": plan_id, "delivery": record, "stage": stage, "error": str(error)}
    _immutable_bytes(
        root / "quarantine" / plan_id / f"{_identity(content)}.json", canonical_bytes(content)
    )


def _verify_landing(root, record):
    landing = _landing(root, record)
    if (landing / "receipt.json").read_bytes() != canonical_bytes(record):
        raise IntegrityError("Recibo de landing alterado")
    if checksum(landing / "payload.csv") != record["payload_sha256"]:
        raise IntegrityError("Payload de landing alterado")
    return landing / "payload.csv"


def ingest(source_root, work_root, plan_id):
    """Copia evidencia inmutable al landing; no escribe en ninguna ruta del origen."""
    root, plan, _ = _load_plan(work_root, plan_id)
    catalog = DeliveryCatalog(source_root)
    if checksum(Path(source_root) / "manifest.json") != plan["source_manifest_sha256"]:
        raise PipelineError("El manifiesto cambió: redescubrir, sin sobrescribir el plan previo")
    for record in plan["deliveries"]:
        try:
            if parse_instant(record["available_at"]) > parse_instant(plan["as_of"]):
                raise IntegrityError("Entrega posterior al corte")
            catalog.verify_delivery(record)
            target = _landing(root, record)
            if target.exists():
                _verify_landing(root, record)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".land-", dir=target.parent) as temporary:
                stage = Path(temporary) / "receipt"
                stage.mkdir()
                shutil.copyfile(catalog._path(record["payload_path"]), stage / "payload.csv")
                if checksum(stage / "payload.csv") != record["payload_sha256"]:
                    raise IntegrityError("Entrega cambió durante la copia")
                (stage / "receipt.json").write_bytes(canonical_bytes(record))
                stage.rename(target)
        except (ValueError, OSError) as error:
            _quarantine(root, plan_id, record, "ingest", error)
            raise PipelineError(
                f"Entrega en cuarentena: {record['delivery_id']}: {error}"
            ) from error
    _immutable_bytes(
        root / "batches" / f"{plan_id}.json",
        canonical_bytes({"plan_id": plan_id, "copied_deliveries": len(plan["deliveries"])}),
    )
    return plan_id


def _verify_bundle(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = {"manifest.json", *manifest["files"]}
    actual = {p.name for p in directory.iterdir() if p.is_file()}
    if expected != actual:
        raise IntegrityError(f"Archivos faltantes o extra: {directory}")
    for name, digest in manifest["files"].items():
        if Path(name).name != name or checksum(directory / name) != digest:
            raise IntegrityError(f"Artefacto alterado: {name}")
    return manifest


def validate(work_root, plan_id):
    """Valida cada celda y unicidad global antes de publicar la etapa intermedia."""
    root, plan, contracts = _load_plan(work_root, plan_id)
    batch = json.loads((root / "batches" / f"{plan_id}.json").read_text())
    if batch != {"plan_id": plan_id, "copied_deliveries": len(plan["deliveries"])}:
        raise IntegrityError("Lote de ingesta incompatible")
    for record in plan["deliveries"]:
        try:
            _verify_landing(root, record)
        except (ValueError, OSError) as error:
            _quarantine(root, plan_id, record, "validate", error)
            raise PipelineError(f"Landing inválido: {record['delivery_id']}") from error
    output = root / "validated" / plan_id
    if output.exists():
        bundle = _verify_bundle(output)
        if bundle["plan_id"] != plan_id:
            raise IntegrityError("Validación de otro plan")
        return plan_id
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".validate-", dir=output.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        profiles = {s: {"rows": 0, "nulls": Counter(), "zeros": Counter()} for s in SOURCES}
        stores = {}
        with closing(sqlite3.connect(stage / "rows.sqlite")) as connection:
            for source in SOURCES:
                constraints = ",".join(
                    f"key_{i} TEXT UNIQUE" for i in range(len(contracts.keys(source)))
                )
                connection.execute(
                    f"CREATE TABLE {source} (record TEXT, delivery_id TEXT,{constraints})"
                )
            records = sorted(
                plan["deliveries"],
                key=lambda r: (
                    r["source"] != "stores",
                    r["source"],
                    r["reference_date"],
                    r["revision"],
                ),
            )
            for record in records:
                source = record["source"]
                try:
                    count = 0
                    for raw, typed in contracts.iter_csv(
                        source, _landing(root, record) / "payload.csv"
                    ):
                        if (
                            "date" in typed
                            and typed["date"].isoformat() != record["reference_date"]
                        ):
                            raise ContractError("La fecha del payload no coincide con el recibo")
                        validate_relation(source, typed, stores)
                        keys = [
                            json.dumps([str(typed[c]) for c in key])
                            for key in contracts.keys(source)
                        ]
                        connection.execute(
                            f"INSERT INTO {source} VALUES ({','.join('?' for _ in range(2 + len(keys)))})",
                            (
                                json.dumps(raw, sort_keys=True, ensure_ascii=False),
                                record["delivery_id"],
                                *keys,
                            ),
                        )
                        if source == "stores":
                            stores[typed["store_nbr"]] = typed
                        for field, value in typed.items():
                            if value is None:
                                profiles[source]["nulls"][field] += 1
                            elif type(value) in {int, Decimal} and value == 0:
                                profiles[source]["zeros"][field] += 1
                        count += 1
                    if count != record["row_count"]:
                        raise ContractError("Cantidad de filas distinta del recibo")
                    profiles[source]["rows"] += count
                except (ValueError, OSError, sqlite3.IntegrityError) as error:
                    _quarantine(root, plan_id, record, "validate", error)
                    raise PipelineError(
                        f"Validación fallida: {record['delivery_id']}: {error}"
                    ) from error
            connection.commit()
        report = {
            "schema_version": 1,
            "plan_id": plan_id,
            "source_profiles": profiles,
            "missing_sources": sorted(s for s, p in profiles.items() if p["rows"] == 0),
            "files": {"rows.sqlite": checksum(stage / "rows.sqlite")},
        }
        (stage / "manifest.json").write_bytes(canonical_bytes(report))
        stage.rename(output)
    return plan_id


def snapshot(work_root, plan_id):
    """Publica cinco CSV coherentes con el mismo corte y un manifiesto de linaje."""
    root, plan, contracts = _load_plan(work_root, plan_id)
    validated = root / "validated" / plan_id
    validation = _verify_bundle(validated)
    if validation["plan_id"] != plan_id:
        raise IntegrityError("Validación de otro plan")
    output = root / "snapshots" / plan_id
    if output.exists():
        saved = _verify_bundle(output)
        if saved["plan_id"] != plan_id:
            raise IntegrityError("Snapshot de otro plan")
        return {
            "snapshot_id": plan_id,
            "as_of": plan["as_of"],
            "source_profiles": saved["source_profiles"],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=output.parent) as temporary:
        stage = Path(temporary) / "snapshot"
        stage.mkdir()
        with closing(
            sqlite3.connect(f"file:{validated / 'rows.sqlite'}?mode=ro", uri=True)
        ) as connection:
            for source in SOURCES:
                with (stage / f"{source}.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(
                        stream, fieldnames=contracts.columns(source), lineterminator="\n"
                    )
                    writer.writeheader()
                    for (record,) in connection.execute(
                        f"SELECT record FROM {source} ORDER BY key_0"
                    ):
                        writer.writerow(json.loads(record))
        result = {
            **plan,
            "plan_id": plan_id,
            "validation_manifest_sha256": checksum(validated / "manifest.json"),
            "source_profiles": validation["source_profiles"],
            "missing_sources": validation["missing_sources"],
            "files": {f"{s}.csv": checksum(stage / f"{s}.csv") for s in SOURCES},
        }
        (stage / "manifest.json").write_bytes(canonical_bytes(result))
        stage.rename(output)
    return {
        "snapshot_id": plan_id,
        "as_of": plan["as_of"],
        "source_profiles": validation["source_profiles"],
    }


def run_pipeline(
    source_root, work_root, contracts_path, as_of, reference_start=None, reference_end=None
):
    plan_id = discover(
        source_root, work_root, contracts_path, as_of, reference_start, reference_end
    )
    ingest(source_root, work_root, plan_id)
    validate(work_root, plan_id)
    return snapshot(work_root, plan_id)
