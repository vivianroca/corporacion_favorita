import csv
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from reposicion import automatic, release
from reposicion.ingestion import PipelineError, run_pipeline
from reposicion.source_io import DeliveryCatalog, IntegrityError, canonical_bytes, checksum

A = "2020-01-01T00:00:00Z"
B = "2020-01-01T00:05:00Z"
C = "2020-01-01T00:10:00Z"
D = "2020-01-01T00:15:00Z"
SALE = "train/2016-12-29/r0001"


def setup(synthetic, tmp_path, *, corrections=False):
    if corrections:
        synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    synthetic["build"]()
    inbox = tmp_path / "inbox"
    init = release.initialize(synthetic["output"], inbox)
    work = tmp_path / "live-work"
    root = work / "automatic" / init["stream_id"]
    return inbox, work, root


def poll(inbox, work, contracts, cutoff, cycle):
    return automatic.poll_cycle(inbox, work, contracts.path, cutoff, cycle)


def file_state(root):
    return {
        str(p.relative_to(root)): (checksum(p), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def publication_rows(root, result, source):
    with (root / "publications" / result["publication_id"] / f"{source}.csv").open() as stream:
        return list(csv.DictReader(stream))


def test_empty_then_two_releases_then_idle_only_reads_new_files(
    synthetic, contracts, tmp_path, monkeypatch
):
    inbox, work, root = setup(synthetic, tmp_path)
    master_state = file_state(synthetic["output"])
    original_state = file_state(synthetic["originals"])
    empty = poll(inbox, work, contracts, A, "empty")
    assert empty["reason"] == "no_new_deliveries"
    assert empty["publication_id"] is None
    assert DeliveryCatalog(inbox).records == []
    release.publish_next(synthetic["output"], inbox)
    source_state = file_state(inbox)
    first = poll(inbox, work, contracts, B, "first")
    assert first["new_deliveries"] == 1
    assert len(publication_rows(root, first, "stores")) == 2
    assert file_state(inbox) == source_state
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    calls = []
    original = DeliveryCatalog.verify_delivery

    def verify(self, record):
        calls.append(record["delivery_id"])
        return original(self, record)

    monkeypatch.setattr(DeliveryCatalog, "verify_delivery", verify)
    second = poll(inbox, work, contracts, C, "second")
    assert second["new_deliveries"] == 1
    assert calls == [SALE]
    assert len(publication_rows(root, second, "stores")) == 2
    assert len(publication_rows(root, second, "train")) == 3
    assert publication_rows(root, second, "train")[1]["sales"] == "1.25"
    before_publications = file_state(root / "publications")
    calls.clear()
    idle = poll(inbox, work, contracts, D, "idle")
    assert idle["publication_id"] is None and idle["new_deliveries"] == 0
    assert calls == []
    assert file_state(root / "publications") == before_publications
    assert poll(inbox, work, contracts, D, "idle") == idle
    with sqlite3.connect(root / "control.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 2
        assert (
            db.execute("SELECT COUNT(*) FROM publications WHERE status='published'").fetchone()[0]
            == 2
        )
    assert file_state(synthetic["output"]) == master_state
    assert file_state(synthetic["originals"]) == original_state


def test_correction_replaces_partition_and_preserves_publications(synthetic, contracts, tmp_path):
    inbox, work, root = setup(synthetic, tmp_path, corrections=True)
    release.publish_next(synthetic["output"], inbox)
    poll(inbox, work, contracts, A, "stores")
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    first = poll(inbox, work, contracts, B, "provisional")
    first_state = file_state(root / "publications")
    assert publication_rows(root, first, "train")[1]["sales"] == "1.125"
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE.replace("r0001", "r0002")])
    second = poll(inbox, work, contracts, C, "corrected")
    assert second["new_deliveries"] == 1
    assert len(publication_rows(root, second, "train")) == 3
    assert publication_rows(root, second, "train")[1]["sales"] == "1.25"
    after = file_state(root / "publications")
    assert all(after[k] == v for k, v in first_state.items())
    metadata = json.loads(
        (root / "publications" / second["publication_id"] / "manifest.json").read_text()
    )
    assert metadata["predecessor"] == first["publication_id"]


def test_release_preserves_historical_time_and_payload_bytes(synthetic, tmp_path):
    inbox, _, _ = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    parent = next(
        r for r in DeliveryCatalog(synthetic["output"]).records if r["delivery_id"] == SALE
    )
    released = next(r for r in DeliveryCatalog(inbox).records if r["delivery_id"] == SALE)
    assert parent == released
    assert checksum(inbox / released["payload_path"]) == parent["payload_sha256"]
    catalog = DeliveryCatalog(inbox).manifest
    assert catalog["release_events"][-1]["released_at"] != parent["available_at"]
    state = file_state(inbox)
    assert release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])["published"] == []
    assert file_state(inbox) == state


