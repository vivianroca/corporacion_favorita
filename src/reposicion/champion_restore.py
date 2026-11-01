"""Exporta y restaura el Champion existente y sus residuos; nunca llama a fit."""

import argparse
import csv
import fcntl
import hashlib
import json
import shutil
import tempfile
from contextlib import contextmanager
from datetime import date, timedelta
from importlib.metadata import version as package_version
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.exceptions import MlflowException
from mlflow.models import Model, infer_signature
from threadpoolctl import threadpool_limits

from reposicion.source_io import canonical_bytes, checksum
from reposicion.uncertainty import artifact_bytes, intervals, residual_pools

NAME = "corporacion_favorita_random_forest"
MODEL_PATH = "models/current/random_forest/fold_4/model.joblib"
FILES = {"metadata.json", "probe.json"} | {f"calibration/fold_{i}.csv" for i in range(1, 5)}
PACKAGES = (
    "mlflow-skinny",
    "scikit-learn",
    "numpy",
    "scipy",
    "pandas",
    "joblib",
    "cloudpickle",
    "PyYAML",
    "threadpoolctl",
    "psutil",
    "matplotlib",
)


def read_json(path):
    return json.loads(Path(path).read_text())


def export_bundle(output, uri="http://localhost:5011", project_root="."):
    """Lee el servidor fuente y publica un paquete inmutable verificable."""
    root, output = Path(project_root).resolve(), Path(output).resolve()
    if output.exists():
        return verify_bundle(output, root)["bundle_id"]
    client = mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri)
    champion = client.get_model_version_by_alias(NAME, "champion")
    source = client.get_run(champion.run_id)
    model = root / MODEL_PATH
    if checksum(model) != champion.tags["champion.pipeline_sha256"]:
        raise ValueError("Pesos DVC distintos del Champion fuente")
    runs = [
        r
        for r in client.search_runs(
            [source.info.experiment_id],
            filter_string="params.walk_forward_id = '"
            + source.data.params["walk_forward_id"]
            + "'",
            max_results=1000,
        )
        if r.data.params.get("model") == "random_forest" and "window_index" in r.data.params
    ]
    runs.sort(key=lambda r: int(r.data.params["window_index"]))
    if [r.data.params["window_index"] for r in runs] != ["1", "2", "3", "4"]:
        raise ValueError("Se requieren exactamente cuatro folds originales")
    if any(r.info.status != "FINISHED" for r in runs) or source.info.run_id != runs[-1].info.run_id:
        raise ValueError("Champion/folds fuente incompatibles")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-export-", dir=output.parent) as temporary:
        stage = Path(temporary) / "bundle"
        (stage / "calibration").mkdir(parents=True)
        records = []
        for run in runs:
            fold = run.data.params["window_index"]
            path = f"calibration/fold_{fold}.csv"
            (stage / path).write_bytes(artifact_bytes(uri, run, "evaluation.csv"))
            records.append(
                {
                    "source_run_id": run.info.run_id,
                    "params": dict(run.data.params),
                    "metrics": {
                        k: run.data.metrics[k]
                        for k in ("mae", "wape", "observations", "actual_sales_sum")
                    },
                    "evaluation": path,
                }
            )
        local = mlflow.artifacts.download_artifacts(
            artifact_uri=client.get_logged_model(
                champion.source.removeprefix("models:/")
            ).artifact_location,
            tracking_uri=uri,
            dst_path=str(Path(temporary) / "model"),
        )
        example = read_json(Path(local) / "input_example.json")
        frame = pd.DataFrame(example["data"], columns=example["columns"])
        with threadpool_limits(limits=2):
            expected = mlflow.pyfunc.load_model(local).predict(frame)
            np.testing.assert_allclose(
                joblib.load(model).predict(frame), expected, rtol=1e-12, atol=1e-12
            )
        (stage / "probe.json").write_bytes(
            canonical_bytes({"input": example, "prediction": list(expected)})
        )
        metadata = {
            "model_name": NAME,
            "source_version": champion.version,
            "source_run_id": champion.run_id,
            "source_model_uri": champion.source,
            "source_experiment": client.get_experiment(source.info.experiment_id).name,
            "model_tags": {
                k: v
                for k, v in champion.tags.items()
                if k.startswith("champion.") or k in {"feature_set", "validation_only", "fold"}
            },
            "model": {
                "path": MODEL_PATH,
                "sha256": checksum(model),
                "dvc_pointer": "models/current.dvc",
                "dvc_pointer_sha256": checksum(root / "models/current.dvc"),
            },
            "packages": {p: package_version(p) for p in PACKAGES},
            "runs": records,
        }
        (stage / "metadata.json").write_bytes(canonical_bytes(metadata))
        identity = {"schema_version": 1, "files": {p: checksum(stage / p) for p in sorted(FILES)}}
        manifest = {**identity, "bundle_id": hashlib.sha256(canonical_bytes(identity)).hexdigest()}
        (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
        verify_bundle(stage, root)
        stage.rename(output)
    return manifest["bundle_id"]


def verify_bundle(bundle, project_root="."):
    """Valida todo antes de deserializar pesos o escribir en MLflow."""
    bundle, root = Path(bundle), Path(project_root)
    manifest = read_json(bundle / "manifest.json")
    identity = {k: manifest[k] for k in ("schema_version", "files")}
    if manifest["schema_version"] != 1 or set(manifest["files"]) != FILES:
        raise ValueError("Inventario del paquete incompatible")
    if hashlib.sha256(canonical_bytes(identity)).hexdigest() != manifest["bundle_id"]:
        raise ValueError("Identidad del paquete inválida")
    actual = {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file()}
    if actual != FILES | {"manifest.json"} or any(p.is_symlink() for p in bundle.rglob("*")):
        raise ValueError("Archivos adicionales o enlaces en paquete")
    for path, digest in manifest["files"].items():
        if checksum(bundle / path) != digest:
            raise ValueError("Checksum de paquete incompatible: " + path)
    metadata = read_json(bundle / "metadata.json")
    model = metadata["model"]
    if model["path"] != MODEL_PATH or model["dvc_pointer"] != "models/current.dvc":
        raise ValueError("Ruta del modelo no autorizada")
    if (
        checksum(root / MODEL_PATH) != model["sha256"]
        or checksum(root / "models/current.dvc") != model["dvc_pointer_sha256"]
    ):
        raise ValueError("Pesos o puntero DVC incompatibles")
    runs = metadata["runs"]
    if metadata["model_name"] != NAME or [r["params"]["window_index"] for r in runs] != [
        "1",
        "2",
        "3",
        "4",
    ]:
        raise ValueError("Folds incompatibles")
    if metadata["source_run_id"] != runs[-1]["source_run_id"]:
        raise ValueError("Champion no corresponde al último fold")
    for i, run in enumerate(runs, 1):
        if (
            run["evaluation"] != f"calibration/fold_{i}.csv"
            or run["params"]["model"] != "random_forest"
            or run["params"]["feature_set"] != "temporal_v2"
        ):
            raise ValueError("Calibración incompatible")
        if run["params"]["walk_forward_id"] != runs[-1]["params"]["walk_forward_id"]:
            raise ValueError("Grupos de validación distintos")
    windows = []
    for run in runs:
        with (bundle / run["evaluation"]).open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != run["metrics"]["observations"]:
            raise ValueError("Cantidad de residuos incompatible")
        windows.append((run["params"], rows))
    origin = date.fromisoformat(runs[-1]["params"]["forecast_end"]) + timedelta(days=1)
    pools = residual_pools(windows, origin, runs[-1]["params"]["evaluated_at"])
    for errors in pools.values():
        intervals(0, errors)  # Verifica soporte mínimo y finitud, sin ajustar nada.
    return manifest


@contextmanager
def restore_lock(uri, lock_root):
    """Serializa invocaciones en este host; compartir lock_root entre procesos."""
    lock_root = Path(lock_root)
    lock_root.mkdir(parents=True, exist_ok=True)
    with (lock_root / (hashlib.sha256(uri.encode()).hexdigest() + ".lock")).open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def download_bytes(client, run_id, artifact):
    with tempfile.TemporaryDirectory(prefix="restore-check-") as temporary:
        return Path(client.download_artifacts(run_id, artifact, temporary)).read_bytes()


def package_model(bundle, project_root, destination, run_id):
    metadata, probe = (
        read_json(Path(bundle) / "metadata.json"),
        read_json(Path(bundle) / "probe.json"),
    )
    frame = pd.DataFrame(probe["input"]["data"], columns=probe["input"]["columns"])
    pipeline = joblib.load(Path(project_root) / MODEL_PATH)
    with threadpool_limits(limits=2):
        np.testing.assert_allclose(
            pipeline.predict(frame), probe["prediction"], rtol=1e-12, atol=1e-12
        )
    mlflow.sklearn.save_model(
        pipeline,
        str(destination),
        serialization_format="cloudpickle",
        signature=infer_signature(frame, np.asarray(probe["prediction"])),
        input_example=frame,
        code_paths=[str(Path(__file__).parent)],
        pip_requirements=[f"{p}=={v}" for p, v in metadata["packages"].items()],
        mlflow_model=Model(
            run_id=run_id,
            metadata={"restoration_only": True, "pipeline_sha256": metadata["model"]["sha256"]},
        ),
    )


def restore(bundle, uri, project_root=".", lock_root="reports/champion_restore/locks"):
    manifest = verify_bundle(bundle, project_root)
    metadata = read_json(Path(bundle) / "metadata.json")
    for name, expected in metadata["packages"].items():
        if package_version(name) != expected:
            raise ValueError(f"Dependencia incompatible: {name}; se requiere {expected}")
    client = mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri)
    with restore_lock(uri, lock_root):
        return _restore(client, bundle, metadata, manifest, project_root)


