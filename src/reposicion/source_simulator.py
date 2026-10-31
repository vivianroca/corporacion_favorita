"""Generador externo determinista de histórico y entregas; no es el pipeline operativo."""

import csv
import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

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

GENERATOR_VERSION = 1


def load_policy(path):
    policy = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1 or set(policy["sources"]) != set(SOURCES):
        raise ValueError("Versión o fuentes de disponibilidad incorrectas")
    ZoneInfo(policy["timezone"])
    parse_instant(policy["historical_at"])
    date.fromisoformat(policy["stores_reference_date"])
    if type(policy["seed"]) is not int:
        raise ValueError("La semilla debe ser entera")
    for source, spec in policy["sources"].items():
        if spec["cadence"] not in {"daily", "weekly", "business_daily", "snapshot"}:
            raise ValueError(f"{source}: frecuencia inválida")
        if (spec["cadence"] == "snapshot") != (source == "stores"):
            raise ValueError("Solo stores puede tener frecuencia snapshot")
        if source in {"train", "transactions", "oil"} and spec.get("lag_days", 0) < 1:
            raise ValueError(f"{source}: debe conocerse después de la fecha observada")
        for field in (
            "hour",
            "lag_days",
            "lead_days",
            "late_percent",
            "late_days",
            "correction_percent",
        ):
            value = spec.get(field, 0)
            if type(value) is not int or value < 0:
                raise ValueError(f"{source}.{field}: entero no negativo requerido")
        if spec["hour"] > 23 or any(
            spec.get(f, 0) > 100 for f in ("late_percent", "correction_percent")
        ):
            raise ValueError(f"{source}: hora o porcentaje fuera de rango")
        if spec["cadence"] == "weekly" and (
            type(spec["weekday"]) is not int or not 0 <= spec["weekday"] <= 6
        ):
            raise ValueError(f"{source}: día semanal inválido")
        if spec.get("correction_percent", 0):
            if type(spec["correction_days"]) is not int or spec["correction_days"] <= 0:
                raise ValueError("La corrección debe ser estrictamente posterior")
            factor = Decimal(spec["provisional_factor"])
            if not factor.is_finite() or not 0 < factor < 1:
                raise ValueError("El factor provisional debe estar entre cero y uno")
            if (source, spec["correction_field"]) not in {
                ("train", "sales"),
                ("transactions", "transactions"),
                ("oil", "dcoilwtico"),
            }:
                raise ValueError("Campo de corrección no soportado")
    return policy


def scheduled_time(source, reference, rows, policy):
    spec = policy["sources"][source]
    target = date.fromisoformat(reference)
    if source == "holidays_events":
        # Un archivo por fecha; si mezcla eventos conocidos y no anticipables,
        # se entrega cuando todos pueden conocerse (opción conservadora).
        offsets = [
            spec.get("lag_days", 0)
            if row["type"] in spec.get("unplanned_types", [])
            else -spec.get("lead_days", 0)
            for row in rows
        ]
        target += timedelta(days=max(offsets))
    elif spec["cadence"] == "business_daily":
        remaining = spec.get("lag_days", 0)
        while remaining:
            target += timedelta(days=1)
            remaining -= target.weekday() < 5
    else:
        target += timedelta(days=spec.get("lag_days", 0))
    if spec["cadence"] == "weekly":
        target += timedelta(days=(spec["weekday"] - target.weekday()) % 7)
    return datetime.combine(target, time(spec["hour"]), ZoneInfo(policy["timezone"]))


def chosen(seed, source, reference, scenario, percent):
    token = f"{seed}|{source}|{reference}|{scenario}".encode()
    return int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100 < percent


def provisional_rows(source, rows, policy):
    """Altera una sola medida positiva; la corrección restaurará la fuente original."""
    spec = policy["sources"][source]
    field = spec["correction_field"]
    factor = Decimal(spec["provisional_factor"])
    for index, row in enumerate(rows):
        if row[field].strip() and Decimal(row[field]) > 0:
            updated = [dict(r) for r in rows]
            value = Decimal(row[field]) * factor
            updated[index][field] = str(int(value)) if source == "transactions" else str(value)
            return updated
    return None