def test_publisher_requires_dimension_and_previous_revision(synthetic, tmp_path):
    inbox, _, _ = setup(synthetic, tmp_path, corrections=True)
    with pytest.raises(IntegrityError, match="tiendas"):
        release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    release.publish_next(synthetic["output"], inbox)
    with pytest.raises(IntegrityError, match="anterior"):
        release.publish_next(
            synthetic["output"], inbox, delivery_ids=[SALE.replace("r0001", "r0002")]
        )


def test_all_releases_in_batch_keep_correct_final_state(synthetic, contracts, tmp_path):
    inbox, work, root = setup(synthetic, tmp_path, corrections=True)
    published = release.publish_next(synthetic["output"], inbox, count=100)
    result = poll(inbox, work, contracts, A, "batch")
    assert result["new_deliveries"] == len(published["published"])
    assert len(publication_rows(root, result, "train")) == 6
    assert any(r["sales"] == "1.25" for r in publication_rows(root, result, "train"))


def test_future_deliveries_wait_for_historical_availability(synthetic, contracts, tmp_path):
    inbox, work, _ = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    poll(inbox, work, contracts, "2016-12-29T00:00:00Z", "stores")
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    assert poll(inbox, work, contracts, "2016-12-29T01:00:00Z", "too-early")["new_deliveries"] == 0
    assert poll(inbox, work, contracts, "2016-12-30T12:00:00Z", "on-time")["new_deliveries"] == 1


