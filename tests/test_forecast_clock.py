"""El tiempo del scheduler no se utiliza implícitamente como fecha de datos."""

import copy
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from reposicion.forecast_clock import resolve_request, validate_window
from reposicion.source_io import parse_instant


@pytest.fixture
def config():
    return yaml.safe_load(Path("configs/pronostico.yaml").read_text())


def test_scheduled_2026_and_later_week_replay_same_explicit_historical_cut(config):
    a = resolve_request(
        config,
        "scheduled",
        {},
        logical_date="2026-11-01T12:00:00Z",
        data_interval_end="2026-11-01T12:00:00Z",
    )
    b = resolve_request(
        config,
        "scheduled",
        {},
        logical_date="2026-11-08T12:00:00Z",
        data_interval_end="2026-11-08T12:00:00Z",
    )
    for key in ["origin", "issued_at", "snapshot_id", "use_snapshot_cutoff"]:
        assert a[key] == b[key]
    assert a["origin"] == "2017-03-05"
    assert a["issued_at"] == "2017-03-05T12:00:00Z"
    assert not a["use_snapshot_cutoff"]
    assert a["business_clock"]["resolution"] == "scheduled_replay"
    assert a["business_clock"]["physical_logical_date"].startswith("2026")
    assert a["business_clock"]["policy_sha256"] == b["business_clock"]["policy_sha256"]


def test_missing_or_real_time_calendar_fails_instead_of_falling_back_to_now(config):
    missing = copy.deepcopy(config)
    missing.pop("simulation_calendar")
    with pytest.raises(ValueError, match="explícito"):
        resolve_request(missing, "scheduled", {}, data_interval_end="2026-11-01T12:00:00Z")
    config["simulation_calendar"]["mode"] = "wall_clock"
    with pytest.raises(ValueError):
        resolve_request(config, "scheduled", {})


def test_manual_backfill_explicit_cut_preserves_local_date_and_snapshot(config):
    request = resolve_request(
        config,
        "manual",
        {"origin": "2017-03-05", "issued_at": "2017-03-06T00:30:00Z", "snapshot_id": "a" * 64},
        logical_date="2026-11-01T12:00:00Z",
    )
    assert request["origin"] == "2017-03-05"
    assert request["issued_at"] == "2017-03-06T00:30:00Z"
    assert request["snapshot_id"] == "a" * 64
    assert request["business_clock"]["resolution"] == "explicit_backfill"


def test_manual_origin_and_native_backfill_still_use_requested_historical_window(config):
    a = resolve_request(config, "manual", {"origin": "2017-03-05"})
    assert parse_instant(a["issued_at"]) == parse_instant("2017-03-05T12:00:00Z")
    b = resolve_request(config, "backfill", {}, data_interval_end="2017-03-05T12:00:00Z")
    assert b["origin"] == "2017-03-05" and b["snapshot_id"] is None
    with pytest.raises(ValueError, match="fuera del calendario"):
        resolve_request(config, "backfill", {}, data_interval_end="2026-11-01T12:00:00Z")


@pytest.mark.parametrize("origin", ["2013-01-01", "2017-08-10", "2026-11-01"])
def test_bounds_require_28_days_and_complete_seven_day_horizon(config, origin):
    with pytest.raises(ValueError):
        validate_window(origin, origin + "T12:00:00Z", config)


def test_snapshot_only_backfill_discovery_is_bounded_by_historical_calendar(config):
    request = resolve_request(config, "manual", {"snapshot_id": "a" * 64})
    assert request["use_snapshot_cutoff"]
    bound = parse_instant(request["issued_at"]).astimezone(ZoneInfo(config["timezone"])).date()
    assert bound == date(2017, 8, 15)
    # El corte definitivo del snapshot se vuelve a validar tras su selección.
    with pytest.raises(ValueError):
        validate_window("2026-11-01", "2026-11-01T12:00:00Z", config)
