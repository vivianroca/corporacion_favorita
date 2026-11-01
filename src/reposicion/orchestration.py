"""Puente de orquestación: verifica publicaciones y prepara metadatos, sin modelos."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from reposicion.ingestion import _immutable_bytes, _verify_bundle
from reposicion.source_io import IntegrityError, canonical_bytes, checksum, parse_instant


def snapshot_notice(directory, forecasts_root, applied_ids=None):
    directory = Path(directory)
    manifest = _verify_bundle(directory)
    receipts = manifest.get("active_receipts", manifest.get("deliveries", []))
    today = parse_instant(manifest["as_of"]).astimezone(ZoneInfo("America/Guatemala")).date()
    days = {
        r["reference_date"]
        for r in receipts
        if r["source"] == "train"
        and date.fromisoformat(r["reference_date"]) < today
        and (applied_ids is None or r["delivery_id"] in applied_ids)
    }
    affected = []
    for path in sorted(Path(forecasts_root).glob("*/manifest.json")):
        forecast = _verify_bundle(path.parent)["identity"]
        if parse_instant(forecast["issued_at"]) <= parse_instant(manifest["as_of"]) and any(
            forecast["origin"]
            <= day
            <= str(date.fromisoformat(forecast["origin"]) + timedelta(days=6))
            for day in days
        ):
            affected.append(path.parent.name)
    return {
        "snapshot_id": directory.name,
        "path": str(directory),
        "as_of": manifest["as_of"],
        "manifest_sha256": checksum(directory / "manifest.json"),
        "sales_dates": sorted(days),
        "affected_forecast_ids": affected,
    }


def forecast_notice(directory):
    directory = Path(directory)
    manifest = _verify_bundle(directory)
    identity = manifest["identity"]
    return {
        "publication_id": directory.name,
        "path": str(directory),
        "manifest_sha256": checksum(directory / "manifest.json"),
        "as_of": identity["issued_at"],
        "origin": identity["origin"],
        "snapshot_id": identity["snapshot_id"],
        "model_run_id": identity["model_run_id"],
    }


def bootstrap(work_root):
    """Migra una sola vez publicaciones válidas anteriores al uso de Assets."""
    root = Path(work_root)
    target = root / "orchestration" / "legacy_forecasts.json"
    if target.exists():
        return json.loads(target.read_text())
    entries = [
        forecast_notice(p.parent) for p in sorted((root / "forecasts").glob("*/manifest.json"))
    ]
    record = {"schema_version": 1, "publications": entries}
    _immutable_bytes(target, canonical_bytes(record))
    return record


def authorized_forecasts(work_root, events):
    root = Path(work_root)
    path = root / "orchestration" / "legacy_forecasts.json"
    if not path.exists():
        raise ValueError("Inicializar el catálogo de publicaciones anteriores con bootstrap")
    notices = json.loads(path.read_text())["publications"] + list(events)
    found = {}
    for notice in notices:
        pid = notice.get("publication_id")
        if not pid or len(pid) != 64 or any(c not in "0123456789abcdef" for c in pid):
            raise ValueError("Identificador de pronóstico inválido")
        directory = root / "forecasts" / pid
        _verify_bundle(directory)
        if checksum(directory / "manifest.json") != notice["manifest_sha256"]:
            raise IntegrityError("Publicación distinta a la confirmada por su Asset")
        found[pid] = notice
    return sorted(found)


def event_cutoff(notices):
    cutoffs = [n["as_of"] for n in notices if n.get("as_of")]
    if not cutoffs:
        raise ValueError("El evento requiere un corte de negocio explícito")
    return max(cutoffs, key=parse_instant)


def prepare_forecast(
    work_root, contracts_path, origin, issued_at, snapshot_id=None, use_snapshot_cutoff=False
):
    from reposicion.forecast_time import validate_origin
    from reposicion.snapshot_catalog import (
        SnapshotCatalog,
        select_historical_snapshot,
        select_snapshot,
    )

    try:
        directory = (
            select_historical_snapshot(work_root, issued_at, contracts_path, snapshot_id)
            if use_snapshot_cutoff
            else select_snapshot(work_root, issued_at, snapshot_id)
        )
        if use_snapshot_cutoff:
            issued_at = json.loads((directory / "manifest.json").read_text())["as_of"]
            origin = str(parse_instant(issued_at).astimezone(ZoneInfo("America/Guatemala")).date())
        day = validate_origin(origin, issued_at)
        catalog = SnapshotCatalog(directory, contracts_path, day, issued_at)
    except IntegrityError:
        raise
    except ValueError as error:
        return {"ready": False, "reason": str(error)}
    return {
        "ready": True,
        "origin": origin,
        "issued_at": issued_at,
        "snapshot_id": directory.name,
        "manifest_sha256": catalog.digest,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "bootstrap"])
    parser.add_argument("--work-root", required=True)
    parser.add_argument("--contracts-path")
    parser.add_argument("--origin")
    parser.add_argument("--issued-at")
    parser.add_argument("--snapshot-id")
    parser.add_argument("--use-snapshot-cutoff", action="store_true")
    args = vars(parser.parse_args())
    action = args.pop("action")
    result = bootstrap(args["work_root"]) if action == "bootstrap" else prepare_forecast(**args)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
