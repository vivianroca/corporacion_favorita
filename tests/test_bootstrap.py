"""Plan, aislamiento, disponibilidad y reintentos; sin Docker ni entrenamiento."""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from reposicion.bootstrap import (
    Airflow,
    compose_document,
    forecast_policy,
    prepare_env,
    release_through,
    scenario,
)
from reposicion.forecast_clock import asset_request, resolve_request
from reposicion.release import initialize
from reposicion.source_io import DeliveryCatalog, checksum, parse_instant

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def planned():
    first = date(2013, 1, 1)
    last = date(2017, 8, 15)
    catalog = SimpleNamespace(
        manifest={
            "historical_at": "2017-01-01T05:00:00Z",
            "source_profiles": {"train": {"reference_dates": [str(first), str(last)]}},
        }
    )
    days = [
        {"source": "train", "reference_date": str(date(2017, 2, 1) + timedelta(days=i))}
        for i in range(100)
    ]
    catalog.available = lambda cutoff, latest: days
    model = {
        "runs": [{"params": {"training_end": "2017-01-28", "evaluated_at": "2017-03-03T12:00:00Z"}}]
    }
    return catalog, model


def test_new_cut_needs_no_preexisting_snapshot(planned):
    catalog, model = planned
    plan = scenario("2017-03-12", None, None, catalog, model)
    assert plan["issued_at"] == "2017-03-12T12:00:00Z"
    assert plan["evaluated_at"] == "2017-04-09T12:00:00Z"
    assert plan["clock"]["snapshot_id"] is None
    config = {"timezone": "America/Guatemala", "simulation_calendar": plan["clock"]}
    request = resolve_request(config, "scheduled", {}, logical_date="2026-11-01T12:00:00Z")
    assert request["origin"] == "2017-03-12" and request["snapshot_id"] is None


def test_only_discovered_snapshot_of_same_scenario_is_persisted(planned):
    plan = scenario("2017-03-12", None, None, *planned)
    base = {"timezone": "America/Guatemala"}
    assert forecast_policy(base, plan)["simulation_calendar"]["snapshot_id"] is None
    result = {"scenario": plan, "snapshot_id": "a" * 64}
    assert forecast_policy(base, plan, result)["simulation_calendar"]["snapshot_id"] == "a" * 64
    assert plan["clock"]["snapshot_id"] is None
    other = {"scenario": {**plan, "origin": "2017-03-19"}, "snapshot_id": "b" * 64}
    assert forecast_policy(base, plan, other)["simulation_calendar"]["snapshot_id"] is None


@pytest.mark.parametrize(
    "origin,issued,evaluated",
    [
        ("2017-03-01", None, None),
        ("2026-11-01", None, None),
        ("2017-03-12", "2017-03-13T12:00:00Z", None),
        ("2017-03-12", None, "2017-03-18T12:00:00Z"),
    ],
)
def test_invalid_temporal_cuts_fail(planned, origin, issued, evaluated):
    with pytest.raises(ValueError):
        scenario(origin, issued, evaluated, *planned)


def test_late_history_is_not_filled_with_future_data(planned):
    catalog, model = planned
    catalog.available = lambda cutoff, latest: []
    with pytest.raises(ValueError, match="28 días"):
        scenario("2017-03-12", None, None, catalog, model)


def test_actuals_must_be_available_at_evaluation(planned):
    catalog, model = planned
    original = catalog.available
    catalog.available = lambda cutoff, latest: [
        r for r in original(cutoff, latest) if r["reference_date"] < "2017-03-12"
    ]
    with pytest.raises(ValueError, match="Faltan entregas reales"):
        scenario("2017-03-12", None, None, catalog, model)


def test_generated_secrets_and_data_remain_ignored():
    import subprocess

    for path in [
        "data/bootstrap/repro/.env",
        "data/bootstrap/repro/compose.yaml",
        "data/bootstrap/repro/source/manifest.json",
        "data/bootstrap/repro/operational/forecasts/result.csv",
    ]:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", path], cwd=ROOT, check=False
        )
        assert result.returncode == 0


def test_compose_isolates_every_resource_and_keeps_inbox_readonly(tmp_path):
    original = (ROOT / "docker/compose.yaml").read_bytes()
    doc = compose_document(
        ROOT,
        tmp_path,
        "lab1-unit",
        "lab1-bootstrap:test",
        {"issued_at": "2017-03-12T12:00:00Z"},
        18083,
        15013,
    )
    assert doc["name"] == "lab1-unit"
    assert all(v["name"].startswith("lab1-unit_") for v in doc["volumes"].values())
    assert doc["networks"]["internal"]["name"] == "lab1-unit_internal"
    for name, service in doc["services"].items():
        if name.startswith("airflow-"):
            assert service["image"] == "lab1-bootstrap:test"
            for volume in service["volumes"]:
                if isinstance(volume, dict):
                    assert Path(volume["source"]).is_relative_to(tmp_path)
                    if volume["target"] in {"/opt/lab1/source", "/opt/lab1/inbox"}:
                        assert volume["read_only"] is True
    assert (ROOT / "docker/compose.yaml").read_bytes() == original


