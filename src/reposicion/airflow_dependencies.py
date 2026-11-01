"""Assets nativos y emisores condicionales; solo se importa dentro de Airflow."""

from pathlib import Path

from airflow.sdk import Asset, AssetAlias

from reposicion.orchestration import forecast_notice, snapshot_notice

SNAPSHOTS = Asset("lab1.snapshots_validados", uri="lab1://ingesta/snapshots_validados")
SALES = Asset("lab1.ventas_evaluables", uri="lab1://ingesta/ventas_evaluables")
FORECASTS = Asset("lab1.pronosticos_publicados", uri="lab1://pronostico/publicaciones")
FORECAST_REQUESTS = Asset("lab1.pronostico_solicitado", uri="lab1://pronostico/solicitudes")
FORECAST_REQUEST_OUT = AssetAlias("lab1.solicitud_confirmada")
SNAPSHOT_OUT = AssetAlias("lab1.snapshot_confirmado")
SALES_OUT = AssetAlias("lab1.ventas_confirmadas")


def emit_snapshot(context, directory, work_root, applied_ids=None):
    notice = snapshot_notice(directory, Path(work_root) / "forecasts", applied_ids)
    context["outlet_events"][SNAPSHOT_OUT].add(SNAPSHOTS, extra=notice)
    if notice["affected_forecast_ids"]:
        context["outlet_events"][SALES_OUT].add(SALES, extra=notice)
    return notice


def emit_forecast(context, result):
    notice = forecast_notice(result["path"])
    context["outlet_events"][FORECASTS].extra = notice
    return notice


def emit_request(context, notice, request):
    """Solo una solicitud explícita sobre ingesta exitosa activa un pronóstico."""
    if not request:
        return
    if request.get("issued_at") != notice["as_of"] or not request.get("request_id"):
        raise ValueError("Solicitud incompatible con el corte del snapshot")
    payload = {
        **request,
        "snapshot_id": notice["snapshot_id"],
        "manifest_sha256": notice["manifest_sha256"],
    }
    context["outlet_events"][FORECAST_REQUEST_OUT].add(FORECAST_REQUESTS, extra=payload)
