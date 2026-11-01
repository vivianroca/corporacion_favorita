"""Confirmación conjunta y fallos de pedidos con fixtures; no se ejecutan modelos."""

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from reposicion.forecast_publication import atomic_publish
from reposicion.ingestion import _verify_bundle
from reposicion.orders import recommend
from reposicion.replenishment_publication import complete
from reposicion.source_io import IntegrityError, canonical_bytes, checksum


@pytest.fixture
def prepared(tmp_path):
    def create(model_run="existing-model"):
        identity = {
            "origin": "2017-03-05",
            "issued_at": "2017-03-05T12:00:00Z",
            "model_run_id": model_run,
            "model_version": "4",
            "snapshot_id": "snapshot",
        }

        def generate(stage):
            with (stage / "forecast_quantiles.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["date", "store_nbr", "family", "horizon", "p10", "p50", "p90"],
                )
                writer.writeheader()
                for i in range(7):
                    writer.writerow(
                        {
                            "date": str(date(2017, 3, 5) + timedelta(days=i)),
                            "store_nbr": 1,
                            "family": "DAIRY",
                            "horizon": i + 1,
                            "p10": 10,
                            "p50": 20,
                            "p90": 30,
                        }
                    )
            (stage / "lineage.json").write_bytes(
                canonical_bytes({**identity, "rows": 7, "horizon_days": 7})
            )

        return Path(atomic_publish(tmp_path / "forecasts", identity, generate)["path"])

    forecast = create()
    config = yaml.safe_load(Path("configs/costs.yaml").read_text())
    config["demand_distribution"]["scenario_count"] = 128
    config["inventory"]["per_series"] = [
        {"store_nbr": 1, "family": "DAIRY", "on_hand": 10.0, "inbound_at_arrival": 2.0}
    ]
    costs = tmp_path / "costs.yaml"
    costs.write_text(yaml.safe_dump(config))
    order = Path(recommend(forecast, costs, tmp_path / "orders")["path"])
    return forecast, order, costs, config, create


def test_complete_contains_cost_version_inventory_and_reuses_unchanged_results(prepared, tmp_path):
    forecast, orders, costs, config, _ = prepared
    result = complete(forecast, orders, tmp_path / "complete")
    directory = Path(result["path"])
    _verify_bundle(directory)
    assert len(list(directory.iterdir())) == 5
    lineage = json.loads((directory / "lineage.json").read_text())
    assert lineage["status"] == "complete"
    assert lineage["costs_version"] == checksum(costs) == result["costs_version"]
    assert lineage["inventory_assumptions"] == config["inventory"]
    assert lineage["forecast_lineage"]["model_run_id"] == "existing-model"
    assert (directory / "forecast_quantiles.csv").read_bytes() == (
        forecast / "forecast_quantiles.csv"
    ).read_bytes()
    assert (directory / "suggested_orders.csv").read_bytes() == (
        orders / "suggested_orders.csv"
    ).read_bytes()
    assert complete(forecast, orders, tmp_path / "complete")["reused"]


def test_changed_costs_create_new_complete_version_with_same_forecast(prepared, tmp_path):
    forecast, orders, costs, config, _ = prepared
    first = complete(forecast, orders, tmp_path / "complete")
    config["merma_cost_per_unit"] = 5
    costs.write_text(yaml.safe_dump(config))
    next_orders = Path(recommend(forecast, costs, tmp_path / "orders")["path"])
    second = complete(forecast, next_orders, tmp_path / "complete")
    assert first["publication_id"] != second["publication_id"]
    assert first["costs_version"] != second["costs_version"]
    assert first["forecast_publication_id"] == second["forecast_publication_id"]
    assert (Path(first["path"]) / "costs.yaml").read_bytes() != (
        Path(second["path"]) / "costs.yaml"
    ).read_bytes()


def test_no_complete_package_when_orders_are_missing(prepared, tmp_path):
    forecast, _, _, _, _ = prepared
    with pytest.raises(FileNotFoundError):
        complete(forecast, tmp_path / "missing-orders", tmp_path / "complete")
    assert not (tmp_path / "complete").exists()


def test_orders_bound_to_a_different_forecast_are_rejected(prepared, tmp_path):
    _, orders, _, _, create = prepared
    other = create("another-existing-model")
    with pytest.raises(IntegrityError, match="otro pronóstico"):
        complete(other, orders, tmp_path / "complete")
    assert not (tmp_path / "complete").exists()


def test_missing_order_rows_block_confirmation_even_with_updated_checksums(prepared, tmp_path):
    forecast, orders, _, _, _ = prepared
    csv_path = orders / "suggested_orders.csv"
    csv_path.write_text(csv_path.read_text().splitlines()[0] + "\n")
    manifest = json.loads((orders / "manifest.json").read_text())
    manifest["files"]["suggested_orders.csv"] = checksum(csv_path)
    (orders / "manifest.json").write_bytes(canonical_bytes(manifest))
    with pytest.raises(IntegrityError, match="incompletos"):
        complete(forecast, orders, tmp_path / "complete")
    assert not (tmp_path / "complete").exists()
