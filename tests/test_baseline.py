from datetime import date, timedelta

import pytest

from reposicion.baseline import evaluate, read_sales, weekly_forecast


def history():
    return [
        {
            "date": date(2017, 1, 1) + timedelta(days=i),
            "store_nbr": store,
            "family": "BREAD",
            "sales": i * 0.25 * store,
        }
        for i in range(7)
        for store in (1, 2)
    ]


def test_weekly_forecast_preserves_zero_fractional_sales_and_series():
    predictions = weekly_forecast(history(), date(2017, 1, 8))
    assert len(predictions) == 14
    assert predictions[0]["prediction"] == 0
    assert predictions[3]["prediction"] == 0.5
    assert predictions[-1]["lag_date"] == "2017-01-07"


def test_rejects_future_history_and_missing_records():
    with pytest.raises(ValueError, match="leakage"):
        weekly_forecast(history(), date(2017, 1, 7))
    with pytest.raises(ValueError, match="Falta historia"):
        weekly_forecast(history()[1:], date(2017, 1, 8))


def test_metrics_and_zero_denominator():
    predictions = weekly_forecast(history(), date(2017, 1, 8))
    actual = [{**r, "date": date.fromisoformat(r["date"]), "sales": 2} for r in predictions]
    metrics, rows = evaluate(predictions, actual)
    assert metrics["mae"] == pytest.approx(sum(r["absolute_error"] for r in rows) / 14)
    assert metrics["wape"] == pytest.approx(sum(r["absolute_error"] for r in rows) / 28)
    for row in actual:
        row["sales"] = 0
    assert evaluate(predictions, actual)[0]["wape"] is None


def test_reads_only_versions_available_at_issue():
    class Catalog:
        def available(self, cutoff, latest):
            assert cutoff == "2017-01-08T12:00:00Z"
            assert latest
            return [{"source": "train", "reference_date": "2017-01-07", "revision": 1}]

        def read(self, receipt, *, as_of):
            assert receipt["revision"] == 1
            return [history()[-1]]

    class Contracts:
        def validate_row(self, source, row):
            return row

    rows, receipts = read_sales(
        Catalog(), Contracts(), date(2017, 1, 7), date(2017, 1, 7), "2017-01-08T12:00:00Z"
    )
    assert rows[0]["sales"] == 3
    assert receipts[0]["revision"] == 1


def test_future_correction_is_not_used(synthetic, contracts):
    from reposicion.source_io import DeliveryCatalog

    synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    synthetic["build"]()
    catalog = DeliveryCatalog(synthetic["output"])
    start = end = date(2017, 1, 1)
    early, receipts = read_sales(catalog, contracts, start, end, "2017-01-02T12:00:00Z")
    later, corrected = read_sales(catalog, contracts, start, end, "2017-02-01T12:00:00Z")
    assert receipts[0]["revision"] == 1
    assert corrected[0]["revision"] == 2
    assert float(early[0]["sales"]) == pytest.approx(4.95)
    assert float(later[0]["sales"]) == pytest.approx(5.5)
    with pytest.raises(ValueError, match="sin entrega"):
        read_sales(catalog, contracts, start, end, "2017-01-01T00:00:00Z")
