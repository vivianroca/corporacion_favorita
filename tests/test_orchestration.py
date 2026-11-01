"""Eventos, cortes y autorización sin importar Airflow ni entrenar modelos."""

import json

import pytest

from reposicion.orchestration import (
    authorized_forecasts,
    bootstrap,
    event_cutoff,
    forecast_notice,
    snapshot_notice,
)
from reposicion.source_io import IntegrityError, canonical_bytes, checksum


def bundle(path, identity=None, **metadata):
    path.mkdir(parents=True)
    (path / "data.csv").write_text("value\n1\n")
    (path / "manifest.json").write_bytes(
        canonical_bytes(
            {
                "identity": identity or {},
                "files": {"data.csv": checksum(path / "data.csv")},
                **metadata,
            }
        )
    )
    return path


def forecast(root, letter):
    return bundle(
        root / "forecasts" / (letter * 64),
        {
            "issued_at": "2017-03-05T12:00:00Z",
            "origin": "2017-03-05",
            "snapshot_id": "snapshot",
            "model_run_id": "run",
        },
    )


def test_failed_or_unconfirmed_publication_is_not_authorized_but_legacy_survives(tmp_path):
    old = forecast(tmp_path, "a")
    bootstrap(tmp_path)
    successful = forecast(tmp_path, "b")
    forecast(
        tmp_path, "c"
    )  # Archivo válido sin confirmación Airflow: nunca autorizado automáticamente.
    assert authorized_forecasts(tmp_path, []) == [old.name]
    assert authorized_forecasts(tmp_path, [forecast_notice(successful)]) == [
        old.name,
        successful.name,
    ]
    assert len(bootstrap(tmp_path)["publications"]) == 1
    (old / "data.csv").write_text("altered")
    with pytest.raises(IntegrityError):
        authorized_forecasts(tmp_path, [])


def test_sales_notice_only_for_dates_that_can_evaluate_existing_forecasts(tmp_path):
    forecast(tmp_path, "a")
    source = bundle(
        tmp_path / "snapshot",
        as_of="2017-04-02T12:00:00Z",
        active_receipts=[
            {"source": "train", "reference_date": "2017-03-07", "delivery_id": "sale"}
        ],
    )
    assert snapshot_notice(source, tmp_path / "forecasts")["affected_forecast_ids"] == ["a" * 64]
    assert not snapshot_notice(source, tmp_path / "forecasts", set())["affected_forecast_ids"]
    assert snapshot_notice(source, tmp_path / "forecasts", {"sale"})["affected_forecast_ids"]
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["active_receipts"][0]["reference_date"] = "2017-02-01"
    (source / "manifest.json").write_bytes(canonical_bytes(manifest))
    assert not snapshot_notice(source, tmp_path / "forecasts")["affected_forecast_ids"]


def test_business_cutoff_uses_event_metadata_and_preserves_offsets():
    assert (
        event_cutoff([{"as_of": "2017-03-05T20:00:00-06:00"}, {"as_of": "2017-03-06T01:00:00Z"}])
        == "2017-03-05T20:00:00-06:00"
    )
    with pytest.raises(ValueError):
        event_cutoff([])
