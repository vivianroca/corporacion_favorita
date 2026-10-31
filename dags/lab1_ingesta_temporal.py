"""Sondeo cada tres horas y backfill manual por corte explícito."""

from datetime import timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

from reposicion import automatic, ingestion


@dag(
    dag_id="lab1_ingesta_temporal",
    schedule="0 */3 * * *",
    start_date=pendulum.datetime(2017, 1, 1, tz="America/Guatemala"),
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

    @task
    def procesar_pendientes():
        context = get_current_context()
        cutoff = context["data_interval_end"]
        if cutoff is None:
            raise ValueError("El ciclo automático requiere data_interval_end")
        return automatic.poll_cycle(
            **automatic.settings(), as_of=cutoff.isoformat(), cycle_id=context["run_id"]
        )

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

    @task
    def publicar_snapshot(plan_id):
        return ingestion.snapshot(ingestion.settings()["work_root"], plan_id)

    route = elegir_modo()
    plan = descubrir()
    route >> [plan, procesar_pendientes()]
    publicar_snapshot(validar(ingestar(plan)))


ingesta_temporal()