def _stage_source(connection, source, original, contracts, stores, reference):
    keys = contracts.keys(source)
    key_columns = ",".join(f"key_{i} TEXT UNIQUE" for i in range(len(keys)))
    connection.execute(f"CREATE TABLE records (reference TEXT, record TEXT,{key_columns})")
    nulls, zeros = Counter(), Counter()
    count = 0
    batch = []
    for raw, typed in contracts.iter_csv(source, original):
        validate_relation(source, typed, stores)
        ref = typed["date"].isoformat() if "date" in typed else reference
        key_values = [json.dumps([str(typed[c]) for c in key]) for key in keys]
        batch.append((ref, json.dumps(raw, ensure_ascii=False, sort_keys=True), *key_values))
        count += 1
        for field, value in typed.items():
            if value is None:
                nulls[field] += 1
            elif type(value) in {int, Decimal} and value == 0:
                zeros[field] += 1
        if len(batch) == 10000:
            _insert_batch(connection, batch, keys, source)
            batch.clear()
    _insert_batch(connection, batch, keys, source)
    connection.execute("CREATE INDEX records_reference ON records(reference)")
    connection.commit()
    if count == 0:
        raise ContractError(f"{source}: el archivo original no contiene registros")
    return {"rows": count, "nulls": dict(nulls), "zeros": dict(zeros)}


def _insert_batch(connection, batch, keys, source):
    try:
        connection.executemany(
            f"INSERT INTO records VALUES ({','.join('?' for _ in range(2 + len(keys)))})", batch
        )
    except sqlite3.IntegrityError as error:
        raise ContractError(f"{source}: clave duplicada; claves verificadas: {keys}") from error


def _write_delivery(
    root,
    source,
    reference,
    revision,
    rows,
    scheduled,
    available,
    late,
    provisional,
    originals,
    contracts_hash,
    policy,
):
    area = "historical" if available <= parse_instant(policy["historical_at"]) else "source_inbox"
    delivery_id = f"{source}/{reference}/r{revision:04d}"
    relative = Path(area) / f"{delivery_id}.csv"
    payload = root / relative
    payload.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0])
    with payload.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "schema_version": 1,
        "source": source,
        "reference_date": reference,
        "available_at": instant_text(available),
        "scheduled_available_at": instant_text(scheduled),
        "revision": revision,
        "delivery_id": delivery_id,
        "corrects": f"{source}/{reference}/r{revision - 1:04d}" if revision > 1 else None,
        "area": area,
        "payload_path": relative.as_posix(),
        "payload_sha256": checksum(payload),
        "row_count": len(rows),
        "original_sha256": originals[source],
        "contracts_sha256": contracts_hash,
        "simulated_late": late,
        "simulated_provisional": provisional,
    }
    metadata_path = payload.with_suffix(".json")
    metadata_path.write_bytes(canonical_bytes(metadata))
    return {
        **metadata,
        "metadata_path": metadata_path.relative_to(root).as_posix(),
        "metadata_sha256": checksum(metadata_path),
    }


