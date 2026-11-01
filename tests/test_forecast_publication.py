"""Publicación y selección temporal con datos sintéticos, sin ajuste de modelos."""

import json

import pytest

from reposicion.forecast_publication import atomic_publish
from reposicion.snapshot_catalog import select_snapshot
from reposicion.source_io import IntegrityError


def test_publication_retry_and_historical_revision(tmp_path):
    calls = []

    def generate(stage):
        calls.append(1)
        (stage / "forecast.csv").write_text("p10,p50,p90\n1,2,3\n")

    first = atomic_publish(tmp_path, {"snapshot": "one"}, generate)
    assert not first["reused"]
    assert atomic_publish(tmp_path, {"snapshot": "one"}, generate)["reused"]
    second = atomic_publish(tmp_path, {"snapshot": "correction"}, generate)
    assert second["publication_id"] != first["publication_id"]
    assert len(calls) == 2
    from pathlib import Path

    (Path(first["path"]) / "forecast.csv").write_text("corrupted")
    with pytest.raises(IntegrityError):
        atomic_publish(tmp_path, {"snapshot": "one"}, generate)


def test_failed_publication_can_retry(tmp_path):
    def fail(stage):
        (stage / "partial").write_text("partial")
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        atomic_publish(tmp_path, {"cutoff": 1}, fail)
    assert not [p for p in tmp_path.iterdir() if p.is_dir()]
    result = atomic_publish(tmp_path, {"cutoff": 1}, lambda p: (p / "ok").write_text("done"))
    assert not result["reused"]


def test_snapshot_selection_excludes_future_and_requires_unambiguous(tmp_path):
    for name, cutoff in [("old", "2017-03-05T12:00:00Z"), ("future", "2017-03-12T12:00:00Z")]:
        directory = tmp_path / "snapshots" / name
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(json.dumps({"as_of": cutoff}))
    assert select_snapshot(tmp_path, "2017-03-06T12:00:00Z").name == "old"
    with pytest.raises(ValueError):
        select_snapshot(tmp_path, "2017-03-01T12:00:00Z")
    duplicate = tmp_path / "snapshots" / "duplicate"
    duplicate.mkdir()
    (duplicate / "manifest.json").write_text(json.dumps({"as_of": "2017-03-05T12:00:00Z"}))
    with pytest.raises(ValueError, match="ambiguos"):
        select_snapshot(tmp_path, "2017-03-06T12:00:00Z")
    assert select_snapshot(tmp_path, "2017-03-06T12:00:00Z", "old").name == "old"


def test_snapshot_adapter_reads_only_past_and_keeps_zero(tmp_path, contracts):
    import csv
    from datetime import date, timedelta

    from reposicion.snapshot_catalog import SnapshotCatalog
    from reposicion.source_io import canonical_bytes, checksum

    origin = date(2017, 3, 5)
    cutoff = "2017-03-05T12:00:00Z"
    records = []
    with (tmp_path / "train.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=contracts.columns("train"))
        writer.writeheader()
        for i in range(1, 29):
            day = str(origin - timedelta(days=i))
            writer.writerow(
                {
                    "id": i,
                    "date": day,
                    "store_nbr": 1,
                    "family": "DAIRY",
                    "sales": 0,
                    "onpromotion": 0,
                }
            )
            records.append(
                {
                    "source": "train",
                    "reference_date": day,
                    "available_at": "2017-03-04T12:00:00Z",
                    "delivery_id": str(i),
                }
            )
    manifest = {
        "as_of": cutoff,
        "contracts_sha256": checksum(contracts.path),
        "active_receipts": records,
        "files": {"train.csv": checksum(tmp_path / "train.csv")},
    }
    (tmp_path / "manifest.json").write_bytes(canonical_bytes(manifest))
    catalog = SnapshotCatalog(tmp_path, contracts.path, origin, cutoff)
    assert catalog.read(records[0], as_of=cutoff)[0]["sales"] == "0"
    with pytest.raises(ValueError, match="posterior"):
        SnapshotCatalog(tmp_path, contracts.path, origin, "2017-03-04T12:00:00Z")
    manifest["active_receipts"] = records[1:]
    (tmp_path / "manifest.json").write_bytes(canonical_bytes(manifest))
    with pytest.raises(ValueError, match="28 días"):
        SnapshotCatalog(tmp_path, contracts.path, origin, cutoff)
