"""Motor de decisión con datos sintéticos; no se ajustan ni cargan modelos."""

import copy
import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
import yaml

from reposicion.orders import decision, demand_scenarios, load_costs, recommend
from reposicion.source_io import checksum


@pytest.fixture
def config():
    cfg = yaml.safe_load(Path("configs/costs.yaml").read_text())
    cfg["demand_distribution"]["scenario_count"] = 2048
    return cfg


@pytest.fixture
def forecasts(tmp_path):
    source = tmp_path / "forecasts"
    source.mkdir()
    with (source / "forecast_quantiles.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["date", "store_nbr", "family", "horizon", "p10", "p50", "p90"]
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
    (source / "lineage.json").write_text(
        json.dumps(
            {
                "origin": "2017-03-05",
                "issued_at": "2017-03-05T12:00:00Z",
                "horizon_days": 7,
                "rows": 7,
                "model_run_id": "synthetic-existing-run",
                "model_version": "4",
            }
        )
    )
    return source


def output(result):
    with (Path(result["path"]) / "suggested_orders.csv").open() as stream:
        return next(iter(csv.DictReader(stream)))


def test_only_cost_configuration_changes_order_and_keeps_scenarios_and_history(
    config, forecasts, tmp_path
):
    path = tmp_path / "costs.yaml"
    source_hash = checksum(forecasts / "forecast_quantiles.csv")
    config["shortage_cost_per_unit"] = 1.0
    config["merma_cost_per_unit"] = 5.0
    path.write_text(yaml.safe_dump(config))
    low = recommend(forecasts, path, tmp_path / "orders")
    low_row = output(low)
    previous = checksum(Path(low["path"]) / "suggested_orders.csv")
    # Solo cambian dos valores de costos en el mismo archivo. No se toca pronóstico ni semilla.
    config["shortage_cost_per_unit"] = 5.0
    config["merma_cost_per_unit"] = 1.0
    path.write_text(yaml.safe_dump(config))
    high = recommend(forecasts, path, tmp_path / "orders")
    high_row = output(high)
    assert float(high_row["suggested_order"]) > float(low_row["suggested_order"])
    assert float(high_row["critical_fractile"]) == pytest.approx(5 / 6)
    for key in ["demand_7d_p10", "demand_7d_p50", "demand_7d_p90"]:
        assert low_row[key] == high_row[key]
    assert high["publication_id"] != low["publication_id"]
    assert recommend(forecasts, path, tmp_path / "orders")["reused"]
    assert checksum(Path(low["path"]) / "suggested_orders.csv") == previous
    assert checksum(forecasts / "forecast_quantiles.csv") == source_hash


def test_accumulation_is_joint_scenarios_not_sum_of_daily_quantiles(config):
    config["demand_distribution"]["daily_latent_correlation"] = 0
    values = np.array([[10, 20, 30]] * 7)
    scenarios = demand_scenarios(values, config, ["2017-03-05", 1, "A"])
    result = decision(scenarios, config, 0, 0)
    assert result["demand_7d_p90"] < 200  # Sumar directamente siete P90 daría 210.
    assert result["demand_7d_p90"] != pytest.approx(210)
    assert 0 <= result["demand_7d_p10"] <= result["demand_7d_p50"] <= result["demand_7d_p90"]
    np.testing.assert_array_equal(
        scenarios, demand_scenarios(values, config, ["2017-03-05", 1, "A"])
    )
    correlated = copy.deepcopy(config)
    correlated["demand_distribution"]["daily_latent_correlation"] = 0.9
    other = decision(demand_scenarios(values, correlated, ["2017-03-05", 1, "A"]), correlated, 0, 0)
    assert other["demand_7d_p90"] > result["demand_7d_p90"]


def test_lead_time_lost_sales_inventory_and_inbound(config):
    scenarios = np.full((128, 7), 10.0)
    config["lead_time_days"] = 2
    result = decision(scenarios, config, 15, 5)
    assert result["suggested_order"] == 45
    assert result["expected_unavoidable_shortage_before_arrival"] == 5
    assert result["expected_shortage_units"] == 5
    assert result["expected_merma_units"] == 0
    assert result["expected_total_cost"] == 25
    assert result["demand_7d_p50"] == 70
    assert decision(scenarios, config, 100, 0)["suggested_order"] == 0
    assert decision(np.zeros((128, 7)), config, 0, 0)["suggested_order"] == 0


def test_fractional_orders_and_grid_cost_minimum(config):
    config["lead_time_days"] = 0
    config["shortage_cost_per_unit"] = 1
    config["merma_cost_per_unit"] = 1
    scenarios = np.zeros((4, 7))
    scenarios[:, -1] = [0.2, 0.4, 1.2, 1.8]
    assert decision(scenarios, config, 0, 0)["suggested_order"] == 0.4
    config["inventory"]["quantity_step"] = 1
    result = decision(scenarios, config, 0, 0)
    costs = [float(np.mean(np.abs(scenarios.sum(axis=1) - q))) for q in range(4)]
    assert result["suggested_order"] == int(np.argmin(costs))


@pytest.mark.parametrize(
    "field,value",
    [
        ("shortage_cost_per_unit", None),
        ("merma_cost_per_unit", -1),
        ("merma_cost_per_unit", 0),
        ("lead_time_days", 7),
    ],
)
def test_invalid_configuration_is_rejected(config, tmp_path, field, value):
    config[field] = value
    path = tmp_path / "costs.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load_costs(path)


def test_missing_day_and_inverted_quantiles_are_rejected(config, forecasts, tmp_path):
    path = tmp_path / "costs.yaml"
    path.write_text(yaml.safe_dump(config))
    csv_path = forecasts / "forecast_quantiles.csv"
    lines = csv_path.read_text().splitlines()
    csv_path.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="siete fechas"):
        recommend(forecasts, path, tmp_path / "orders")
    with pytest.raises(ValueError, match="P10"):
        demand_scenarios([[30, 20, 10]] * 7, config, ["2017-03-05", 1, "A"])
