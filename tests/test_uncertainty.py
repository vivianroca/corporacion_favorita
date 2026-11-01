"""Cuantiles y exclusión temporal, sin entrenar modelos."""

from datetime import date

import pytest

from reposicion.uncertainty import intervals, residual_pools


def test_quantiles_order_and_nonnegative():
    p10, p50, p90 = intervals(10, list(range(-20, 20)))
    assert (p10, p50, p90) == pytest.approx((0, 9.5, 25.1))
    assert 0 <= p10 <= p50 <= p90
    with pytest.raises(ValueError):
        intervals(1, [0])


def test_future_evaluations_excluded_and_families_separate():
    params = {
        "forecast_start": "2017-01-08",
        "forecast_end": "2017-01-14",
        "training_end": "2017-01-07",
        "evaluated_at": "2017-02-10T12:00:00Z",
    }
    row = {
        "date": "2017-01-08",
        "store_nbr": "1",
        "family": "A",
        "actual": "12",
        "prediction": "10",
    }
    future = {**params, "evaluated_at": "2017-03-10T12:00:00Z"}
    pools = residual_pools(
        [(params, [row]), (future, [{**row, "actual": "99999"}])],
        date(2017, 3, 5),
        "2017-03-05T12:00:00Z",
    )
    assert dict(pools) == {("A", 1): [2]}
    with pytest.raises(ValueError, match="Sin residuos"):
        residual_pools([(future, [row])], date(2017, 3, 5), "2017-03-05T12:00:00Z")
