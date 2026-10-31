import runpy
from pathlib import Path

import joblib
import numpy as np
import pytest
import yaml
from catboost import CatBoostRegressor

from reposicion import catboost_candidate as candidate
from reposicion import catboost_model
from reposicion.temporal_features import SALE_FEATURES, temporal_pipeline

PARAMETERS = Path(__file__).resolve().parents[1] / "configs/catboost.yaml"


def rows():
    values = []
    for i in range(24):
        row = {
            "store": str(i % 2 + 1),
            "family": "DAIRY",
            "weekday": str(i % 7),
            "horizon": i % 7 + 1,
            **{key: i * 0.25 for key in SALE_FEATURES},
        }
        row.update({f"lag_{lag}_exceptional": 0 for lag in (7, 14, 21, 28)})
        values.append(row)
    values[0]["lag_14"] = np.nan
    return values


def test_preprocessing_is_identical_to_temporal_v2():
    parameters = candidate.load_parameters(PARAMETERS)
    actual = candidate.model_pipeline(parameters)[:-1].fit_transform(rows())
    expected = temporal_pipeline("random_forest")[:-1].fit_transform(rows())
    np.testing.assert_array_equal(actual, expected)
    assert parameters["use_best_model"] is False
    assert parameters["iterations"] == 300


def test_full_pipeline_and_native_model_roundtrip(tmp_path):
    parameters = {**candidate.load_parameters(PARAMETERS), "iterations": 3}
    model = candidate.model_pipeline(parameters)
    model.fit(rows(), [i * 0.25 for i in range(24)])
    assert model.named_steps["estimator"].model_.tree_count_ == 3
    predictions = model.predict(rows())
    assert np.isfinite(predictions).all() and (predictions >= 0).all()
    path = tmp_path / "pipeline.joblib"
    joblib.dump(model, path)
    np.testing.assert_allclose(joblib.load(path).predict(rows()), predictions)
    native_path = tmp_path / "model.cbm"
    model.named_steps["estimator"].model_.save_model(str(native_path))
    native = CatBoostRegressor().load_model(str(native_path))
    np.testing.assert_allclose(
        np.maximum(native.predict(model[:-1].transform(rows())), 0), predictions
    )


def test_fit_receives_no_validation_set_and_persistence_includes_floor(monkeypatch):
    received = {}

    class Spy:
        def __init__(self, **parameters):
            received["parameters"] = parameters

        def fit(self, x, y, **kwargs):
            received["fit_kwargs"] = kwargs
            received["labels"] = list(y)

        def predict(self, x):
            return np.array([-3.0, 4.5])

    monkeypatch.setattr(catboost_model, "CatBoostRegressor", Spy)
    model = candidate.CatBoostSalesRegressor(candidate.load_parameters(PARAMETERS))
    model.fit([[0], [1]], [0, 1])
    assert received["fit_kwargs"] == {} and received["labels"] == [0, 1]
    np.testing.assert_array_equal(model.predict([[0], [1]]), [0, 4.5])


def test_configuration_rejects_early_stopping(tmp_path):
    config = yaml.safe_load(PARAMETERS.read_text())
    config["parameters"]["early_stopping_rounds"] = 10
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="sobreajuste"):
        candidate.load_parameters(path)


def test_pipeline_serializes_when_entrypoint_runs_under_a_different_module_name(tmp_path):
    namespace = runpy.run_path(candidate.__file__, run_name="catboost_cli")
    parameters = {**candidate.load_parameters(PARAMETERS), "iterations": 3}
    model = namespace["model_pipeline"](parameters)
    model.fit(rows(), [i * 0.25 for i in range(24)])
    path = tmp_path / "cli-model.joblib"
    joblib.dump(model, path)
    np.testing.assert_allclose(joblib.load(path).predict(rows()), model.predict(rows()))
