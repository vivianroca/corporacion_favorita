"""Reloj de negocio explícito: separa el calendario del scheduler del histórico."""

import hashlib
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from reposicion.source_io import canonical_bytes, parse_instant


def validate_window(origin, issued_at, config):
    clock = config.get("simulation_calendar")
    if not isinstance(clock, dict) or clock.get("mode") != "historical_replay":
        raise ValueError(
            "Configurar simulation_calendar.mode=historical_replay; no hay fallback al reloj real"
        )
    first = date.fromisoformat(clock["data_start"])
    last = date.fromisoformat(clock["data_end"])
    day = date.fromisoformat(origin)
    local_issue = parse_instant(issued_at).astimezone(ZoneInfo(config["timezone"]))
    if first > last or local_issue.date() != day:
        raise ValueError("Origen/emisión incompatibles con el calendario histórico local")
    if day - timedelta(days=28) < first or day + timedelta(days=6) > last:
        raise ValueError(
            "Corte fuera del calendario histórico: requiere 28 días previos y siete días de horizonte"
        )
    return day


def resolve_request(config, run_type, conf, *, logical_date=None, data_interval_end=None):
    """La fecha física solo se registra; jamás se usa como corte programado implícito."""
    clock = config.get("simulation_calendar")
    if not isinstance(clock, dict) or clock.get("mode") != "historical_replay":
        raise ValueError(
            "Falta calendario simulado explícito; no usar fecha actual como fecha de datos"
        )
    validate_window(clock["origin"], clock["issued_at"], config)
    snapshot = clock.get("snapshot_id")
    if (
        not isinstance(snapshot, str)
        or len(snapshot) != 64
        or any(c not in "0123456789abcdef" for c in snapshot)
    ):
        raise ValueError("El replay programado debe fijar un snapshot_id válido")
    if not isinstance(clock.get("replay_id"), str) or not clock["replay_id"].strip():
        raise ValueError("Identificar el escenario de replay")
    kind = getattr(run_type, "value", run_type)
    if kind not in {"scheduled", "manual", "backfill"}:
        raise ValueError("Este DAG acepta cron, manual o backfill; no se activa por Assets")
    conf = conf or {}
    historical_snapshot = False
    if conf.get("origin") or conf.get("issued_at"):
        issued = conf.get("issued_at")
        if issued is None:
            issued = datetime.combine(
                date.fromisoformat(conf["origin"]), time(6), ZoneInfo(config["timezone"])
            ).isoformat()
        origin = conf.get(
            "origin", str(parse_instant(issued).astimezone(ZoneInfo(config["timezone"])).date())
        )
        snapshot = conf.get("snapshot_id")
        resolution = "explicit_backfill"
        validate_window(origin, issued, config)
    elif kind == "backfill":
        if data_interval_end is None:
            raise ValueError(
                "Backfill nativo requiere data_interval_end histórico o un corte explícito"
            )
        issued = parse_instant(str(data_interval_end)).isoformat()
        origin = str(parse_instant(issued).astimezone(ZoneInfo(config["timezone"])).date())
        snapshot = conf.get("snapshot_id")
        resolution = "backfill_interval"
        validate_window(origin, issued, config)
    elif kind == "manual" and conf.get("snapshot_id"):
        # Compatibilidad: replay de snapshot explícito dentro del calendario, no hasta "ahora".
        origin = clock["origin"]
        issued = datetime.combine(
            date.fromisoformat(clock["data_end"]), time.max, ZoneInfo(config["timezone"])
        ).isoformat()
        snapshot = conf["snapshot_id"]
        resolution = "explicit_snapshot"
        historical_snapshot = True
    else:
        origin, issued = clock["origin"], clock["issued_at"]
        resolution = "scheduled_replay" if kind == "scheduled" else "manual_replay"
    audit = {
        "mode": clock["mode"],
        "resolution": resolution,
        "policy": clock,
        "policy_sha256": hashlib.sha256(canonical_bytes(clock)).hexdigest(),
        "physical_logical_date": str(logical_date) if logical_date is not None else None,
        "physical_data_interval_end": str(data_interval_end)
        if data_interval_end is not None
        else None,
    }
    return {
        "origin": origin,
        "issued_at": issued,
        "snapshot_id": snapshot,
        "use_snapshot_cutoff": historical_snapshot,
        "business_clock": audit,
    }
