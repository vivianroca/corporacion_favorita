from datetime import date, timedelta

import joblib
import numpy as np
import pytest

from reposicion.contracts import Contracts
from reposicion.random_forest import (
    SalesHistory,
    features,
    model_pipeline,
    training_data,
)
from reposicion.source_io import DeliveryCatalog


def test_features_never_read_inside_forecast_horizon():
    origin = date(2017, 1, 8)
    history = {(origin - timedelta(days=i), 1, "DAIRY"): i * 0.25 for i in range(1, 29)}
    first = features(history, origin, origin + timedelta(days=6), 1, "DAIRY")
    history[(origin, 1, "DAIRY")] = 9999999
    assert first == features(history, origin, origin + timedelta(days=6), 1, "DAIRY")
    assert first["lag_7"] == 0.25
    assert first["recent_count"] == 7
    with pytest.raises(ValueError, match="Horizonte"):
        features(history, origin, origin + timedelta(days=7), 1, "DAIRY")


def test_missing_values_differ_from_observed_zero():
    origin = date(2017, 1, 8)
    history = {(origin - timedelta(days=7), 1, "DAIRY"): 0.0}
    row = features(history, origin, origin, 1, "DAIRY")
    assert row["lag_7"] == 0
    assert row["lag_7_missing"] == 0
    assert np.isnan(row["lag_14"])
    assert row["lag_14_missing"] == 1


def test_training_excludes_holdout_and_uses_historical_versions(synthetic, contracts):
    synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    synthetic["build"]()
    catalog = DeliveryCatalog(synthetic["output"])
    history = SalesHistory(catalog, Contracts(contracts.path))
    x, y, lineage = training_data(
        history, date(2017, 1, 2), "2017-01-02T12:00:00Z", [(1, "DAIRY")], weeks=1
    )
    # Jan 2's label (8) is in the source, but belongs to the holdout, so is excluded.
    assert y == [0, 0, 4.95]
    assert len(x) == 3
    assert lineage["origins"][0]["origin"] == "2016-12-26"
    assert all(r["reference_date"] < "2017-01-02" for r in lineage["label_deliveries"])
    assert all(r["revision"] == 1 for r in lineage["label_deliveries"])


def test_pipeline_is_reproducible_and_serializable(tmp_path):
    rows = [
        {
            "family": "DAIRY",
            "store": str(i % 2),
            "lag_7": float(i),
            "lag_14": np.nan,
            "lag_14_missing": 1,
        }
        for i in range(12)
    ]
    params = {"n_estimators": 4, "max_depth": 3, "random_state": 42, "n_jobs": 1}
    first, second = model_pipeline(params), model_pipeline(params)
    first.fit(rows, list(range(12)))
    second.fit(rows, list(range(12)))
    assert np.array_equal(first.predict(rows), second.predict(rows))
    path = tmp_path / "model.joblib"
    joblib.dump(first, path)
    assert np.array_equal(first.predict(rows), joblib.load(path).predict(rows))
