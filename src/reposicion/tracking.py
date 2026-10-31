"""Cliente REST mínimo para el MLflow existente, sin dependencias adicionales."""

import json
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


def log_baseline(uri, parameters, metrics, artifacts):
    return log_experiment(
        uri,
        parameters,
        metrics,
        artifacts,
        experiment_name="corporacion_favorita-baselines",
        run_name="weekly-baseline-" + parameters["forecast_start"],
    )


def log_experiment(uri, parameters, metrics, artifacts, *, experiment_name, run_name):
    """Registra un experimento real y artefactos planos sin crear aliases de modelos."""
    uri = uri.rstrip("/")
    if urlsplit(uri).scheme not in {"http", "https"}:
        raise ValueError("MLflow requiere una dirección HTTP(S)")

    def request(path, value=None, method=None):
        data = json.dumps(value).encode() if value is not None else None
        req = Request(
            uri + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    name = experiment_name
    try:
        experiment = request(
            "/api/2.0/mlflow/experiments/get-by-name?" + urlencode({"experiment_name": name})
        )["experiment"]
        experiment_id = experiment["experiment_id"]
    except HTTPError as error:
        body = json.loads(error.read())
        if body.get("error_code") != "RESOURCE_DOES_NOT_EXIST":
            raise
        experiment_id = request("/api/2.0/mlflow/experiments/create", {"name": name})[
            "experiment_id"
        ]
    now = int(time.time() * 1000)
    run = request(
        "/api/2.0/mlflow/runs/create",
        {
            "experiment_id": experiment_id,
            "start_time": now,
            "tags": [
                {
                    "key": "mlflow.runName",
                    "value": run_name,
                }
            ],
        },
    )["run"]
    run_id = run["info"]["run_id"]
    try:
        request(
            "/api/2.0/mlflow/runs/log-batch",
            {
                "run_id": run_id,
                "params": [{"key": k, "value": str(v)} for k, v in parameters.items()],
                "metrics": [
                    {"key": k, "value": v, "timestamp": now, "step": 0}
                    for k, v in metrics.items()
                    if v is not None
                ],
                "tags": [
                    {"key": "wape_defined", "value": str(metrics["wape"] is not None).lower()}
                ],
            },
        )
        artifact_uri = run["info"]["artifact_uri"]
        if not artifact_uri.startswith("mlflow-artifacts:/"):
            raise ValueError("Se requiere el proxy de artefactos del MLflow existente")
        base = "/api/2.0/mlflow-artifacts/artifacts/" + artifact_uri.split(":", 1)[1].lstrip("/")
        for path in sorted(artifacts.iterdir()):
            req = Request(
                uri + base.rstrip("/") + "/" + quote(path.name),
                data=path.read_bytes(),
                method="PUT",
                headers={"Content-Type": "application/octet-stream"},
            )
            with urlopen(req, timeout=60) as response:
                response.read()
        request(
            "/api/2.0/mlflow/runs/update",
            {"run_id": run_id, "status": "FINISHED", "end_time": int(time.time() * 1000)},
        )
    except Exception:
        request(
            "/api/2.0/mlflow/runs/update",
            {"run_id": run_id, "status": "FAILED", "end_time": int(time.time() * 1000)},
        )
        raise
    return run_id
