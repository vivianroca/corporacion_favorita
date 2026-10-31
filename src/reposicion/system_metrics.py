"""Contexto oficial de MLflow para medir próximos entrenamientos en el host ejecutor."""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

import mlflow
import psutil
from mlflow import MlflowClient, system_metrics


@dataclass
class TrainingRun:
    client: MlflowClient
    run_id: str

    def log_results(self, parameters, metrics, artifacts):
        """Conserva métricas predictivas y todos los artefactos existentes del modelo."""
        self.client.log_param(self.run_id, "psutil_version", psutil.__version__)
        self.client.log_param(self.run_id, "system_metrics_sampling_interval_seconds", 1)
        self.client.set_tag(self.run_id, "system_metrics_scope", "training_host")
        self.client.set_tag(self.run_id, "wape_defined", str(metrics["wape"] is not None).lower())
        for key, value in parameters.items():
            self.client.log_param(self.run_id, key, str(value))
        for key, value in metrics.items():
            if value is not None:
                self.client.log_metric(self.run_id, key, value)
        for path in sorted(artifacts.iterdir()):
            if path.is_file():
                self.client.log_artifact(self.run_id, str(path))


@contextmanager
def training_run(uri, *, experiment_name, run_name):
    """Abre el run antes del trabajo y activa el muestreo nativo cada segundo."""
    if mlflow.active_run() is not None or os.environ.get("MLFLOW_RUN_ID"):
        raise RuntimeError("Finalice el run activo y quite MLFLOW_RUN_ID antes de entrenar")
    previous_uri = mlflow.get_tracking_uri()
    variables = (
        "MLFLOW_SYSTEM_METRICS_SAMPLING_INTERVAL",
        "MLFLOW_SYSTEM_METRICS_SAMPLES_BEFORE_LOGGING",
    )
    previous = {key: os.environ.get(key) for key in variables}
    try:
        mlflow.set_tracking_uri(uri)
        system_metrics.set_system_metrics_sampling_interval(1)
        system_metrics.set_system_metrics_samples_before_logging(1)
        experiment = mlflow.set_experiment(experiment_name)
        with mlflow.start_run(
            experiment_id=experiment.experiment_id, run_name=run_name, log_system_metrics=True
        ) as active:
            client = MlflowClient(tracking_uri=uri)
            started = perf_counter()
            try:
                yield TrainingRun(client, active.info.run_id)
            finally:
                client.log_metric(
                    active.info.run_id, "execution_duration_seconds", perf_counter() - started
                )
    finally:
        mlflow.set_tracking_uri(previous_uri)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
