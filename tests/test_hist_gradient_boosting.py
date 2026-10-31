import numpy as np
import pandas as pd
import pytest
from mlflow.models import infer_signature
from mlflow.sklearn import load_model, save_model
from threadpoolctl import threadpool_limits

from reposicion.hist_gradient_boosting import MODEL_PARAMS, model_pipeline, verify_evaluation
from reposicion.random_forest import model_pipeline as forest_pipeline
from reposicion.random_forest import write_csv


def sample_features():
    return [
        {
            "store": str(i % 2),
            "family": "DAIRY",
            "weekday": str(i % 7),
            "horizon": i % 7 + 1,
            "lag_7": float(i) * 0.25,
            "lag_14": np.nan if i % 2 else float(i),
            "lag_14_missing": i % 2,
        }
        for i in range(24)
    ]


def test_preprocessing_matches_random_forest_exactly():
    rows = sample_features()
    expected = forest_pipeline()[:-1].fit_transform(rows)
    actual = model_pipeline()[:-1].fit_transform(pd.DataFrame(rows))
    np.testing.assert_array_equal(actual, expected)
    assert MODEL_PARAMS["early_stopping"] is False


def test_mlflow_pipeline_roundtrip_preserves_nonnegative_fractional_predictions(tmp_path):
    frame = pd.DataFrame(sample_features())
    model = model_pipeline({**MODEL_PARAMS, "max_iter": 3, "min_samples_leaf": 2})
    with threadpool_limits(limits=2):
        model.fit(frame, [i * 0.25 for i in range(24)])
        predicted = model.predict(frame)
    assert np.isfinite(predicted).all() and (predicted >= 0).all()
    path = tmp_path / "model"
    save_model(
        model,
        str(path),
        serialization_format="cloudpickle",
        signature=infer_signature(frame, predicted),
        input_example=frame.head(2),
        pip_requirements=["scikit-learn==1.9.1", "pandas==3.1.0"],
    )
    restored = load_model(str(path))
    with threadpool_limits(limits=2):
        np.testing.assert_allclose(restored.predict(frame), predicted)


def test_comparison_rejects_changed_truth_or_keys(tmp_path):
    rows = [{"date": "2017-01-08", "store_nbr": 1, "family": "DAIRY", "actual": 1.25}]
    write_csv(tmp_path / "evaluation.csv", rows)
    verify_evaluation(tmp_path, rows)
    with pytest.raises(ValueError, match="reales"):
        verify_evaluation(tmp_path, [{**rows[0], "actual": 0}])
