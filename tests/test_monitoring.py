"""Métricas, datos tardíos y correcciones; sin cargar ni entrenar modelos."""

import pytest

from reposicion.forecast_publication import publication_id
from reposicion.monitoring import compare


def forecast(day="2017-03-05", family="A"):
    return {"date": day, "store_nbr": "1", "family": family, "p10": "0", "p50": "2", "p90": "4"}


def test_zero_missing_and_interval_coverage_are_distinct():
    rows, m = compare(
        [forecast(), forecast(family="B"), forecast("2017-03-06")],
        {("2017-03-05", 1, "A"): 0},
        {"2017-03-05": {"delivery_id": "r1"}},
        "2017-03-07T12:00:00Z",
    )
    assert [r["status"] for r in rows] == ["evaluated", "absent_record", "not_delivered"]
    assert rows[0]["actual"] == 0
    assert m["mae"] == 2
    assert m["wape"] is None
    assert m["coverage_p10_p90"] == 1
    assert m["evaluated_rows"] == 1 and m["pending_rows"] == 2


def test_late_data_and_corrections_change_identity_without_mutating_forecast():
    predictions = [forecast()]
    original = [dict(r) for r in predictions]
    empty, m0 = compare(predictions, {}, {}, "2017-03-06T12:00:00Z")
    late, m1 = compare(
        predictions,
        {("2017-03-05", 1, "A"): 3},
        {"2017-03-05": {"delivery_id": "r1"}},
        "2017-03-07T12:00:00Z",
    )
    corrected, m2 = compare(
        predictions,
        {("2017-03-05", 1, "A"): 6},
        {"2017-03-05": {"delivery_id": "r2"}},
        "2017-03-08T12:00:00Z",
    )
    assert m0["mae"] is None and m1["mae"] == 1 and m2["mae"] == 4
    assert m1["wape"] == pytest.approx(1 / 3)
    assert m2["coverage_p10_p90"] == 0
    assert len({publication_id(x) for x in [empty, late, corrected]}) == 3
    assert predictions == original


def test_future_days_are_not_scored_and_duplicate_keys_fail():
    rows, m = compare(
        [forecast()],
        {("2017-03-05", 1, "A"): 3},
        {"2017-03-05": {"delivery_id": "r"}},
        "2017-03-05T12:00:00Z",
    )
    assert rows[0]["status"] == "future_date" and m["evaluated_rows"] == 0
    with pytest.raises(ValueError, match="duplicada"):
        compare([forecast(), forecast()], {}, {}, "2017-03-06T12:00:00Z")


def test_snapshot_merge_keeps_other_dates_and_replaces_entire_corrected_partition(
    tmp_path, monkeypatch
):
    import json

    from reposicion import monitoring

    full = tmp_path / "snapshots" / "full"
    corrected = tmp_path / "snapshots" / "correction"
    future = tmp_path / "snapshots" / "future"
    for directory, cutoff in [
        (full, "2017-03-07T12:00:00Z"),
        (corrected, "2017-03-08T12:00:00Z"),
        (future, "2017-03-10T12:00:00Z"),
    ]:
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(json.dumps({"as_of": cutoff}))

    def receipt(day, revision):
        return {
            "reference_date": day,
            "revision": revision,
            "delivery_id": f"{day}/{revision}",
            "payload_sha256": str(revision),
        }

    def read(directory, *args):
        if directory == full:
            return (
                {},
                {"2017-03-05": receipt("2017-03-05", 1), "2017-03-06": receipt("2017-03-06", 1)},
                {("2017-03-05", 1, "A"): 3, ("2017-03-05", 1, "B"): 20, ("2017-03-06", 1, "A"): 7},
            )
        assert directory == corrected
        return {}, {"2017-03-05": receipt("2017-03-05", 2)}, {("2017-03-05", 1, "A"): 6}

    monkeypatch.setattr(monitoring, "truth_snapshot", read)
    _, receipts, actuals, _ = monitoring.merged_truth(
        tmp_path, "unused", "2017-03-09T12:00:00Z", {"2017-03-05", "2017-03-06"}
    )
    assert receipts["2017-03-05"]["revision"] == 2
    assert actuals == {("2017-03-05", 1, "A"): 6, ("2017-03-06", 1, "A"): 7}


def test_cli_keeps_sdk_messages_out_of_json(monkeypatch, capsys):
    import json

    from reposicion import monitoring

    def evaluate(**kwargs):
        print("MLflow SDK run created")
        return {"evaluations": [], "snapshot_id": "historical"}

    monkeypatch.setattr(monitoring, "evaluate", evaluate)
    args = ["monitoring"]
    for key in ["work-root", "forecasts-root", "output-root", "contracts-path", "as-of", "uri"]:
        args.extend(["--" + key, "unused"])
    monkeypatch.setattr("sys.argv", args)
    monitoring.main()
    output = capsys.readouterr()
    assert json.loads(output.out)["snapshot_id"] == "historical"
    assert "MLflow SDK" in output.err
