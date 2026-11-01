"""Sondeo cada tres horas y backfill manual por corte explícito."""

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, get_current_context, task

from reposicion import automatic, ingestion
from reposicion.airflow_dependencies import (
    FORECAST_REQUEST_OUT,
    SALES_OUT,
    SNAPSHOT_OUT,
    emit_request,
    emit_snapshot,
)


@dag(
    dag_id="lab1_ingesta_temporal",
    schedule="0 */3 * * *",
    start_date=pendulum.parse(os.environ["LAB1_SCHEDULER_START"])
    if os.environ.get("LAB1_SCHEDULER_START")
    else pendulum.datetime(2017, 1, 1, tz="America/Guatemala"),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={"retries": 1, "retry_delay": timedelta(seconds=15)},
    tags=["lab1", "ingesta", "temporal"],
    doc_md=__doc__,
)
def ingesta_temporal():
    @task.branch
    def elegir_modo():
        conf = get_current_context()["dag_run"].conf or {}
        return "descubrir" if conf.get("as_of") else "procesar_pendientes"

    @task(outlets=[SNAPSHOT_OUT, SALES_OUT])
    def procesar_pendientes():
        context = get_current_context()
        cutoff = context["data_interval_end"]
        if cutoff is None:
            raise ValueError("El ciclo automático requiere data_interval_end")
        result = automatic.poll_cycle(
            **automatic.settings(),
            as_of=os.environ.get("LAB1_INGEST_AS_OF", cutoff.isoformat()),
            cycle_id=context["run_id"],
        )
        if result.get("publication_id"):
            work = automatic.settings()["work_root"]
            paths = list(Path(work).glob("automatic/*/publications/" + result["publication_id"]))
            if len(paths) != 1:
                raise ValueError("Publicación incremental ambigua")
            emit_snapshot(
                context,
                paths[0],
                work,
                {r["delivery_id"] for r in result["processed_files"] if r["applied"]},
            )
        return result

    @task
    def descubrir():
        config = ingestion.settings()
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        if not conf.get("as_of"):
            raise ValueError("Indicar as_of con zona horaria en la configuración del DAG run")
        return ingestion.discover(
            **config,
            as_of=conf["as_of"],
            reference_start=conf.get("reference_start"),
            reference_end=conf.get("reference_end"),
        )

    @task
    def ingestar(plan_id):
        config = ingestion.settings()
        return ingestion.ingest(config["source_root"], config["work_root"], plan_id)

    @task
    def validar(plan_id):
        return ingestion.validate(ingestion.settings()["work_root"], plan_id)

    @task(outlets=[SNAPSHOT_OUT, SALES_OUT, FORECAST_REQUEST_OUT])
    def publicar_snapshot(plan_id):
        work = ingestion.settings()["work_root"]
        result = ingestion.snapshot(work, plan_id)
        context = get_current_context()
        notice = emit_snapshot(context, Path(work) / "snapshots" / plan_id, work)
        emit_request(context, notice, (context["dag_run"].conf or {}).get("forecast_request"))
        return result

    route = elegir_modo()
    plan = descubrir()
    route >> [plan, procesar_pendientes()]
    publicar_snapshot(validar(ingestar(plan)))


ingesta_temporal()