def test_secrets_are_local_and_reused(tmp_path, monkeypatch):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            pass

    monkeypatch.setattr("reposicion.bootstrap.socket.socket", Socket)
    first = prepare_env(tmp_path, "lab1-unit", 18083, 15013)
    content = (tmp_path / ".env").read_bytes()
    assert prepare_env(tmp_path, "lab1-unit", 18083, 15013) == first
    assert (tmp_path / ".env").read_bytes() == content
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="otros puertos"):
        prepare_env(tmp_path, "lab1-other", 18083, 15013)


def test_progressive_release_is_idempotent_and_preserves_availability(synthetic, tmp_path):
    synthetic["build"]()
    master = synthetic["output"]
    before = {str(p.relative_to(master)): checksum(p) for p in master.rglob("*") if p.is_file()}
    inbox = tmp_path / "inbox"
    initialize(master, inbox)
    cutoff = "2017-01-03T12:00:00Z"
    first = release_through(master, inbox, cutoff)
    assert first["published"]
    assert release_through(master, inbox, cutoff)["published"] == []
    for record in DeliveryCatalog(inbox).records:
        assert parse_instant(record["available_at"]) <= parse_instant(cutoff)
        original = next(
            r for r in DeliveryCatalog(master).records if r["delivery_id"] == record["delivery_id"]
        )
        assert original == record
    assert before == {
        str(p.relative_to(master)): checksum(p) for p in master.rglob("*") if p.is_file()
    }


def test_only_explicit_asset_request_can_trigger_forecast(planned):
    plan = scenario("2017-03-12", None, None, *planned)
    config = {"timezone": "America/Guatemala", "simulation_calendar": plan["clock"]}
    request = {
        "origin": plan["origin"],
        "issued_at": plan["issued_at"],
        "snapshot_id": "a" * 64,
        "request_id": "one",
    }
    resolved = resolve_request(config, "asset_triggered", asset_request([request]))
    assert resolved["business_clock"]["resolution"] == "asset_request"
    with pytest.raises(ValueError):
        resolve_request(config, "asset_triggered", {})
    with pytest.raises(ValueError):
        asset_request([request, {**request, "request_id": "another"}])


def test_released_corrections_include_their_historical_ancestors(synthetic, tmp_path):
    synthetic["policy"]["sources"]["train"]["correction_percent"] = 100
    synthetic["build"]()
    inbox = tmp_path / "inbox-corrections"
    initialize(synthetic["output"], inbox)
    release_through(synthetic["output"], inbox, "2017-01-12T12:00:00Z")
    records = DeliveryCatalog(inbox).records
    ids = {r["delivery_id"] for r in records}
    assert any(r.get("corrects") for r in records)
    assert all(not r.get("corrects") or r["corrects"] in ids for r in records)


def test_existing_dag_run_is_reused_without_new_post():
    api = Airflow("http://unused", "not-used")
    conf = {"as_of": "2017-03-12T12:00:00Z"}
    calls = []

    def call(path, method="GET", body=None):
        calls.append(method)
        return {"conf": conf, "state": "success"}

    api.call = call
    assert api.trigger("dag", "same-run", conf)["state"] == "success"
    assert calls == ["GET"]
    with pytest.raises(ValueError):
        api.trigger("dag", "same-run", {"as_of": "other"})


def test_missing_dag_run_is_posted_once():
    api = Airflow("http://unused", "not-used")

    def call(path, method="GET", body=None):
        if method == "GET":
            raise HTTPError(path, 404, "missing", {}, None)
        assert body["logical_date"] is None
        return body

    api.call = call
    assert api.trigger("dag", "new", {})["dag_run_id"] == "new"


def test_dag_chain_uses_request_and_or_assets_without_snapshot_subscription():
    source = (ROOT / "dags/lab1_pronostico_reposicion.py").read_text()
    assert "assets=FORECAST_REQUESTS" in source
    assert "assets=SNAPSHOTS" not in source
    assert "CronTriggerTimetable" in source
    assert "schedule=FORECASTS | SALES" in (ROOT / "dags/lab1_seguimiento.py").read_text()
    assert "emit_request(context, notice" in (ROOT / "dags/lab1_ingesta_temporal.py").read_text()
