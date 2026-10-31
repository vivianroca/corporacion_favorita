import csv
import json

import pytest

from reposicion.contracts import ContractError
from reposicion.ingestion import (
    PipelineError,
    discover,
    ingest,
    run_pipeline,
    snapshot,
    validate,
)
from reposicion.source_io import IntegrityError, canonical_bytes, checksum

FUTURE = "2020-01-01T00:00:00Z"


def state(root):
    return {
        str(p.relative_to(root)): (checksum(p), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def run(synthetic, contracts, tmp_path, cutoff=FUTURE, **window):
    return run_pipeline(
        synthetic["output"], tmp_path / "operational", contracts.path, cutoff, **window
    )


def rows(tmp_path, result, source):
    with (
        tmp_path / "operational/snapshots" / result["snapshot_id"] / f"{source}.csv"
    ).open() as stream:
        return list(csv.DictReader(stream))


def rewrite_synthetic_delivery(synthetic, source, reference, mutate):
    """Simula una entrega inválida con checksum válido, solo sobre fixtures temporales."""
    root = synthetic["output"]
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    record = next(
        r
        for r in manifest["deliveries"]
        if r["source"] == source and r["reference_date"] == reference
    )
    payload = root / record["payload_path"]
    with payload.open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns, records = reader.fieldnames, list(reader)
    mutate(records)
    with payload.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    record["payload_sha256"] = checksum(payload)
    metadata = root / record["metadata_path"]
    metadata.write_bytes(
        canonical_bytes(
            {k: v for k, v in record.items() if k not in {"metadata_path", "metadata_sha256"}}
        )
    )
    record["metadata_sha256"] = checksum(metadata)
    path.write_bytes(canonical_bytes(manifest))


def test_snapshot_preserves_zero_fraction_null_absence_and_granularity(
    synthetic, contracts, tmp_path
):
    synthetic["build"]()
    result = run(synthetic, contracts, tmp_path)
    sales = rows(tmp_path, result, "train")
    assert len(sales) == 6
    assert sum(r["sales"] == "0" for r in sales) == 2
    assert any(r["sales"] == "1.25" for r in sales)
    assert not any(r["date"] == "2016-12-31" for r in sales)
    assert len(rows(tmp_path, result, "transactions")) == 2
    assert "family" not in rows(tmp_path, result, "transactions")[0]
    assert rows(tmp_path, result, "oil")[0]["dcoilwtico"] == ""
    assert len(rows(tmp_path, result, "holidays_events")) == 4
    assert result["source_profiles"]["oil"]["nulls"]["dcoilwtico"] == 1


def test_as_of_does_not_read_corrupt_future_payload(synthetic, contracts, tmp_path):
    manifest = synthetic["build"]()
    future = next(
        r
        for r in manifest["deliveries"]
        if r["source"] == "train" and r["reference_date"] == "2017-01-02"
    )
    (synthetic["output"] / future["payload_path"]).write_text("future corruption")
    result = run(synthetic, contracts, tmp_path, cutoff="2016-12-30T12:00:00Z")
    assert len(rows(tmp_path, result, "train")) == 3
    assert rows(tmp_path, result, "oil") == []
    assert rows(tmp_path, result, "transactions") == []
    assert len(rows(tmp_path, result, "holidays_events")) == 2
    with pytest.raises(PipelineError, match="cuarentena"):
        run(synthetic, contracts, tmp_path)


def test_revisions_replace_and_historical_backfill_is_immutable(synthetic, contracts, tmp_path):
    synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    synthetic["build"]()
    window = {"reference_start": "2016-12-29", "reference_end": "2016-12-29"}
    initial = run(synthetic, contracts, tmp_path, cutoff="2016-12-31T23:59:59-05:00", **window)
    initial_state = state(tmp_path / "operational/snapshots" / initial["snapshot_id"])
    final = run(synthetic, contracts, tmp_path, cutoff="2017-01-07T00:00:00-05:00", **window)
    assert len(rows(tmp_path, initial, "train")) == len(rows(tmp_path, final, "train")) == 3
    assert rows(tmp_path, initial, "train")[1]["sales"] == "1.125"
    assert rows(tmp_path, final, "train")[1]["sales"] == "1.25"
    assert initial["snapshot_id"] != final["snapshot_id"]
    assert state(tmp_path / "operational/snapshots" / initial["snapshot_id"]) == initial_state
    assert (
        run(synthetic, contracts, tmp_path, cutoff="2016-12-31T23:59:59-05:00", **window) == initial
    )


def test_idempotence_and_immutable_source_originals(synthetic, contracts, tmp_path):
    synthetic["build"]()
    original_state = state(synthetic["originals"])
    source_state = state(synthetic["output"])
    first = run(synthetic, contracts, tmp_path)
    work_state = state(tmp_path / "operational")
    assert run(synthetic, contracts, tmp_path) == first
    assert state(tmp_path / "operational") == work_state
    assert state(synthetic["originals"]) == original_state
    assert state(synthetic["output"]) == source_state
    path = tmp_path / "operational/snapshots" / first["snapshot_id"] / "manifest.json"
    manifest = json.loads(path.read_text())
    assert manifest["source_manifest_sha256"] == checksum(synthetic["output"] / "manifest.json")
    assert manifest["contracts_sha256"] == checksum(contracts.path)
    assert manifest["code_sha256"]
    assert manifest["deliveries"]


@pytest.mark.parametrize(
    "problem", ["missing_sales", "unknown_store", "wrong_date", "duplicate_id"]
)
def test_invalid_known_delivery_quarantined_before_snapshot(
    synthetic, contracts, tmp_path, problem
):
    synthetic["build"]()
    source_date = "2017-01-02" if problem == "duplicate_id" else "2016-12-29"

    def mutate(records):
        column, value = {
            "missing_sales": ("sales", ""),
            "unknown_store": ("store_nbr", "99"),
            "wrong_date": ("date", "2016-12-28"),
            "duplicate_id": ("id", "0"),
        }[problem]
        records[0][column] = value

    rewrite_synthetic_delivery(synthetic, "train", source_date, mutate)
    with pytest.raises(PipelineError, match="Validación fallida"):
        run(synthetic, contracts, tmp_path)
    assert list((tmp_path / "operational/quarantine").rglob("*.json"))
    assert not (tmp_path / "operational/snapshots").exists()
    assert not list((tmp_path / "operational/validated").glob(".validate-*"))


def test_bad_checksum_quarantined_at_ingestion(synthetic, contracts, tmp_path):
    manifest = synthetic["build"]()
    record = next(r for r in manifest["deliveries"] if r["source"] == "train")
    (synthetic["output"] / record["payload_path"]).write_text("broken")
    with pytest.raises(PipelineError):
        run(synthetic, contracts, tmp_path)
    errors = list((tmp_path / "operational/quarantine").rglob("*.json"))
    assert json.loads(errors[0].read_text())["stage"] == "ingest"
    assert not (tmp_path / "operational/snapshots").exists()


def test_window_is_explicit_and_stores_dimension_is_retained(synthetic, contracts, tmp_path):
    synthetic["build"]()
    result = run(
        synthetic, contracts, tmp_path, reference_start="2017-01-01", reference_end="2017-01-02"
    )
    assert len(rows(tmp_path, result, "train")) == 2
    assert len(rows(tmp_path, result, "stores")) == 2
    saved = json.loads(
        (tmp_path / "operational/snapshots" / result["snapshot_id"] / "manifest.json").read_text()
    )
    assert saved["reference_start"] == "2017-01-01"
    assert saved["reference_end"] == "2017-01-02"


def test_empty_business_period_publishes_headers_not_invented_zeros(synthetic, contracts, tmp_path):
    synthetic["build"]()
    result = run(synthetic, contracts, tmp_path, cutoff="1900-01-01T00:00:00Z")
    assert all(p["rows"] == 0 for p in result["source_profiles"].values())
    assert rows(tmp_path, result, "train") == []


@pytest.mark.parametrize(
    "as_of,start,end",
    [
        ("2017-01-01T00:00:00", None, None),
        (FUTURE, "2017-01-03", "2017-01-01"),
        (FUTURE, "20170101", None),
    ],
)
def test_invalid_cut_or_window_rejected(synthetic, contracts, tmp_path, as_of, start, end):
    synthetic["build"]()
    with pytest.raises(ValueError):
        run(synthetic, contracts, tmp_path, cutoff=as_of, reference_start=start, reference_end=end)


def test_output_and_source_cannot_overlap(synthetic, contracts):
    synthetic["build"]()
    with pytest.raises(PipelineError, match="solaparse"):
        discover(synthetic["output"], synthetic["output"] / "landing", contracts.path, FUTURE)


def test_landing_corruption_blocks_revalidation_and_snapshot(synthetic, contracts, tmp_path):
    synthetic["build"]()
    work = tmp_path / "operational"
    plan_id = discover(synthetic["output"], work, contracts.path, FUTURE)
    ingest(synthetic["output"], work, plan_id)
    next((work / "landing").rglob("payload.csv")).write_text("altered")
    with pytest.raises(PipelineError, match="Landing inválido"):
        validate(work, plan_id)
    assert not (work / "snapshots").exists()


def test_corrupt_published_snapshot_is_not_repaired(synthetic, contracts, tmp_path):
    synthetic["build"]()
    result = run(synthetic, contracts, tmp_path)
    path = tmp_path / "operational/snapshots" / result["snapshot_id"] / "train.csv"
    path.write_text("corrupt snapshot")
    with pytest.raises(IntegrityError):
        snapshot(tmp_path / "operational", result["snapshot_id"])
    assert path.read_text() == "corrupt snapshot"


def test_new_manifest_requires_new_plan(synthetic, contracts, tmp_path):
    synthetic["build"]()
    work = tmp_path / "operational"
    plan_id = discover(synthetic["output"], work, contracts.path, FUTURE)
    manifest = synthetic["output"] / "manifest.json"
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(PipelineError, match="manifiesto cambió"):
        ingest(synthetic["output"], work, plan_id)


def test_changed_contract_minimum_is_enforced(synthetic, contracts, tmp_path):
    synthetic["build"]()
    altered = tmp_path / "contracts.yaml"
    altered.write_text(contracts.path.read_text().replace("minimum: 0", "minimum: 1000000"))
    with pytest.raises((PipelineError, ContractError)):
        run_pipeline(synthetic["output"], tmp_path / "operational", altered, FUTURE)


def test_ingest_cli_uses_pipeline_configuration(
    synthetic, contracts, tmp_path, monkeypatch, capsys
):
    import yaml

    from reposicion.cli import main

    synthetic["build"]()
    config = tmp_path / "pipeline.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "source_root": str(synthetic["output"]),
                "work_root": str(tmp_path / "operational"),
                "contracts": str(contracts.path),
            }
        )
    )
    for key in ("LAB1_SOURCE_ROOT", "LAB1_WORK_ROOT", "LAB1_CONTRACTS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "reposicion",
            "ingest-snapshot",
            "--pipeline-config",
            str(config),
            "--as-of",
            FUTURE,
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["source_profiles"]["train"]["rows"] == 6
