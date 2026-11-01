"""Confirma un paquete inmutable de pronóstico y pedidos; no ejecuta modelos."""

import argparse
import csv
import hashlib
import json
import math
import shutil
from datetime import timedelta
from pathlib import Path

from reposicion.forecast_publication import atomic_publish, publication_id
from reposicion.ingestion import _verify_bundle
from reposicion.orders import load_costs, read_forecasts
from reposicion.source_io import IntegrityError, canonical_bytes, checksum


def complete(forecast_dir, orders_dir, output_root):
    forecast_dir, orders_dir = Path(forecast_dir), Path(orders_dir)
    if any(
        Path(output_root).resolve().is_relative_to(source.resolve())
        for source in [forecast_dir, orders_dir]
    ):
        raise ValueError("El paquete completo debe estar separado de sus fuentes")
    forecast = _verify_bundle(forecast_dir)
    orders = _verify_bundle(orders_dir)
    origin, forecast_lineage, groups = read_forecasts(forecast_dir)
    orders_lineage = json.loads((orders_dir / "lineage.json").read_text())
    config = load_costs(orders_dir / "costs.yaml")
    costs_sha = checksum(orders_dir / "costs.yaml")
    forecast_hashes = {
        name: checksum(forecast_dir / name) for name in ["forecast_quantiles.csv", "lineage.json"]
    }
    if orders["identity"]["forecast_files_sha256"] != forecast_hashes:
        raise IntegrityError("Pedidos calculados para otro pronóstico")
    if (
        orders["identity"]["costs_sha256"] != costs_sha
        or orders_lineage["identity"] != orders["identity"]
        or orders_lineage["assumptions"] != config
        or orders_lineage["forecast_lineage"] != forecast_lineage
    ):
        raise IntegrityError("Costos, inventario o linaje de pedidos incompatibles")
    for manifest, directory in [(forecast, forecast_dir), (orders, orders_dir)]:
        if (
            manifest["publication_id"] != directory.name
            or publication_id(manifest["identity"]) != directory.name
        ):
            raise IntegrityError("Identidad de publicación incompatible")
    with (orders_dir / "suggested_orders.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    keys = set()
    for row in rows:
        key = int(row["store_nbr"]), row["family"]
        quantity = float(row["suggested_order"])
        if (
            key in keys
            or row["origin"] != str(origin)
            or row["horizon_end"] != str(origin + timedelta(days=6))
            or not math.isfinite(quantity)
            or quantity < 0
            or float(row["shortage_cost_per_unit"]) != config["shortage_cost_per_unit"]
            or float(row["merma_cost_per_unit"]) != config["merma_cost_per_unit"]
        ):
            raise IntegrityError("Pedido duplicado, inválido o fuera de su política")
        keys.add(key)
    if keys != set(groups) or len(rows) != orders_lineage["series_count"]:
        raise IntegrityError("Pedidos incompletos para las series pronosticadas")
    inventory_sha = hashlib.sha256(canonical_bytes(config["inventory"])).hexdigest()
    identity = {
        "schema_version": 1,
        "forecast_publication_id": forecast_dir.name,
        "forecast_manifest_sha256": checksum(forecast_dir / "manifest.json"),
        "orders_publication_id": orders_dir.name,
        "orders_manifest_sha256": checksum(orders_dir / "manifest.json"),
        "costs_sha256": costs_sha,
        "inventory_assumptions_sha256": inventory_sha,
        "code_sha256": checksum(__file__),
    }

    def generate(stage):
        for source, name in [
            (forecast_dir, "forecast_quantiles.csv"),
            (orders_dir, "suggested_orders.csv"),
            (orders_dir, "costs.yaml"),
        ]:
            shutil.copyfile(source / name, stage / name)
        lineage = {
            "status": "complete",
            "identity": identity,
            "costs_schema_version": config["schema_version"],
            "costs_version": costs_sha,
            "inventory_assumptions": config["inventory"],
            "lead_time_days": config["lead_time_days"],
            "horizon_days": 7,
            "forecast_lineage": forecast_lineage,
            "orders_lineage": orders_lineage,
            "order_rows": len(rows),
        }
        (stage / "lineage.json").write_bytes(canonical_bytes(lineage))
        # Los bundles fuente son inmutables; se vuelve a comprobar antes del commit.
        _verify_bundle(forecast_dir)
        _verify_bundle(orders_dir)
        if (
            checksum(forecast_dir / "manifest.json") != identity["forecast_manifest_sha256"]
            or checksum(orders_dir / "manifest.json") != identity["orders_manifest_sha256"]
            or any(
                checksum(stage / name) != checksum(source / name)
                for source, name in [
                    (forecast_dir, "forecast_quantiles.csv"),
                    (orders_dir, "suggested_orders.csv"),
                    (orders_dir, "costs.yaml"),
                ]
            )
        ):
            raise IntegrityError("Entradas cambiaron durante la confirmación")

    result = atomic_publish(output_root, identity, generate)
    return {
        **result,
        "forecast_publication_id": forecast_dir.name,
        "orders_publication_id": orders_dir.name,
        "costs_schema_version": config["schema_version"],
        "costs_version": costs_sha,
        "inventory_assumptions_sha256": inventory_sha,
        "complete_manifest_sha256": checksum(Path(result["path"]) / "manifest.json"),
        "order_rows": len(rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["forecast-dir", "orders-dir", "output-root"]:
        parser.add_argument("--" + name, required=True)
    print(json.dumps(complete(**vars(parser.parse_args())), indent=2))


if __name__ == "__main__":
    main()
