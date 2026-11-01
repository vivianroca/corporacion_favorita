"""Arranque reproducible desde CSV; servicios y estado propios, sin entrenamiento."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yaml

from reposicion.forecast_clock import validate_window
from reposicion.ingestion import _verify_bundle
from reposicion.release import initialize, publish_next
from reposicion.source_io import (
    SOURCES,
    DeliveryCatalog,
    canonical_bytes,
    checksum,
    instant_text,
    parse_instant,
)
from reposicion.source_simulator import simulate

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ["apache/airflow:3.3.2-python3.12", "postgres:16", "ghcr.io/mlflow/mlflow:v3.17.2"]
DAGS = ["lab1_ingesta_temporal", "lab1_pronostico_reposicion", "lab1_seguimiento"]


def progress(message):
    print(message, flush=True)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_bytes(value))
    os.replace(temporary, path)


def code_identity(root):
    paths = []
    for directory, pattern in [
        ("src/reposicion", "*.py"),
        ("dags", "*.py"),
        ("configs", "*.yaml"),
        ("docker", "Dockerfile*"),
        ("docker", "*.lock"),
    ]:
        paths.extend((root / directory).glob(pattern))
    paths.append(root / "docker/init_airflow.py")
    return hashlib.sha256(
        canonical_bytes({str(p.relative_to(root)): checksum(p) for p in sorted(set(paths))})
    ).hexdigest()


def scenario(origin, issued_at, evaluated_at, catalog, model_metadata):
    """Fechas explícitas; no desplazar el corte para esconder datos tardíos."""
    day = date.fromisoformat(origin)
    issued = instant_text(parse_instant(issued_at or origin + "T12:00:00Z"))
    evaluated = instant_text(
        parse_instant(evaluated_at or str(day + timedelta(days=28)) + "T12:00:00Z")
    )
    dates = catalog.manifest["source_profiles"]["train"]["reference_dates"]
    clock = {
        "mode": "historical_replay",
        "origin": origin,
        "issued_at": issued,
        "data_start": min(dates),
        "data_end": max(dates),
        "snapshot_policy": "discover_at_cut",
        "snapshot_id": None,
        "replay_id": "bootstrap-" + origin,
    }
    config = {"timezone": "America/Guatemala", "simulation_calendar": clock}
    validate_window(origin, issued, config)
    if parse_instant(issued) < parse_instant(catalog.manifest["historical_at"]):
        raise ValueError("El corte precede a la carga histórica inicial configurada")
    last = model_metadata["runs"][-1]["params"]
    if last["training_end"] >= origin or parse_instant(last["evaluated_at"]) > parse_instant(
        issued
    ):
        raise ValueError("Champion todavía no disponible al corte solicitado")
    if parse_instant(evaluated) <= parse_instant(issued) or parse_instant(evaluated).astimezone(
        ZoneInfo("America/Guatemala")
    ).date() <= day + timedelta(days=6):
        raise ValueError("La evaluación requiere cerrar los siete días de pronóstico")
    known = {
        r["reference_date"]
        for r in catalog.available(issued, latest=True)
        if r["source"] == "train"
    }
    missing = [
        str(day - timedelta(days=i))
        for i in range(1, 29)
        if str(day - timedelta(days=i)) not in known
    ]
    if missing:
        raise ValueError("Historia de 28 días incompleta al corte: " + ", ".join(missing))
    actual = {
        r["reference_date"]
        for r in catalog.available(evaluated, latest=True)
        if r["source"] == "train"
    }
    missing_actual = [
        str(day + timedelta(days=i)) for i in range(7) if str(day + timedelta(days=i)) not in actual
    ]
    if missing_actual:
        raise ValueError(
            "Faltan entregas reales al corte de evaluación: " + ", ".join(missing_actual)
        )
    return {"origin": origin, "issued_at": issued, "evaluated_at": evaluated, "clock": clock}


def release_through(master, inbox, cutoff):
    """El publicador es el único escritor de la bandeja; conserva available_at."""
    catalog = DeliveryCatalog(master)
    ids = {
        r["delivery_id"]
        for r in catalog.records
        if parse_instant(r["available_at"]) <= parse_instant(cutoff)
        and (r["area"] == "source_inbox" or r["source"] == "stores")
    }
    records = {r["delivery_id"]: r for r in catalog.records}
    pending = list(ids)
    while pending:
        previous = records[pending.pop()].get("corrects")
        if previous and previous not in ids:
            if parse_instant(records[previous]["available_at"]) > parse_instant(cutoff):
                raise ValueError("Corrección anterior no disponible al corte")
            ids.add(previous)
            pending.append(previous)
    return publish_next(master, inbox, delivery_ids=sorted(ids))


def prepare_env(directory, project, airflow_port, mlflow_port):
    path = directory / ".env"
    expected = {
        "COMPOSE_PROJECT_NAME": project,
        "LAB1_AIRFLOW_PORT": str(airflow_port),
        "LAB1_MLFLOW_PORT": str(mlflow_port),
    }
    if path.exists():
        values = dict(
            line.split("=", 1)
            for line in path.read_text().splitlines()
            if line and not line.startswith("#")
        )
        if any(values.get(k) != v for k, v in expected.items()):
            raise ValueError("La instancia ya tiene otros puertos/proyecto; elegir otro --instance")
        return values
    for port in (airflow_port, mlflow_port):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    values = {
        **expected,
        "LAB1_SCHEDULER_START": datetime.now(UTC).isoformat(),
        "LAB1_POSTGRES_PASSWORD": secrets.token_hex(24),
        "LAB1_AIRFLOW_ADMIN_PASSWORD": secrets.token_hex(16),
        "LAB1_FERNET_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "LAB1_API_SECRET": secrets.token_urlsafe(32),
        "LAB1_JWT_SECRET": secrets.token_urlsafe(32),
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
    return values


def compose_document(root, directory, project, image, config, airflow_port, mlflow_port):
    """Reutiliza servicios existentes, pero ninguna red/base/volumen anterior."""
    document = yaml.safe_load((root / "docker/compose.yaml").read_text())
    document.pop("x-airflow", None)
    document["name"] = project
    for key in document["volumes"]:
        document["volumes"][key] = {"name": project + "_" + key}
    document["networks"]["internal"]["name"] = project + "_internal"
    for name, service in document["services"].items():
        if not name.startswith("airflow-"):
            continue
        service.pop("build", None)
        service["image"] = image
        service["environment"] = {
            **service["environment"],
            "LAB1_BOOTSTRAP_ENABLED": "true",
            "LAB1_INGEST_AS_OF": config["issued_at"],
            "LAB1_FORECAST_CONFIG": "/opt/lab1/bootstrap/pronostico.yaml",
            "LAB1_SCHEDULER_START": "${LAB1_SCHEDULER_START:?Falta activacion fisica}",
        }
        service["volumes"] = [
            {
                "type": "bind",
                "source": str(directory / "source"),
                "target": "/opt/lab1/source",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": str(directory / "inbox"),
                "target": "/opt/lab1/inbox",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": str(directory / "operational"),
                "target": "/opt/lab1/operational",
            },
            {
                "type": "bind",
                "source": str(directory / "pronostico.yaml"),
                "target": "/opt/lab1/bootstrap/pronostico.yaml",
                "read_only": True,
            },
            "airflow_logs:/opt/airflow/logs",
            "airflow_auth:/opt/airflow/auth",
        ]
    document["services"]["airflow-api"]["ports"] = [f"127.0.0.1:{airflow_port}:8080"]
    document["services"]["mlflow"]["ports"] = [f"127.0.0.1:{mlflow_port}:5000"]
    return document


def forecast_policy(base, config, result=None):
    """Fija únicamente un ID descubierto en esta ejecución, nunca uno preexistente requerido."""
    clock = dict(config["clock"])
    if result and result.get("scenario") == config:
        clock["snapshot_id"] = result["snapshot_id"]
    return {**base, "simulation_calendar": clock}


class Airflow:
    def __init__(self, uri, password):
        self.uri, self.password, self.token = uri, password, None

    def call(self, path, method="GET", body=None):
        if path != "/auth/token" and self.token is None:
            self.token = self.call(
                "/auth/token", "POST", {"username": "admin", "password": self.password}
            )["access_token"]
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(
            self.uri + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 401 and path != "/auth/token":
                self.token = None
                return self.call(path, method, body)
            raise

    def trigger(self, dag, run_id, conf):
        path = f"/api/v2/dags/{dag}/dagRuns"
        try:
            existing = self.call(path + "/" + quote(run_id, safe=""))
        except HTTPError as error:
            if error.code != 404:
                raise
            return self.call(
                path, "POST", {"dag_run_id": run_id, "logical_date": None, "conf": conf}
            )
        if existing["conf"] != conf:
            raise ValueError("DAG Run existente con otra configuración")
        return existing


def wait_until(check, description, timeout=1800):
    start, last_update = time.monotonic(), 0
    while time.monotonic() - start < timeout:
        result = check()
        if result:
            return result
        if time.monotonic() - last_update >= 30:
            progress("Esperando: " + description)
            last_update = time.monotonic()
        time.sleep(3)
    raise TimeoutError("Tiempo agotado: " + description)


def dag_success(api, dag, run_id):
    run = api.call(f"/api/v2/dags/{dag}/dagRuns/" + quote(run_id, safe=""))
    if run["state"] == "failed":
        raise RuntimeError(
            f"DAG fallido: {dag}/{run_id}; revisar logs de Airflow y reintentar limpiando tareas fallidas"
        )
    return run if run["state"] == "success" else None


def find_complete(work, config, model_run, code_hashes):
    for path in sorted((work / "replenishment").glob("*/manifest.json")):
        complete = _verify_bundle(path.parent)
        fid = complete["identity"]["forecast_publication_id"]
        forecast = _verify_bundle(work / "forecasts" / fid)
        identity = forecast["identity"]
        if (
            identity["origin"] == config["origin"]
            and parse_instant(identity["issued_at"]) == parse_instant(config["issued_at"])
            and identity["model_run_id"] == model_run
            and identity["code_sha256"] == code_hashes
        ):
            return {
                "forecast_id": fid,
                "complete_id": path.parent.name,
                "snapshot_id": identity["snapshot_id"],
            }
    return None


def evaluated_result(work, forecast_id, as_of):
    for path in sorted((work / "monitoring").glob("*/manifest.json")):
        manifest = _verify_bundle(path.parent)
        if manifest["identity"]["forecast_publication_id"] != forecast_id:
            continue
        lineage = json.loads((path.parent / "lineage.json").read_text())
        if parse_instant(lineage["evaluated_as_of"]) != parse_instant(as_of):
            continue
        metrics = json.loads((path.parent / "metrics.json").read_text())
        if metrics["evaluated_rows"] > 0 and metrics["pending_rows"] == 0:
            return {"evaluation_id": path.parent.name, "metrics": metrics}
    return None


def execute(args):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Ejecutar con Python 3.12 de .venv")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", args.instance):
        raise ValueError("--instance debe usar minúsculas/números/guiones, máximo 36 caracteres")
    root = ROOT
    missing = [s + ".csv" for s in SOURCES if not (root / "data/original" / (s + ".csv")).is_file()]
    if missing:
        raise ValueError("Faltan CSV en data/original/: " + ", ".join(missing))
    directory = root / "data/bootstrap" / args.instance
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return run_locked(args, directory)


def run_locked(args, directory):
    root, project = ROOT, "lab1-" + args.instance
    (directory / "logs").mkdir(exist_ok=True)

    def command(argv):
        with (directory / "logs/commands.log").open("a") as log:
            log.write("COMMAND " + " ".join(map(str, argv)) + "\n")
            log.flush()
            result = subprocess.run(
                list(map(str, argv)),
                check=False,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        if result.returncode:
            raise RuntimeError("Comando fallido; consultar " + str(directory / "logs/commands.log"))

    command(["docker", "info"])
    progress("Recuperando pesos y calibración desde DVC")
    command(
        [
            sys.executable,
            "-m",
            "dvc",
            "pull",
            "models/current.dvc",
            "models/champion_restore.dvc",
            "--remote",
            "google_drive",
        ]
    )
    from reposicion.champion_restore import read_json, restore, verify_bundle

    verify_bundle(root / "models/champion_restore", root)
    progress("Preparando simulación determinista desde los cinco CSV")
    manifest = simulate(
        root / "data/original",
        directory / "source",
        root / "configs/contracts.yaml",
        root / "configs/availability.yaml",
    )
    catalog = DeliveryCatalog(directory / "source")
    metadata = read_json(root / "models/champion_restore/metadata.json")
    config = scenario(args.origin, args.issued_at, args.evaluated_at, catalog, metadata)
    marker = directory / "scenario.json"
    if marker.exists() and json.loads(marker.read_text()) != config:
        raise ValueError(
            "La instancia está fijada a otro escenario; elegir otro --instance y puertos"
        )
    write_json(marker, config)
    initialize(directory / "source", directory / "inbox", project)
    (directory / "operational").mkdir(exist_ok=True)
    env = prepare_env(directory, project, args.airflow_port, args.mlflow_port)
    identity = code_identity(root)
    image = "lab1-bootstrap-airflow:" + identity[:16]
    prior = read_json(directory / "result.json") if (directory / "result.json").exists() else None
    forecast_config = forecast_policy(
        yaml.safe_load((root / "configs/pronostico.yaml").read_text()), config, prior
    )
    (directory / "pronostico.yaml").write_text(yaml.safe_dump(forecast_config, sort_keys=False))
    compose_path = directory / "compose.yaml"
    compose_path.write_text(
        yaml.safe_dump(
            compose_document(
                root, directory, project, image, config, args.airflow_port, args.mlflow_port
            ),
            sort_keys=False,
        )
    )
    compose = ["docker", "compose", "--env-file", directory / ".env", "-f", compose_path]
    command([*compose, "config", "--quiet"])
    for official in IMAGES:
        if subprocess.run(
            ["docker", "image", "inspect", official],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode:
            command(["docker", "pull", official])
    if subprocess.run(
        ["docker", "image", "inspect", image],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode:
        progress("Construyendo imagen independiente de Airflow e inferencia")
        command(
            [
                "docker",
                "build",
                "--pull=false",
                "-f",
                "docker/Dockerfile.bootstrap",
                "-t",
                image,
                ".",
            ]
        )
    command([*compose, "up", "-d", "--no-build", "--pull", "never", "postgres", "mlflow"])
    mlflow_uri = f"http://localhost:{args.mlflow_port}"

    def health():
        try:
            with urlopen(mlflow_uri + "/health", timeout=5) as response:
                return response.status == 200
        except OSError:
            return False

    wait_until(health, "MLflow saludable", args.timeout)
    progress("Restaurando Champion y residuos, sin entrenamiento")
    restored = restore(root / "models/champion_restore", mlflow_uri, root, directory / "locks")
    command([*compose, "up", "-d", "--no-build", "--pull", "never"])
    api = Airflow(f"http://localhost:{args.airflow_port}", env["LAB1_AIRFLOW_ADMIN_PASSWORD"])

    def ready():
        try:
            return set(DAGS) <= {d["dag_id"] for d in api.call("/api/v2/dags?limit=100")["dags"]}
        except OSError:
            return False

    wait_until(ready, "API de Airflow y tres DAGs importados", args.timeout)
    for dag in DAGS:
        api.call("/api/v2/dags/" + dag, "PATCH", {"is_paused": False})
    base = {
        "generation": manifest["generation_id"],
        "model_bundle": verify_bundle(root / "models/champion_restore", root)["bundle_id"],
        "code": identity,
        "config": config,
    }
    request_id = hashlib.sha256(canonical_bytes(base)).hexdigest()
    historic_id = (
        "bootstrap-historico-"
        + hashlib.sha256(
            (
                manifest["generation_id"]
                + "".join(
                    checksum(root / "src/reposicion" / p)
                    for p in ("ingestion.py", "contracts.py", "source_io.py")
                )
            ).encode()
        ).hexdigest()[:24]
    )
    progress("Ingestando y validando la carga histórica inicial")
    release_through(directory / "source", directory / "inbox", manifest["historical_at"])
    api.trigger(DAGS[0], historic_id, {"as_of": manifest["historical_at"]})
    historical = wait_until(
        lambda: dag_success(api, DAGS[0], historic_id), "carga histórica inicial", args.timeout
    )
    progress("Solicitando snapshot y pronóstico para " + args.origin)
    release_through(directory / "source", directory / "inbox", config["issued_at"])
    request = {
        "request_id": request_id,
        "origin": config["origin"],
        "issued_at": config["issued_at"],
        "model_version": restored["version"],
    }
    conf = {
        "as_of": config["issued_at"],
        "reference_start": str(date.fromisoformat(args.origin) - timedelta(days=28)),
        "reference_end": str(date.fromisoformat(args.origin) + timedelta(days=6)),
        "forecast_request": request,
    }
    snapshot_run = "bootstrap-corte-" + request_id[:24]
    api.trigger(DAGS[0], snapshot_run, conf)
    snapshot = wait_until(
        lambda: dag_success(api, DAGS[0], snapshot_run), "snapshot del corte", args.timeout
    )
    code_hashes = {p.name: checksum(p) for p in sorted((root / "src/reposicion").glob("*.py"))}
    work = directory / "operational"
    complete = wait_until(
        lambda: find_complete(
            work, config, restored["run_mapping"][metadata["source_run_id"]], code_hashes
        ),
        "pronóstico y pedidos por Asset",
        args.timeout,
    )
    # Evita ambigüedad si después el ledger publica otro snapshot al mismo corte.
    # El usuario nunca tiene que proporcionar este ID, derivado del DAG 1.
    pinned = forecast_policy(
        forecast_config, config, {"scenario": config, "snapshot_id": complete["snapshot_id"]}
    )
    (directory / "pronostico.yaml").write_text(yaml.safe_dump(pinned, sort_keys=False))
    progress("Liberando reales y correcciones al corte de evaluación")
    release_through(directory / "source", directory / "inbox", config["evaluated_at"])
    actual_run = "bootstrap-reales-" + request_id[:24]
    api.trigger(
        DAGS[0],
        actual_run,
        {
            "as_of": config["evaluated_at"],
            "reference_start": args.origin,
            "reference_end": str(date.fromisoformat(args.origin) + timedelta(days=6)),
        },
    )
    actuals = wait_until(
        lambda: dag_success(api, DAGS[0], actual_run), "ventas reales y Asset", args.timeout
    )
    evaluation = wait_until(
        lambda: evaluated_result(work, complete["forecast_id"], config["evaluated_at"]),
        "seguimiento automático completo",
        args.timeout,
    )

    def finished_consumers():
        current = {
            dag: api.call(f"/api/v2/dags/{dag}/dagRuns?limit=100")["dag_runs"] for dag in DAGS
        }
        successful = all(
            any(
                r["run_type"] == "asset_triggered" and r["state"] == "success" for r in current[dag]
            )
            for dag in DAGS[1:]
        )
        active = any(r["state"] in {"queued", "running"} for dag in DAGS[1:] for r in current[dag])
        return current if successful and not active else None

    runs = wait_until(finished_consumers, "DAGs consumidores exitosos por Assets", args.timeout)
    report = {
        "schema_version": 1,
        "project": project,
        "image": image,
        "request_id": request_id,
        "scenario": config,
        "generation_id": manifest["generation_id"],
        "restored_model": restored,
        **complete,
        **evaluation,
        "ingestion_runs": [historical["dag_run_id"], snapshot["dag_run_id"], actuals["dag_run_id"]],
        "dag_runs": runs,
        "trained": False,
    }
    write_json(directory / ("result-" + request_id[:24] + ".json"), report)
    write_json(directory / "result.json", report)
    progress("Bootstrap completo: " + str(directory / "result.json"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--issued-at")
    parser.add_argument("--evaluated-at")
    parser.add_argument("--instance", default="repro")
    parser.add_argument("--airflow-port", type=int, default=8083)
    parser.add_argument("--mlflow-port", type=int, default=5013)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        result = execute(args)
    except (ValueError, RuntimeError, OSError, TimeoutError) as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("project", "forecast_id", "complete_id", "evaluation_id", "metrics")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
