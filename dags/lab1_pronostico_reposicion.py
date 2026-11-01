"""Pronóstico semanal: espera un snapshot validado y confirmado por su Asset."""

import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pendulum
import yaml
from airflow.sdk import dag, get_current_context, task
from airflow.sdk.bases.sensor import PokeReturnValue

from reposicion.airflow_dependencies import FORECASTS, SNAPSHOTS, emit_forecast
from reposicion.forecast_clock import resolve_request, validate_window

CONFIG = yaml.safe_load(
    Path(
        os.environ.get("LAB1_FORECAST_CONFIG", "/opt/lab1/forecast_project/configs/pronostico.yaml")
    ).read_text()
)


def execute(module, args):
    result = subprocess.run(
        [
            os.environ.get("LAB1_FORECAST_PYTHON", "/opt/lab1/inference/bin/python"),
            "-m",
            module,
            *args,
        ],
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
    return json.loads(result.stdout)


def request(context):
    return resolve_request(
        CONFIG,
        context["dag_run"].run_type,
        context["dag_run"].conf or {},
        logical_date=context.get("logical_date"),
        data_interval_end=context.get("data_interval_end"),
    )


@dag(
    dag_id="lab1_pronostico_reposicion",
    schedule=os.environ.get("LAB1_FORECAST_SCHEDULE", CONFIG["schedule"]),
    start_date=pendulum.parse(CONFIG["start_date"], tz=CONFIG["timezone"]),
    catchup=CONFIG["catchup"],
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["lab1", "pronostico", "champion"],
    doc_md=__doc__,
)
def pronostico_reposicion():
    @task.sensor(
        inlets=[SNAPSHOTS],
        mode="reschedule",
        poke_interval=30,
        timeout=CONFIG.get("snapshot_wait_seconds", 900),
    )
    def esperar_snapshot():
        context = get_current_context()
        clock = request(context)
        print("Reloj de negocio explícito: " + json.dumps(clock))
        args = [
            "prepare",
            "--work-root",
            os.environ.get("LAB1_WORK_ROOT", "/opt/lab1/operational"),
            "--contracts-path",
            "/opt/lab1/forecast_project/configs/contracts.yaml",
            "--origin",
            clock["origin"],
            "--issued-at",
            clock["issued_at"],
        ]
        if clock["use_snapshot_cutoff"]:
            args.append("--use-snapshot-cutoff")
        if clock["snapshot_id"]:
            args.extend(["--snapshot-id", str(clock["snapshot_id"])])
        plan = execute("reposicion.orchestration", args)
        if not plan["ready"]:
            print(plan)
            return PokeReturnValue(False)
        validate_window(plan["origin"], plan["issued_at"], CONFIG)
        plan["business_clock"] = {
            **clock["business_clock"],
            "resolved_origin": plan["origin"],
            "resolved_issued_at": plan["issued_at"],
            "resolved_snapshot_id": plan["snapshot_id"],
        }
        confirmed = any(
            e.extra.get("snapshot_id") == plan["snapshot_id"]
            and e.extra.get("manifest_sha256") == plan["manifest_sha256"]
            for e in context["inlet_events"][SNAPSHOTS]
        )
        if not confirmed:
            print("Esperando confirmación exitosa del Asset del snapshot")
        return PokeReturnValue(confirmed, plan if confirmed else None)

    @task(inlets=[SNAPSHOTS])
    def generar_publicacion(plan):
        conf = get_current_context()["dag_run"].conf or {}
        work = os.environ.get("LAB1_WORK_ROOT", "/opt/lab1/operational")
        args = [
            "--work-root",
            work,
            "--output-root",
            os.environ.get("LAB1_FORECAST_OUTPUT", work + "/forecasts"),
            "--origin",
            plan["origin"],
            "--issued-at",
            plan["issued_at"],
            "--snapshot-id",
            plan["snapshot_id"],
            "--uri",
            os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"),
            "--contracts-path",
            "/opt/lab1/forecast_project/configs/contracts.yaml",
        ]
        if conf.get("model_version") is not None:
            args.extend(["--model-version", str(conf["model_version"])])
        return execute("reposicion.forecast_publication", args)

    @task
    def calcular_pedidos(result):
        conf = get_current_context()["dag_run"].conf or {}
        work = os.environ.get("LAB1_WORK_ROOT", "/opt/lab1/operational")
        config_root = Path("/opt/lab1/forecast_project/configs")
        costs = Path(
            conf.get(
                "costs_path", os.environ.get("LAB1_COSTS_CONFIG", str(config_root / "costs.yaml"))
            )
        ).resolve()
        if not any(
            costs.is_relative_to(root.resolve()) for root in [config_root, Path(work) / "costs"]
        ):
            raise ValueError("Usar costos de configs o del archivo de políticas de lab1")
        return execute(
            "reposicion.orders",
            [
                "--forecast-dir",
                result["path"],
                "--costs",
                str(costs),
                "--output-root",
                os.environ.get("LAB1_ORDERS_OUTPUT", work + "/orders"),
            ],
        )

    @task(inlets=[SNAPSHOTS], outlets=[FORECASTS])
    def confirmar_publicacion(result, orders, plan):
        context = get_current_context()
        work = os.environ.get("LAB1_WORK_ROOT", "/opt/lab1/operational")
        complete = execute(
            "reposicion.replenishment_publication",
            [
                "--forecast-dir",
                result["path"],
                "--orders-dir",
                orders["path"],
                "--output-root",
                os.environ.get("LAB1_REPLENISHMENT_OUTPUT", work + "/replenishment"),
            ],
        )
        notice = emit_forecast(context, result)
        notice.update(
            {
                "status": "complete",
                "business_clock": plan["business_clock"],
                "complete_publication_id": complete["publication_id"],
                "complete_path": complete["path"],
                "complete_manifest_sha256": complete["complete_manifest_sha256"],
                "orders_publication_id": complete["orders_publication_id"],
                "costs_schema_version": complete["costs_schema_version"],
                "costs_version": complete["costs_version"],
                "inventory_assumptions_sha256": complete["inventory_assumptions_sha256"],
                "order_rows": complete["order_rows"],
            }
        )
        context["outlet_events"][FORECASTS].extra = notice
        return {**notice, "complete_reused": complete["reused"]}

    plan = esperar_snapshot()
    forecast = generar_publicacion(plan)
    confirmar_publicacion(forecast, calcular_pedidos(forecast), plan)


pronostico_reposicion()
