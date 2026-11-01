"""Assets nativos y emisores condicionales; solo se importa dentro de Airflow."""

from pathlib import Path

from airflow.sdk import Asset, AssetAlias

from reposicion.orchestration import forecast_notice, snapshot_notice

SNAPSHOTS = Asset("lab1.snapshots_validados", uri="lab1://ingesta/snapshots_validados")
SALES = Asset("lab1.ventas_evaluables", uri="lab1://ingesta/ventas_evaluables")
FORECASTS = Asset("lab1.pronosticos_publicados", uri="lab1://pronostico/publicaciones")
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
