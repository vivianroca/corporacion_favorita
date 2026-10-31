import csv
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from reposicion import walk_forward as wf
from reposicion.source_io import parse_instant

CONFIG = Path(__file__).resolve().parents[1] / "configs/walk_forward.yaml"


def test_windows_are_weekly_paired_and_training_precedes_forecast():
    _, windows = wf.load_windows(CONFIG)
    assert [w["forecast_start"] for w in windows] == [
        "2017-01-08",
        "2017-01-15",
        "2017-01-22",
        "2017-01-29",
    ]
    assert windows[-1]["forecast_end"] == "2017-02-04"
    for window in windows:
        assert window["training_end"] < window["forecast_start"]
        assert parse_instant(window["evaluated_at"]) - parse_instant(
            window["issued_at"]
        ) == timedelta(days=33)


def test_rejects_overlapping_or_out_of_order_windows(tmp_path):
    config = yaml.safe_load(CONFIG.read_text())
    config["forecast_starts"][1] = "2017-01-09"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="Configuración"):
        wf.load_windows(path)


def error_row(day, store, actual, error):
    return {
        "date": day,
        "store_nbr": store,
        "family": "DAIRY",
        "actual": actual,
        "absolute_error": error,
    }


def test_aggregate_uses_pooled_errors_not_mean_wape():
    windows = [
        [error_row("2017-01-08", 1, 100, 100)],
        [error_row("2017-01-15", 1, 500, 50), error_row("2017-01-15", 2, 500, 50)],
    ]
    metrics = wf.aggregate_metrics(windows)
    assert metrics["mae"] == pytest.approx(200 / 3)
    assert metrics["mae_mean"] == 75
    assert metrics["wape"] == pytest.approx(200 / 1100)
    assert metrics["wape_mean"] == pytest.approx(0.55)
    assert metrics["wape"] != metrics["wape_mean"]
    with pytest.raises(ValueError, match="repetidas"):
        wf.aggregate_metrics([windows[0], windows[0]])


def test_zero_actual_sales_do_not_fabricate_wape():
    metrics = wf.aggregate_metrics([[error_row("2017-01-08", 1, 0, 2)]])
    assert metrics["wape"] is None and metrics["wape_mean"] is None
    assert metrics["mae"] == 2
    with pytest.raises(ValueError, match="vacías"):
        wf.aggregate_metrics([[]])


@pytest.mark.parametrize("temporal", [False])
def test_synthetic_walk_forward_retrains_and_respects_revisions(
    synthetic, contracts, tmp_path, monkeypatch, temporal
):
    with (synthetic["originals"] / "train.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(contracts.columns("train"))
        row_id = 0
        for offset in range(112):
            day = date(2016, 10, 16) + timedelta(days=offset)
            if day == date(2016, 12, 25):
                continue
            for store in (1, 2):
                writer.writerow(
                    [row_id, day.isoformat(), store, "DAIRY", (offset % 7) * 0.25 * store, 0]
                )
                row_id += 1
    synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    synthetic["build"]()
    logged = []
    models = []
    original_fit = wf.fit_predict

    def fit(name, x, y, test, **kwargs):
        result = original_fit(name, x, y, test, **kwargs)
        models.append(result[0])
        return result

    @contextmanager
    def fake_run(uri, **kwargs):
        def log_results(parameters, metrics, artifacts):
            logged.append((parameters, metrics, artifacts))

        yield SimpleNamespace(
            client=SimpleNamespace(set_tag=lambda *args: None),
            run_id=f"test-{len(logged)}",
            log_results=log_results,
        )

    monkeypatch.setattr(wf, "fit_predict", fit)
    monkeypatch.setattr(wf, "training_run", fake_run)
    monkeypatch.setattr(wf, "log_experiment", lambda *args, **kwargs: "aggregate-test")
    monkeypatch.setattr(wf, "plots", lambda *args, **kwargs: None)
    options = {}
    if temporal:
        from reposicion.source_io import DeliveryCatalog
        from reposicion.temporal_features import TemporalFeatures, temporal_pipeline

        options = {
            "feature_builder": TemporalFeatures(DeliveryCatalog(synthetic["output"]), contracts),
            "pipeline_factory": temporal_pipeline,
        }
    result = wf.run(
        synthetic["output"],
        contracts.path,
        CONFIG,
        tmp_path / "results",
        "http://unused",
        **options,
    )
    assert len(logged) == 12
    assert len(models) == len({id(m) for m in models}) == 8
    assert len(result["aggregates"]) == 3
    assert {r["observations"] for r in result["aggregates"]} == {56}
    for index in range(4):
        baseline, forest, boosting = logged[index * 3 : index * 3 + 3]
        assert forest[0]["shared_training_sha256"] == boosting[0]["shared_training_sha256"]
        assert forest[0]["training_rows"] == boosting[0]["training_rows"] == 110
        assert {r[1]["observations"] for r in (baseline, forest, boosting)} == {14}
        for parameters, _, path in (forest, boosting):
            import json

            lineage = json.loads((path / "lineage.json").read_text())
            if temporal:
                receipts = {r["delivery_id"]: r for r in lineage["calendar"]["receipts"]}
                for context in lineage["calendar"]["contexts"]:
                    for receipt_id in context["delivery_ids"]:
                        assert parse_instant(receipts[receipt_id]["available_at"]) <= parse_instant(
                            context["as_of"]
                        )
            for receipt in lineage["training"]["label_deliveries"]:
                assert receipt["reference_date"] < parameters["forecast_start"]
                assert parse_instant(receipt["available_at"]) <= parse_instant(
                    parameters["issued_at"]
                )
            for origin in lineage["training"]["origins"]:
                allowed = set(origin["feature_deliveries"])
                for receipt in lineage["training_and_feature_receipts"]:
                    if receipt["delivery_id"] in allowed:
                        assert parse_instant(receipt["available_at"]) <= parse_instant(
                            origin["issued_at"]
                        )
