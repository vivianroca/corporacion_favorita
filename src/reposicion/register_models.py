"""Publicar pipelines ya ajustados en Logged Models y Registry, sin entrenamiento."""

import argparse
import csv
import json
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

import joblib
import mlflow
import mlflow.pyfunc
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.entities import LoggedModelOutput
from mlflow.exceptions import MlflowException
from mlflow.models import Model, infer_signature
from threadpoolctl import threadpool_limits

from reposicion.contracts import Contracts
from reposicion.random_forest import SalesHistory
from reposicion.source_io import DeliveryCatalog, canonical_bytes, checksum
from reposicion.temporal_features import TemporalFeatures

NAMES = {
    "random_forest": "corporacion_favorita_random_forest",
    "hist_gradient_boosting": "corporacion_favorita_hist_gradient_boosting",
    "catboost": "corporacion_favorita_catboost",
}


def input_frame(folder, window, catalog, contracts):
    with (folder / "forecast.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    origin = date.fromisoformat(window["forecast_start"])
    past, _ = SalesHistory(catalog, contracts).window(
        origin - timedelta(days=28), origin - timedelta(days=1), window["issued_at"]
    )
    builder = TemporalFeatures(catalog, contracts)
    frame = pd.DataFrame(
        [
            builder.enrich(
                past,
                origin,
                date.fromisoformat(row["date"]),
                int(row["store_nbr"]),
                row["family"],
                window["issued_at"],
            )
            for row in rows
        ]
    )
    for column in frame.select_dtypes(include="number").columns:
        frame[column] = frame[column].astype(float)
    return frame, np.array([float(row["prediction"]) for row in rows])


def entries(temporal_root, catboost_root):
    for root in (Path(temporal_root), Path(catboost_root)):
        result = json.loads((root / "results.json").read_text())
        for window in result["windows"]:
            name = window.get("model", "catboost")
            if name in NAMES:
                yield name, window, root / f"window_{window['window_index']}" / name


def register(temporal_root, catboost_root, output, uri):
    client = mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri)
    previous_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    catalog, contracts = DeliveryCatalog("data/simulation"), Contracts("configs/contracts.yaml")
    requirements = [
        f"{name}=={version(name)}"
        for name in (
            "mlflow-skinny",
            "scikit-learn",
            "numpy",
            "scipy",
            "pandas",
            "catboost",
            "joblib",
            "cloudpickle",
            "PyYAML",
            "matplotlib",
            "psutil",
            "threadpoolctl",
        )
    ]
    registrations = []
    try:
        for name, window, folder in entries(temporal_root, catboost_root):
            registry_name, run_id = NAMES[name], window["run_id"]
            existing = [
                v
                for v in client.search_model_versions(f"name='{registry_name}'")
                if v.run_id == run_id and v.tags.get("feature_set") == "temporal_v2"
            ]
            if existing:
                registered = existing[0]
                if registered.status != "READY":
                    raise ValueError("Existe una versión que aún no está lista")
                registrations.append(
                    {
                        "name": registry_name,
                        "version": registered.version,
                        "model_id": registered.model_id
                        or registered.source.removeprefix("models:/"),
                        "run_id": run_id,
                        "source": registered.source,
                        "fold": window["window_index"],
                        "forecast_start": window["forecast_start"],
                    }
                )
                continue
            print(f"Empaquetando {name}, fold {window['window_index']}, sin fit", flush=True)
            run = client.get_run(run_id)
            frame, expected = input_frame(folder, window, catalog, contracts)
            pipeline = joblib.load(folder / "model.joblib")
            with threadpool_limits(limits=2):
                np.testing.assert_allclose(
                    pipeline.predict(frame), expected, rtol=1e-12, atol=1e-12
                )
            local = output / name / f"fold_{window['window_index']}"
            if not local.exists():
                mlflow.sklearn.save_model(
                    pipeline,
                    str(local),
                    serialization_format="cloudpickle",
                    signature=infer_signature(frame, expected),
                    input_example=frame.head(3),
                    code_paths=["src/reposicion"],
                    pip_requirements=requirements,
                    mlflow_model=Model(
                        run_id=run_id,
                        metadata={
                            "feature_set": "temporal_v2",
                            "forecast_start": window["forecast_start"],
                            "horizon_days": 7,
                            "registration_only": True,
                            "trained_pipeline_sha256": checksum(folder / "model.joblib"),
                        },
                    ),
                )
            with threadpool_limits(limits=2):
                restored = mlflow.pyfunc.load_model(str(local))
                np.testing.assert_allclose(
                    restored.predict(frame), expected, rtol=1e-12, atol=1e-12
                )
            model_name = registry_name + f"-temporal-v2-fold-{window['window_index']}"
            candidates = client.search_logged_models([run.info.experiment_id], max_results=1000)
            matching = [m for m in candidates if m.source_run_id == run_id and m.name == model_name]
            logged = (
                matching[0]
                if matching
                else client.create_logged_model(
                    experiment_id=run.info.experiment_id,
                    name=model_name,
                    source_run_id=run_id,
                    model_type=name,
                    params=run.data.params,
                    tags={
                        "feature_set": "temporal_v2",
                        "fold": str(window["window_index"]),
                        "forecast_start": window["forecast_start"],
                        "registration_only": "true",
                    },
                )
            )
            if str(logged.status) != "READY":
                specification = Model.load(str(local))
                specification.model_id = logged.model_id
                specification.save(str(local / "MLmodel"))
                client.log_model_artifacts(logged.model_id, str(local))
                client.finalize_logged_model(logged.model_id, "READY")
            for key in ("mae", "wape"):
                history = client.get_metric_history(run_id, key)
                metric = max(history, key=lambda m: (m.step, m.timestamp))
                # Mismo evento histórico: MLflow deduplica el run y lo vincula al nuevo modelo.
                client.log_metric(
                    run_id,
                    key,
                    metric.value,
                    timestamp=metric.timestamp,
                    step=metric.step,
                    model_id=logged.model_id,
                )
                assert [
                    (m.value, m.timestamp, m.step) for m in client.get_metric_history(run_id, key)
                ] == [(m.value, m.timestamp, m.step) for m in history]
            client.log_outputs(run_id, [LoggedModelOutput(logged.model_id, step=0)])
            try:
                client.get_registered_model(registry_name)
            except MlflowException as exc:
                if exc.error_code != "RESOURCE_DOES_NOT_EXIST":
                    raise
                client.create_registered_model(
                    registry_name,
                    description="Pipelines temporales v2 existentes, una versión por fold; sin promoción.",
                )
            registered = client.create_model_version(
                registry_name,
                source="models:/" + logged.model_id,
                run_id=run_id,
                model_id=logged.model_id,
                await_creation_for=60,
                tags={
                    "feature_set": "temporal_v2",
                    "fold": str(window["window_index"]),
                    "forecast_start": window["forecast_start"],
                    "issued_at": window["issued_at"],
                    "mae": str(run.data.metrics["mae"]),
                    "wape": str(run.data.metrics["wape"]),
                    "validation_only": "true",
                },
                description=f"Modelo ya entrenado, fold {window['window_index']}, corte {window['issued_at']}. Sin reentrenar ni asignar aliases.",
            )
            registrations.append(
                {
                    "name": registry_name,
                    "version": registered.version,
                    "model_id": logged.model_id,
                    "run_id": run_id,
                    "source": registered.source,
                    "fold": window["window_index"],
                    "forecast_start": window["forecast_start"],
                }
            )
            (output / "registrations.json").write_bytes(canonical_bytes(registrations))
            print(f"Registrado {registry_name} v{registered.version}", flush=True)
        (output / "registrations.json").write_bytes(canonical_bytes(registrations))
        return registrations
    finally:
        mlflow.set_tracking_uri(previous_uri)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal", default="reports/walk_forward/temporal_v2_january_2017")
    parser.add_argument("--catboost", default="reports/walk_forward/catboost_january_2017")
    parser.add_argument("--output", default="reports/model_registry/temporal_v2")
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    print(
        json.dumps(register(args.temporal, args.catboost, args.output, args.tracking_uri), indent=2)
    )


if __name__ == "__main__":
    main()
