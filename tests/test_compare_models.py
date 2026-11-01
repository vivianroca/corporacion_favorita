"""Verificación numérica de la comparación; no se ajusta ningún modelo."""

import pytest

from reposicion.compare_models import scores, validate_model


def test_scores_preserve_order_and_unit_invariance():
    assert scores([2, 4, 8]) == [1, 0.5, 0.25]
    assert scores([200, 400, 800]) == scores([2, 4, 8])


def test_zero_error_normalization():
    assert scores([0, 3, 0]) == [1, 0, 1]


@pytest.mark.parametrize("values", [[], [-1, 2], [float("nan")], [float("inf")]])
def test_invalid_scores(values):
    with pytest.raises(ValueError):
        scores(values)


def test_global_metrics_use_pooled_denominators():
    folds = [
        {"observations": 2, "actual_sales_sum": 10, "mae": 2, "wape": 0.4},
        {"observations": 8, "actual_sales_sum": 90, "mae": 1, "wape": 8 / 90},
    ]
    summary = {"observations": 10, "actual_sales_sum": 100, "mae": 1.2, "wape": 0.12}
    validate_model(summary, folds)
    with pytest.raises(ValueError):
        validate_model({**summary, "mae": 1.5, "wape": 0.15}, folds)
    with pytest.raises(ValueError):
        validate_model({**summary, "observations": 9}, folds)
