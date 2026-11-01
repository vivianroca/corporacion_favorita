"""Seguimiento diario de pronósticos publicados, sin modificar predicciones."""

import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pendulum
import yaml
from airflow.sdk import dag, get_current_context, task

from reposicion.airflow_dependencies import FORECASTS, SALES
from reposicion.orchestration import authorized_forecasts, event_cutoff

CONFIG = yaml.safe_load(
    Path(
        os.environ.get(
            "LAB1_MONITORING_CONFIG", "/opt/lab1/forecast_project/configs/seguimiento.yaml"
        )
    ).read_text()
)


@dag(
    dag_id="lab1_seguimiento",
    schedule=FORECASTS | SALES,
    start_date=pendulum.parse(CONFIG["start_date"], tz=CONFIG["timezone"]),
    catchup=CONFIG["catchup"],
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["lab1", "seguimiento"],
    doc_md=__doc__,
)
def seguimiento():
    @task(inlets=[FORECASTS, SALES])
    def evaluar_publicaciones():
        context = get_current_context()
        conf = context["dag_run"].conf or {}
        known_forecasts = [e.extra for e in context["inlet_events"][FORECASTS]]
        known_sales = [e.extra for e in context["inlet_events"][SALES]]
        as_of = conf.get("as_of")
        run_type = context["dag_run"].run_type
        if as_of is None and getattr(run_type, "value", run_type) == "asset_triggered":
            notices = [
                e.extra
                for events in context.get("triggering_asset_events", {}).values()
                for e in events
            ]
            as_of = event_cutoff(notices + known_sales)
        if as_of is None:
            boundary = context.get("data_interval_end") or context.get("logical_date")
            if boundary is None:
                raise ValueError("El seguimiento manual requiere as_of con zona horaria")
            as_of = pendulum.instance(boundary).in_timezone("UTC").isoformat()
        work = os.environ.get("LAB1_WORK_ROOT", "/opt/lab1/operational")
        eligible = authorized_forecasts(work, known_forecasts)
        if conf.get("forecast_id"):
            if conf["forecast_id"] not in eligible:
                raise ValueError("Pronóstico sin confirmación exitosa ni registro histórico")
            eligible = [conf["forecast_id"]]
        args = [
            "/opt/lab1/inference/bin/python",
            "-m",
            "reposicion.monitoring",
            "--work-root",
            work,
            "--forecasts-root",
            work + "/forecasts",
            "--output-root",
            work + "/monitoring",
            "--contracts-path",
            "/opt/lab1/forecast_project/configs/contracts.yaml",
            "--as-of",
            as_of,
            "--uri",
            os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"),
        ]
        for key in ("snapshot_id",):
            if conf.get(key):
                args.extend(["--" + key.replace("_", "-"), str(conf[key])])
        evaluations = []
        for forecast_id in eligible:
            result = subprocess.run(
                args + ["--forecast-id", forecast_id],
                check=False,
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "PYTHONPATH": "/opt/lab1/forecast_project/src",
                    "MLFLOW_DISABLE_AGENT_HINT": "1",
                },
            )
            print(result.stderr)
            result.check_returncode()
            payload = json.loads(result.stdout)
            print(json.dumps(payload))
            evaluations.extend(
                {
                    "evaluation_id": x["publication_id"],
                    "mlflow_run_id": x["mlflow_run_id"],
                    "reused": x["reused"],
                }
                for x in payload["evaluations"]
            )
        return {"as_of": as_of, "eligible_forecasts": len(eligible), "evaluations": evaluations}

    evaluar_publicaciones()


seguimiento()
