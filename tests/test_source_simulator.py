import csv
import json
from datetime import timedelta

import pytest

from reposicion.contracts import ContractError
from reposicion.source_io import DeliveryCatalog, IntegrityError, checksum, parse_instant
from reposicion.source_simulator import load_policy, scheduled_time

FUTURE = "2020-01-01T00:00:00Z"


def file_state(root):
    return {
        p.relative_to(root).as_posix(): (checksum(p), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_historical_partition_respects_knowledge_not_reference_date(synthetic):
    manifest = synthetic["build"]()
    cutoff = parse_instant(manifest["historical_at"])
    for record in manifest["deliveries"]:
        assert (record["area"] == "historical") == (parse_instant(record["available_at"]) <= cutoff)
    catalog = DeliveryCatalog(synthetic["output"])
    initial = catalog.available(manifest["historical_at"], area="historical")
    assert initial
    assert any(
        r["source"] == "holidays_events" and r["reference_date"] == "2017-01-01" for r in initial
    )
    assert not any(r["source"] == "train" and r["reference_date"] == "2017-01-01" for r in initial)


def test_zero_null_absent_records_and_multiple_events_preserved(synthetic):
    synthetic["build"]()
    catalog = DeliveryCatalog(synthetic["output"])
    receipts = catalog.available(FUTURE, latest=True)
    sales = [
        row for r in receipts if r["source"] == "train" for row in catalog.read(r, as_of=FUTURE)
    ]
    assert len(sales) == 6
    assert sum(r["sales"] == "0" for r in sales) == 2
    assert any(r["sales"] == "1.25" for r in sales)
    assert not any(r["date"] == "2016-12-31" for r in sales)
    assert not any(
        r["date"] == "2016-12-29" and r["store_nbr"] == "2" and r["family"] == "GROCERY I"
        for r in sales
    )
    oil = next(r for r in receipts if r["source"] == "oil" and r["reference_date"] == "2016-12-29")
    assert catalog.read(oil, as_of=FUTURE)[0]["dcoilwtico"] == ""
    events = next(
        r
        for r in receipts
        if r["source"] == "holidays_events" and r["reference_date"] == "2017-01-01"
    )
    assert len(catalog.read(events, as_of=FUTURE)) == 2
    tx = [r for r in receipts if r["source"] == "transactions"]
    assert sum(r["row_count"] for r in tx) == 2
    assert "family" not in catalog.read(tx[0], as_of=FUTURE)[0]


def test_daily_weekly_business_day_and_unplanned_calendar(synthetic):
    policy = synthetic["policy"]
    assert (
        scheduled_time("train", "2016-12-29", [], policy).isoformat() == "2016-12-30T06:00:00-05:00"
    )
    assert (
        scheduled_time("transactions", "2016-12-29", [], policy).isoformat()
        == "2017-01-02T09:00:00-05:00"
    )
    assert (
        scheduled_time("oil", "2016-12-30", [], policy).isoformat() == "2017-01-02T18:00:00-05:00"
    )
    planned = scheduled_time("holidays_events", "2017-01-01", [{"type": "Holiday"}], policy)
    assert planned.isoformat() == "2016-12-05T08:00:00-05:00"
    mixed = scheduled_time(
        "holidays_events", "2017-01-02", [{"type": "Holiday"}, {"type": "Event"}], policy
    )
    assert mixed.isoformat() == "2017-01-09T08:00:00-05:00"


def test_late_delivery_is_invisible_until_actual_availability(synthetic):
    synthetic["policy"]["sources"]["train"]["late_percent"] = 100
    manifest = synthetic["build"]()
    record = next(
        r
        for r in manifest["deliveries"]
        if r["source"] == "train" and r["reference_date"] == "2016-12-29"
    )
    assert record["simulated_late"]
    assert parse_instant(record["available_at"]) - parse_instant(
        record["scheduled_available_at"]
    ) == timedelta(days=3)
    catalog = DeliveryCatalog(synthetic["output"])
    assert record not in catalog.available(record["scheduled_available_at"])
    with pytest.raises(IntegrityError, match="disponible"):
        catalog.read(record, as_of=record["scheduled_available_at"])
    assert record in catalog.available(record["available_at"])


def test_correction_crosses_bootstrap_boundary_and_restores_original(synthetic):
    synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    manifest = synthetic["build"]()
    catalog = DeliveryCatalog(synthetic["output"])
    versions = sorted(
        [
            r
            for r in manifest["deliveries"]
            if r["source"] == "train" and r["reference_date"] == "2016-12-29"
        ],
        key=lambda r: r["revision"],
    )
    first, corrected = versions
    assert first["area"] == "historical" and corrected["area"] == "source_inbox"
    assert corrected["corrects"] == first["delivery_id"]
    assert first["payload_sha256"] != corrected["payload_sha256"]
    original = list(csv.DictReader((synthetic["originals"] / "train.csv").open()))[:3]
    assert catalog.read(corrected, as_of=FUTURE) == original
    assert catalog.read(first, as_of=FUTURE)[1]["sales"] == "1.125"
    assert catalog.read(first, as_of=FUTURE)[0]["sales"] == "0"
    initial_versions = catalog.available(manifest["historical_at"], latest=True)
    assert first in initial_versions and corrected not in initial_versions
    assert corrected in catalog.available(corrected["available_at"], latest=True)
    # El archivo con solo ceros no recibe corrección artificial.
    assert (
        len(
            [
                r
                for r in manifest["deliveries"]
                if r["source"] == "train" and r["reference_date"] == "2016-12-30"
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    "source,reference,field",
    [
        ("transactions", "2016-12-29", "transactions"),
        ("oil", "2016-12-30", "dcoilwtico"),
    ],
)
def test_numeric_corrections_have_valid_types_and_restore_values(
    synthetic, contracts, source, reference, field
):
    synthetic["policy"]["sources"][source]["correction_percent"] = 100
    manifest = synthetic["build"]()
    catalog = DeliveryCatalog(synthetic["output"])
    versions = sorted(
        [
            r
            for r in manifest["deliveries"]
            if r["source"] == source and r["reference_date"] == reference
        ],
        key=lambda r: r["revision"],
    )
    assert len(versions) == 2
    provisional = catalog.read(versions[0], as_of=FUTURE)[0]
    final = catalog.read(versions[1], as_of=FUTURE)[0]
    contracts.validate_row(source, provisional)
    contracts.validate_row(source, final)
    assert provisional[field] != final[field]


def test_determinism_idempotence_originals_and_read_only_consumer(synthetic, tmp_path):
    before = file_state(synthetic["originals"])
    first = synthetic["build"]()
    original_state = file_state(synthetic["output"])
    assert synthetic["build"]() == first
    assert file_state(synthetic["output"]) == original_state
    other = tmp_path / "another-generation"
    assert synthetic["build"](output=other) == first
    assert {p: s[0] for p, s in file_state(other).items()} == {
        p: s[0] for p, s in original_state.items()
    }
    catalog = DeliveryCatalog(synthetic["output"])
    assert catalog.verify() == len(first["deliveries"])
    for record in catalog.available(FUTURE):
        catalog.read(record, as_of=FUTURE)
    assert file_state(synthetic["output"]) == original_state
    assert file_state(synthetic["originals"]) == before


@pytest.mark.parametrize("kind", ["payload", "metadata", "extra"])
def test_corruption_is_detected_not_repaired_in_place(synthetic, kind):
    manifest = synthetic["build"]()
    root = synthetic["output"]
    receipt = manifest["deliveries"][0]
    target = root / (receipt[f"{kind}_path"] if kind != "extra" else "unexpected.txt")
    target.write_text("alterado", encoding="utf-8")
    with pytest.raises(IntegrityError):
        DeliveryCatalog(root).verify()
    with pytest.raises(IntegrityError):
        synthetic["build"]()
    assert target.read_text() == "alterado"


def test_modified_configuration_requires_another_output(synthetic):
    synthetic["build"]()
    before = file_state(synthetic["output"])
    synthetic["policy"]["seed"] += 1
    with pytest.raises(IntegrityError, match="otra ruta"):
        synthetic["build"]()
    assert file_state(synthetic["output"]) == before


@pytest.mark.parametrize("source", ["train", "stores", "oil", "transactions", "holidays_events"])
def test_duplicate_keys_stop_publication(synthetic, source):
    path = synthetic["originals"] / f"{source}.csv"
    with path.open(newline="") as stream:
        records = list(csv.reader(stream))
    with path.open("a", newline="") as stream:
        csv.writer(stream).writerow(records[1])
    with pytest.raises(ContractError, match="duplicad"):
        synthetic["build"]()
    assert not synthetic["output"].exists()


def test_duplicate_id_across_dates_rejected(synthetic):
    path = synthetic["originals"] / "train.csv"
    with path.open("a", newline="") as stream:
        csv.writer(stream).writerow([0, "2017-01-05", 1, "DAIRY", "2", 0])
    with pytest.raises(ContractError, match="duplicada"):
        synthetic["build"]()
    assert not synthetic["output"].exists()


@pytest.mark.parametrize(
    "problem", ["unknown_store", "missing_sales", "extra_column", "empty", "bad_width"]
)
def test_invalid_sources_never_publish_partial_generation(synthetic, problem):
    path = synthetic["originals"] / "train.csv"
    with path.open(newline="") as stream:
        records = list(csv.reader(stream))
    if problem == "unknown_store":
        records[1][2] = "99"
    elif problem == "missing_sales":
        records[1][4] = ""
    elif problem == "extra_column":
        records[0].append("unexpected")
    elif problem == "bad_width":
        records[1].pop()
    else:
        records = records[:1]
    with path.open("w", newline="") as stream:
        csv.writer(stream).writerows(records)
    with pytest.raises(ContractError):
        synthetic["build"]()
    assert not synthetic["output"].exists()
    assert not list(synthetic["output"].parent.glob(".source-build-*"))


def test_naive_timestamp_and_unsafe_path_rejected(synthetic):
    synthetic["build"]()
    with pytest.raises(ValueError, match="zona"):
        DeliveryCatalog(synthetic["output"]).available("2017-01-01T00:00:00")
    path = synthetic["output"] / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["deliveries"][0]["payload_path"] = "../original/train.csv"
    path.write_text(json.dumps(manifest))
    with pytest.raises(IntegrityError, match="insegura"):
        DeliveryCatalog(synthetic["output"])


def test_originals_cannot_be_output(synthetic, contracts):
    from reposicion.source_simulator import simulate

    synthetic["build"]()
    with pytest.raises(ValueError, match="solaparse"):
        simulate(
            synthetic["originals"],
            synthetic["originals"] / "bad",
            contracts.path,
            synthetic["settings"],
        )


def test_bad_policy_rejected(synthetic):
    synthetic["policy"]["sources"]["train"]["correction_percent"] = 101
    with pytest.raises(ValueError, match="rango"):
        synthetic["build"]()
    # La configuración rechazada se dejó escrita por el fixture, no por el generador.
    with pytest.raises(ValueError):
        load_policy(synthetic["settings"])


def test_correction_waits_for_delayed_first_revision(synthetic):
    spec = synthetic["policy"]["sources"]["train"]
    spec["late_percent"] = spec["correction_percent"] = 100
    manifest = synthetic["build"]()
    versions = sorted(
        [
            r
            for r in manifest["deliveries"]
            if r["source"] == "train" and r["reference_date"] == "2016-12-29"
        ],
        key=lambda r: r["revision"],
    )
    assert parse_instant(versions[1]["available_at"]) - parse_instant(
        versions[0]["available_at"]
    ) == timedelta(days=7)


def test_cli_uses_external_source_paths(synthetic, contracts, tmp_path, monkeypatch, capsys):
    import yaml

    from reposicion.cli import main

    synthetic["build"]()
    config = tmp_path / "sources.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "original_directory": str(synthetic["originals"]),
                "simulation_directory": str(tmp_path / "cli-output"),
                "contracts": str(contracts.path),
                "availability": str(synthetic["settings"]),
            }
        )
    )
    prefix = ["reposicion", "--sources-config", str(config)]
    monkeypatch.setattr("sys.argv", [*prefix, "simulate"])
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["source_profiles"]["train"]["rows"] == 6
    monkeypatch.setattr("sys.argv", [*prefix, "verify-source"])
    main()
    assert json.loads(capsys.readouterr().out)["verified_deliveries"] > 0
    monkeypatch.setattr("sys.argv", [*prefix, "list-deliveries", "--as-of", FUTURE, "--latest"])
    main()
    assert len(json.loads(capsys.readouterr().out)) == sum(summary["deliveries_by_area"].values())


@pytest.mark.parametrize(
    "field,value", [("lag_days", 0), ("cadence", "snapshot"), ("correction_days", 0)]
)
def test_invalid_temporal_policy_is_rejected(synthetic, field, value):
    synthetic["policy"]["sources"]["train"][field] = value
    if field == "correction_days":
        synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    with pytest.raises(ValueError):
        synthetic["build"]()
