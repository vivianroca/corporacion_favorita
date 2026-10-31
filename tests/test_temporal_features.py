from datetime import date

import numpy as np
import pandas as pd
import pytest

from reposicion.hist_gradient_boosting import model_pipeline as old_boosting
from reposicion.random_forest import model_pipeline as old_forest
from reposicion.source_io import DeliveryCatalog
from reposicion.temporal_features import (
    SALE_FEATURES,
    CalendarView,
    SeriesFamilyImputer,
    TemporalFeatures,
    temporal_pipeline,
)


def test_known_calendar_respects_publication_locale_and_transfers(synthetic, contracts):
    synthetic["build"]()
    features = TemporalFeatures(DeliveryCatalog(synthetic["output"]), contracts)
    early = features.prepare(date(2017, 1, 2), "2017-01-02T12:00:00Z")
    assert early.flags(date(2017, 1, 1), 1)["holiday_national"] == 1
    assert early.flags(date(2017, 1, 1), 1)["holiday_local"] == 1
    assert early.flags(date(2017, 1, 1), 2)["holiday_local"] == 0
    # El recibo mezcla Event y Holiday: el simulador retrasa toda esa fecha.
    assert early.flags(date(2017, 1, 2), 2)["transferred"] == 0
    assert early.flags(date(2017, 1, 2), 2)["holiday_active"] == 0
    assert early.flags(date(2017, 1, 2), 1)["event"] == 0
    later = features.prepare(date(2017, 1, 9), "2017-01-10T12:00:00Z")
    assert later.flags(date(2017, 1, 2), 1)["event"] == 1
    assert later.flags(date(2017, 1, 2), 2)["transferred"] == 1
    assert later.flags(date(2017, 1, 2), 1)["transferred"] == 0
    # Una planificación futura sí puede ser conocida antes de su fecha de referencia.
    planned = features.prepare(date(2016, 12, 29), "2016-12-29T12:00:00Z")
    assert planned.flags(date(2017, 1, 1), 1)["holiday_active"] == 1


def test_lags_preserve_zero_and_separate_missing_exceptional(synthetic, contracts):
    synthetic["build"]()
    builder = TemporalFeatures(DeliveryCatalog(synthetic["output"]), contracts)
    history = {
        (date(2017, 1, 1), 1, "DAIRY"): 0,
        (date(2016, 12, 18), 1, "DAIRY"): 1.25,
        (date(2016, 12, 11), 1, "DAIRY"): 2.75,
    }
    row = builder.enrich(
        history, date(2017, 1, 8), date(2017, 1, 8), 1, "DAIRY", "2017-01-08T12:00:00Z"
    )
    assert row["lag_7"] == 0 and row["lag_7_observed_zero"] == 1
    assert row["lag_7_missing"] == 0 and row["lag_7_exceptional"] == 1
    assert np.isnan(row["lag_14"]) and row["lag_14_missing"] == 1
    assert row["normal_weekday_median"] == 2.0
    assert row["normal_weekday_count"] == 2


def feature_row(store, family, value):
    row = {"store": store, "family": family, **{key: value for key in SALE_FEATURES}}
    row.update({f"lag_{lag}_exceptional": 0 for lag in (7, 14, 21, 28)})
    return row


def test_regional_holiday_only_applies_to_matching_state():
    day = date(2017, 1, 1)
    view = CalendarView(
        {1: {"city": "Quito", "state": "Pichincha"}, 2: {"city": "Guayaquil", "state": "Guayas"}},
        {
            day: [
                {
                    "locale": "Regional",
                    "locale_name": "Guayas",
                    "type": "Holiday",
                    "transferred": False,
                }
            ]
        },
    )
    assert view.flags(day, 2)["holiday_regional"] == 1
    assert view.flags(day, 1)["holiday_regional"] == 0


def test_imputer_never_borrows_scale_from_another_family_or_refits_on_test():
    imputer = SeriesFamilyImputer().fit(
        [feature_row("1", "SMALL", 10), feature_row("1", "LARGE", 10000)]
    )
    missing = [feature_row("99", "SMALL", np.nan), feature_row("99", "LARGE", np.nan)]
    transformed = imputer.transform(pd.DataFrame(missing))
    assert transformed[0]["lag_7"] == 10
    assert transformed[1]["lag_7"] == 10000
    observed = feature_row("1", "SMALL", 0)
    observed["lag_7_exceptional"] = 1
    assert imputer.transform([observed])[0]["lag_7"] == 0
    imputer.transform([feature_row("1", "SMALL", 999999)])
    assert imputer.transform(missing)[0]["lag_7"] == 10
    with pytest.raises(ValueError, match="Sin historia"):
        imputer.transform([feature_row("1", "UNSEEN", np.nan)])


@pytest.mark.parametrize(
    "name,old,step",
    [("random_forest", old_forest, "forest"), ("hist_gradient_boosting", old_boosting, "boosting")],
)
def test_estimator_hyperparameters_are_identical(name, old, step):
    assert (
        temporal_pipeline(name).named_steps["estimator"].get_params()
        == old().named_steps[step].get_params()
    )