def _restore(client, bundle, metadata, manifest, project_root):
    bundle, bid = Path(bundle), manifest["bundle_id"]
    # Nunca sustituir silenciosamente una promoción o un modelo ajeno.
    try:
        registered = client.get_registered_model(NAME)
    except MlflowException as exc:
        if exc.error_code != "RESOURCE_DOES_NOT_EXIST":
            raise
        registered = None
    if registered:
        versions = list(client.search_model_versions(f"name='{NAME}'"))
        if any(v.tags.get("restore.bundle_id") != bid for v in versions):
            raise ValueError("Registry contiene versiones ajenas; usar MLflow vacío")
    experiment_name = "corporacion_favorita-champion-restaurado-" + bid[:12]
    experiment = client.get_experiment_by_name(experiment_name)
    eid = experiment.experiment_id if experiment else client.create_experiment(experiment_name)
    mappings = {}
    for record in metadata["runs"]:
        source_id = record["source_run_id"]
        found = client.search_runs(
            [eid], filter_string=f"tags.`restore.source_run_id` = '{source_id}'", max_results=1000
        )
        if len(found) > 1:
            raise ValueError("Restauraciones ambiguas del run fuente")
        run = (
            found[0]
            if found
            else client.create_run(
                eid,
                tags={
                    "restore.bundle_id": bid,
                    "restore.source_run_id": source_id,
                    "restore.source_experiment": metadata["source_experiment"],
                    "restoration_only": "true",
                    "mlflow.runName": "restaurado-random-forest-fold-"
                    + record["params"]["window_index"],
                },
            )
        )
        rid = run.info.run_id
        if run.data.tags.get("restore.complete") != "true":
            for key, value in record["params"].items():
                client.log_param(rid, key, value)
            for key, value in record["metrics"].items():
                if key not in run.data.metrics:
                    client.log_metric(rid, key, value)
            # El consumidor existente espera exactamente evaluation.csv.
            # Se preservan nombres locales de fold en DVC, sin duplicar su contenido.
            with tempfile.TemporaryDirectory(prefix="restore-evaluation-") as temporary:
                path = Path(temporary) / "evaluation.csv"
                shutil.copyfile(bundle / record["evaluation"], path)
                client.log_artifact(rid, str(path))
            client.set_terminated(rid, status="FINISHED")
            client.set_tag(rid, "restore.complete", "true")
        restored = client.get_run(rid)
        if (
            restored.info.status != "FINISHED"
            or any(restored.data.params.get(k) != v for k, v in record["params"].items())
            or any(restored.data.metrics.get(k) != v for k, v in record["metrics"].items())
        ):
            raise ValueError("Run restaurado incompatible")
        if (
            download_bytes(client, rid, "evaluation.csv")
            != (bundle / record["evaluation"]).read_bytes()
        ):
            raise ValueError("Residuos restaurados incompatibles")
        mappings[source_id] = rid
    rid = mappings[metadata["source_run_id"]]
    versions = list(client.search_model_versions(f"name='{NAME}'")) if registered else []
    if len(versions) > 1:
        raise ValueError("Versiones restauradas ambiguas")
    if versions:
        model_version = versions[0]
        if model_version.run_id != rid or model_version.status != "READY":
            raise ValueError("Versión restaurada incompatible")
    else:
        model_hash = client.get_run(rid).data.tags.get("restore.serialized_sha256")
        if not model_hash:
            with tempfile.TemporaryDirectory(prefix="restore-model-") as temporary:
                path = Path(temporary) / "model"
                package_model(bundle, project_root, path, rid)
                client.log_artifacts(rid, str(path), artifact_path="model")
                model_hash = checksum(path / "model.pkl")
                client.set_tag(rid, "restore.serialized_sha256", model_hash)
        if not registered:
            client.create_registered_model(NAME)
        model_version = client.create_model_version(
            NAME,
            source=f"runs:/{rid}/model",
            run_id=rid,
            await_creation_for=60,
            tags={
                **metadata["model_tags"],
                "restore.bundle_id": bid,
                "restore.source_run_id": metadata["source_run_id"],
                "restore.source_version": str(metadata["source_version"]),
                "restore.source_model_uri": metadata["source_model_uri"],
                "restore.serialized_sha256": model_hash,
            },
            description="Restauración de pesos y validación existentes; sin entrenamiento.",
        )
    if hashlib.sha256(
        download_bytes(client, rid, "model/model.pkl")
    ).hexdigest() != model_version.tags.get("restore.serialized_sha256"):
        raise ValueError("Pesos publicados en MLflow modificados")
    # La promoción solo ocurre después de verificar artefactos, predicción y residuos.
    probe = read_json(bundle / "probe.json")
    with tempfile.TemporaryDirectory(prefix="restore-load-") as temporary:
        local = client.download_artifacts(rid, "model", temporary)
        model = mlflow.pyfunc.load_model(local)
        with threadpool_limits(limits=2):
            actual = model.predict(
                pd.DataFrame(probe["input"]["data"], columns=probe["input"]["columns"])
            )
        np.testing.assert_allclose(actual, probe["prediction"], rtol=1e-12, atol=1e-12)
    client.set_registered_model_alias(NAME, "champion", model_version.version)
    return {
        "bundle_id": bid,
        "model_name": NAME,
        "version": model_version.version,
        "source_version": metadata["source_version"],
        "run_mapping": mappings,
        "trained": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "verify", "restore"])
    parser.add_argument("--bundle", default="models/champion_restore")
    parser.add_argument("--uri", default="http://localhost:5011")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    if args.action == "export":
        result = {"bundle_id": export_bundle(args.bundle, args.uri, args.project_root)}
    elif args.action == "verify":
        result = verify_bundle(args.bundle, args.project_root)
    else:
        result = restore(args.bundle, args.uri, args.project_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
