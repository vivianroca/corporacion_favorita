"""Regresión del conflicto entre fecha UTC y día de emisión en Guatemala."""

from datetime import date

import pytest

from reposicion.forecast_time import validate_origin


@pytest.mark.parametrize(
    "instant", ["2017-03-06T00:30:00Z", "2017-03-05T18:30:00-06:00", "2017-03-05T12:00:00Z"]
)
def test_origin_is_local_day_not_utc_day(instant):
    assert validate_origin("2017-03-05", instant) == date(2017, 3, 5)


def test_genuinely_incompatible_origin_is_rejected():
    with pytest.raises(ValueError, match="America/Guatemala"):
        validate_origin("2017-03-06", "2017-03-06T00:30:00Z")
    with pytest.raises(ValueError):
        validate_origin("2017-03-05", "2017-03-05T12:00:00")