def simulate(original_directory, output_directory, contracts_path, availability_path):
    """Publica una generación completa; rechaza sobrescribir otra o reparar corrupción."""
    originals_root, output = Path(original_directory).resolve(), Path(output_directory).resolve()
    if output.is_relative_to(originals_root) or originals_root.is_relative_to(output):
        raise ValueError("La salida y los originales no pueden solaparse")
    contracts = Contracts(contracts_path)
    if set(contracts.sources) != set(SOURCES):
        raise ContractError("Se requieren exactamente los contratos de las cinco fuentes")
    policy = load_policy(availability_path)
    originals = {source: checksum(originals_root / f"{source}.csv") for source in SOURCES}
    identity = {
        "generator_version": GENERATOR_VERSION,
        "original_sha256": originals,
        "contracts_sha256": checksum(contracts_path),
        "availability_sha256": checksum(availability_path),
    }
    generation_id = hashlib.sha256(canonical_bytes(identity)).hexdigest()
    if output.exists():
        existing = DeliveryCatalog(output)
        if existing.manifest["generation_id"] != generation_id:
            raise IntegrityError("La salida pertenece a otros datos/configuración; use otra ruta")
        existing.verify()
        return existing.manifest

    # El consumidor nunca llama a este generador. Staging y publicación son
    # responsabilidad exclusiva del sistema externo simulado.
    stores = {}
    store_keys = set()
    for _, typed in contracts.iter_csv("stores", originals_root / "stores.csv"):
        if typed["store_nbr"] in store_keys:
            raise ContractError("stores: tienda duplicada")
        store_keys.add(typed["store_nbr"])
        stores[typed["store_nbr"]] = typed
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-build-", dir=output.parent) as temporary:
        stage = Path(temporary) / "generation"
        stage.mkdir()
        (stage / "historical").mkdir()
        (stage / "source_inbox").mkdir()
        deliveries, profiles = [], {}
        with closing(sqlite3.connect(Path(temporary) / "scratch.sqlite")) as connection:
            for source in SOURCES:
                profile = _stage_source(
                    connection,
                    source,
                    originals_root / f"{source}.csv",
                    contracts,
                    stores,
                    policy["stores_reference_date"],
                )
                references = [
                    r[0]
                    for r in connection.execute(
                        "SELECT DISTINCT reference FROM records ORDER BY reference"
                    )
                ]
                profile["reference_dates"] = references
                profile["late_deliveries"] = profile["corrected_partitions"] = 0
                for reference in references:
                    source_rows = [
                        json.loads(r[0])
                        for r in connection.execute(
                            "SELECT record FROM records WHERE reference=? ORDER BY key_0",
                            (reference,),
                        )
                    ]
                    # Columnas canónicas del contrato, aunque la cabecera de entrada esté reordenada.
                    source_rows = [
                        {c: row[c] for c in contracts.columns(source)} for row in source_rows
                    ]
                    spec = policy["sources"][source]
                    scheduled = scheduled_time(source, reference, source_rows, policy)
                    late = chosen(policy["seed"], source, reference, "late", spec["late_percent"])
                    available = scheduled + timedelta(days=spec["late_days"] if late else 0)
                    provisional = None
                    if chosen(
                        policy["seed"], source, reference, "correction", spec["correction_percent"]
                    ):
                        provisional = provisional_rows(source, source_rows, policy)
                    deliveries.append(
                        _write_delivery(
                            stage,
                            source,
                            reference,
                            1,
                            provisional or source_rows,
                            scheduled,
                            available,
                            late,
                            provisional is not None,
                            originals,
                            identity["contracts_sha256"],
                            policy,
                        )
                    )
                    profile["late_deliveries"] += late
                    if provisional is not None:
                        corrected_at = available + timedelta(days=spec["correction_days"])
                        deliveries.append(
                            _write_delivery(
                                stage,
                                source,
                                reference,
                                2,
                                source_rows,
                                corrected_at,
                                corrected_at,
                                False,
                                False,
                                originals,
                                identity["contracts_sha256"],
                                policy,
                            )
                        )
                        profile["corrected_partitions"] += 1
                profiles[source] = profile
                connection.execute("DROP TABLE records")
                connection.commit()
        if originals != {s: checksum(originals_root / f"{s}.csv") for s in SOURCES}:
            raise IntegrityError("Los originales cambiaron durante la simulación")
        manifest = {
            "schema_version": 1,
            "generation_id": generation_id,
            **identity,
            "historical_at": instant_text(parse_instant(policy["historical_at"])),
            "timezone": policy["timezone"],
            "availability_policy": policy,
            "source_profiles": profiles,
            "deliveries": sorted(
                deliveries,
                key=lambda d: (d["available_at"], d["source"], d["reference_date"], d["revision"]),
            ),
        }
        (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
        DeliveryCatalog(stage).verify()
        if output.exists():
            raise IntegrityError("Otra ejecución publicó la salida; no se sobrescribe")
        stage.rename(output)
    return manifest