def test_recovery_after_commit_before_publication_does_not_reprocess(
    synthetic, contracts, tmp_path, monkeypatch
):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    original = automatic._finalize
    count = 0

    def crash(connection, path):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("simulated process crash")
        return original(connection, path)

    monkeypatch.setattr(automatic, "_finalize", crash)
    with pytest.raises(RuntimeError):
        poll(inbox, work, contracts, A, "recover")
    with sqlite3.connect(root / "control.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 1
        assert db.execute("SELECT status FROM publications").fetchone()[0] == "prepared"
    monkeypatch.setattr(automatic, "_finalize", original)

    def forbidden(*args):
        raise AssertionError("Reprocessing after committed cycle")

    monkeypatch.setattr(DeliveryCatalog, "verify_delivery", forbidden)
    result = poll(inbox, work, contracts, A, "recover")
    assert result["new_deliveries"] == 1
    assert len(list((root / "publications").iterdir())) == 1


def test_recovery_after_prepare_before_commit(synthetic, contracts, tmp_path, monkeypatch):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    original = automatic._prepare

    def crash(*args):
        original(*args)
        raise RuntimeError("before commit")

    monkeypatch.setattr(automatic, "_prepare", crash)
    with pytest.raises(RuntimeError):
        poll(inbox, work, contracts, A, "retry")
    with sqlite3.connect(root / "control.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 0
    monkeypatch.setattr(automatic, "_prepare", original)
    result = poll(inbox, work, contracts, A, "retry")
    assert result["new_deliveries"] == 1
    assert len(list((root / "publications").iterdir())) == 1


def test_checksum_conflict_never_changes_processed_state(synthetic, contracts, tmp_path):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    poll(inbox, work, contracts, A, "first")
    path = inbox / "manifest.json"
    catalog = json.loads(path.read_text())
    catalog["deliveries"][0]["payload_sha256"] = "0" * 64
    path.write_bytes(canonical_bytes(catalog))
    with pytest.raises(IntegrityError, match="diferente"):
        poll(inbox, work, contracts, B, "bad")
    with sqlite3.connect(root / "control.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 1


def test_corrupt_pending_file_rolls_back_and_quarantines(synthetic, contracts, tmp_path):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox, count=2)
    bad = DeliveryCatalog(inbox).records[0]
    (inbox / bad["payload_path"]).write_text("corrupted")
    with pytest.raises(PipelineError):
        poll(inbox, work, contracts, A, "invalid")
    assert list((root / "quarantine").glob("*.json"))
    with sqlite3.connect(root / "control.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 0


def test_concurrent_consumers_do_not_duplicate(synthetic, contracts, tmp_path):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda cycle: poll(inbox, work, contracts, A, cycle), ["one", "two"])
        )
    assert sorted(r["new_deliveries"] for r in results) == [0, 1]
    assert len(list((root / "publications").iterdir())) == 1


def test_historical_backfill_does_not_change_live_ledger(synthetic, contracts, tmp_path):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    poll(inbox, work, contracts, A, "live")
    before = file_state(root)
    run_pipeline(
        synthetic["output"], tmp_path / "backfill", contracts.path, "2016-12-31T23:59:59-05:00"
    )
    assert file_state(root) == before
    with pytest.raises(PipelineError, match="backfill"):
        poll(inbox, work, contracts, "2016-12-31T23:59:59-05:00", "bad-live-backfill")


def test_reinitialization_never_erases_deliveries(synthetic, tmp_path):
    inbox, _, _ = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    before = file_state(inbox)
    assert release.initialize(synthetic["output"], inbox)["released_deliveries"] == 1
    assert file_state(inbox) == before
    with pytest.raises(IntegrityError):
        release.initialize(synthetic["output"], inbox, "another-stream")


def test_semantically_invalid_delivery_with_valid_checksum_is_not_acknowledged(
    synthetic, contracts, tmp_path
):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    poll(inbox, work, contracts, A, "stores")
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    catalog = DeliveryCatalog(inbox).manifest
    receipt = next(r for r in catalog["deliveries"] if r["delivery_id"] == SALE)
    payload = inbox / receipt["payload_path"]
    with payload.open() as stream:
        reader = csv.DictReader(stream)
        columns, records = reader.fieldnames, list(reader)
    records[0]["sales"] = ""
    with payload.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    receipt["payload_sha256"] = checksum(payload)
    metadata = inbox / receipt["metadata_path"]
    metadata.write_bytes(
        canonical_bytes(
            {k: v for k, v in receipt.items() if k not in {"metadata_path", "metadata_sha256"}}
        )
    )
    receipt["metadata_sha256"] = checksum(metadata)
    (inbox / "manifest.json").write_bytes(canonical_bytes(catalog))
    with pytest.raises(PipelineError, match="nulo"):
        poll(inbox, work, contracts, B, "invalid-data")
    with sqlite3.connect(root / "control.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM processed").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM rows_train").fetchone()[0] == 0


def test_retry_uses_frozen_catalog_despite_new_release(synthetic, contracts, tmp_path, monkeypatch):
    inbox, work, root = setup(synthetic, tmp_path)
    release.publish_next(synthetic["output"], inbox)
    original = automatic._apply

    def fail(*args):
        raise PipelineError("temporary failure")

    monkeypatch.setattr(automatic, "_apply", fail)
    with pytest.raises(PipelineError):
        poll(inbox, work, contracts, A, "frozen")
    release.publish_next(synthetic["output"], inbox, delivery_ids=[SALE])
    monkeypatch.setattr(automatic, "_apply", original)
    first = poll(inbox, work, contracts, A, "frozen")
    assert first["new_deliveries"] == 1
    assert publication_rows(root, first, "train") == []
    assert poll(inbox, work, contracts, B, "next")["new_deliveries"] == 1


def test_cycle_identity_and_contract_changes_are_explicit(synthetic, contracts, tmp_path):
    inbox, work, _ = setup(synthetic, tmp_path)
    poll(inbox, work, contracts, A, "same")
    with pytest.raises(IntegrityError, match="otro corte"):
        poll(inbox, work, contracts, B, "same")
    changed = tmp_path / "contract-v2.yaml"
    changed.write_text(contracts.path.read_text() + "\n")
    with pytest.raises(IntegrityError, match="migración"):
        automatic.poll_cycle(inbox, work, changed, B, "new-contract")
