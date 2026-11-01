"""Cuantiles empíricos de residuos walk-forward; solo inferencia del Champion."""

import argparse
import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from reposicion.contracts import Contracts
from reposicion.forecast_time import validate_origin
from reposicion.random_forest import SalesHistory, write_csv
from reposicion.source_io import DeliveryCatalog, canonical_bytes, parse_instant
from reposicion.temporal_features import TemporalFeatures


def residual_pools(windows, origin, issued_at):
    """No admite errores cuyo período o disponibilidad alcance el futuro."""
    pools = defaultdict(list)
    seen = set()
    for params, rows in windows:
        if parse_instant(params["evaluated_at"]) > parse_instant(issued_at):
            continue
        if date.fromisoformat(params["forecast_end"]) >= origin:
            continue
        start = date.fromisoformat(params["forecast_start"])
        if params["training_end"] >= params["forecast_start"]:
            raise ValueError("Validación no temporal")
        for row in rows:
            day = date.fromisoformat(row["date"])
            horizon = (day - start).days + 1
            key = row["date"], row["store_nbr"], row["family"]
            if key in seen or not 1 <= horizon <= 7 or day >= origin:
                raise ValueError("Residuo duplicado o fuera del horizonte")
            seen.add(key)
            error = float(row["actual"]) - float(row["prediction"])
            if not math.isfinite(error):
                raise ValueError("Residuo no finito")
            pools[row["family"], horizon].append(error)
    if not pools:
        raise ValueError("Sin residuos disponibles al corte")
    return pools


def intervals(prediction, errors, minimum=30):
    if not math.isfinite(prediction) or len(errors) < minimum:
        raise ValueError("Predicción inválida o calibración insuficiente")
    values = np.asarray(errors, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Residuos no finitos")
    result = np.maximum(0, prediction + np.quantile(values, [0.1, 0.5, 0.9], method="linear"))
    return tuple(float(x) for x in result)


def artifact_bytes(uri, run, filename):
    path = run.info.artifact_uri
    if not path.startswith("mlflow-artifacts:/"):
        raise ValueError("Se requiere proxy de artefactos")
    with urlopen(
        uri.rstrip("/")
        + "/api/2.0/mlflow-artifacts/artifacts/"
        + path.split(":", 1)[1].lstrip("/")
        + "/"
        + filename,
        timeout=60,
    ) as response:
        return response.read()


def run(
    origin,
    issued_at,
    output,
    uri="http://localhost:5011",
    source="data/simulation",
    *,
    catalog=None,
    model_version=None,
    contracts_path="configs/contracts.yaml",
):
    origin = validate_origin(origin, issued_at)
    client = mlflow.MlflowClient(tracking_uri=uri)
    version = (
        client.get_model_version("corporacion_favorita_random_forest", str(model_version))
        if model_version is not None
        else client.get_model_version_by_alias("corporacion_favorita_random_forest", "champion")
    )
    champion_run = client.get_run(version.run_id)
    if date.fromisoformat(champion_run.data.params["training_end"]) >= origin:
        raise ValueError("Champion entrenado con información futura")
    # El artefacto ya evaluado tampoco se utiliza antes de su disponibilidad simulada.
    if parse_instant(champion_run.data.params["evaluated_at"]) > parse_instant(issued_at):
        raise ValueError("Champion aún no evaluado al corte simulado")
    runs = client.search_runs(
        [champion_run.info.experiment_id],
        filter_string="params.walk_forward_id = '"
        + champion_run.data.params["walk_forward_id"]
        + "'",
        max_results=1000,
    )
    windows, sources = [], []
    for item in runs:
        p = item.data.params
        if p.get("model") != "random_forest" or "window_index" not in p:
            continue
        if item.info.status != "FINISHED":
            raise ValueError("Fold incompleto")
        if (
            parse_instant(p["evaluated_at"]) > parse_instant(issued_at)
            or date.fromisoformat(p["forecast_end"]) >= origin
        ):
            continue
        payload = artifact_bytes(uri, item, "evaluation.csv")
        rows = list(csv.DictReader(io.StringIO(payload.decode())))
        windows.append((p, rows))
        sources.append(
            {
                "run_id": item.info.run_id,
                "evaluated_at": p["evaluated_at"],
                "sha256": hashlib.sha256(payload).hexdigest(),
                "rows": len(rows),
            }
        )
    pools = residual_pools(windows, origin, issued_at)
    catalog = catalog if catalog is not None else DeliveryCatalog(source)
    contracts = Contracts(contracts_path)
    past, receipts = SalesHistory(catalog, contracts).window(
        origin - timedelta(days=28), origin - timedelta(days=1), issued_at
    )
    series = sorted({(store, family) for _, store, family in past})
    expected_stores = int(champion_run.data.params["series_count"])
    if len(series) != expected_stores:
        raise ValueError("Cobertura de series distinta al Champion")
    builder = TemporalFeatures(catalog, contracts)
    keys, features = [], []
    for offset in range(7):
        target = origin + timedelta(days=offset)
        for store, family in series:
            keys.append((target, store, family, offset + 1))
            features.append(builder.enrich(past, origin, target, store, family, issued_at))
    frame = pd.DataFrame(features)
    for column in frame.select_dtypes(include="number").columns:
        frame[column] = frame[column].astype(float)
    output = Path(output)
    if output.exists():
        raise FileExistsError("No se sobrescriben pronósticos existentes")
    output.mkdir(parents=True)
    (output / "downloaded_model").mkdir()
    previous = mlflow.get_tracking_uri()
    try:
        mlflow.set_tracking_uri(uri)
        # Fijar versión: un cambio concurrente del alias no cambia este pronóstico.
        model = mlflow.pyfunc.load_model(
            f"models:/{version.name}/{version.version}", dst_path=str(output / "downloaded_model")
        )
        with threadpool_limits(limits=2):
            predictions = model.predict(frame)
    finally:
        mlflow.set_tracking_uri(previous)
    rows = []
    for key, prediction in zip(keys, predictions, strict=True):
        day, store, family, horizon = key
        errors = pools.get((family, horizon), [])
        p10, p50, p90 = intervals(float(prediction), errors)
        rows.append(
            {
                "date": str(day),
                "store_nbr": store,
                "family": family,
                "horizon": horizon,
                "point_prediction": float(prediction),
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "calibration_count": len(errors),
            }
        )
    write_csv(output / "forecast_quantiles.csv", rows)
    lineage = {
        "origin": str(origin),
        "issued_at": issued_at,
        "horizon_days": 7,
        "model_name": version.name,
        "model_version": version.version,
        "alias": "champion",
        "model_run_id": version.run_id,
        "model_source": version.source,
        "model_tags": dict(version.tags),
        "residual_sources": sources,
        "sales_receipts": receipts,
        "calendar": builder.lineage(),
        "rows": len(rows),
        "method": "signed actual-minus-prediction empirical quantiles by family,horizon; linear; clip at zero",
        "minimum_calibration_count": 30,
        "availability_policy": "simulated evaluated_at, not wall-clock MLflow creation; only past forecast periods",
        "limitations": "pooled stores within family; no guaranteed coverage; model drift possible; no retraining",
    }
    (output / "lineage.json").write_bytes(canonical_bytes(lineage))
    return {
        "output": str(output),
        "rows": len(rows),
        "residual_folds": len(sources),
        "model_version": version.version,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origin", required=True)
    p.add_argument("--issued-at", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--tracking-uri", default="http://localhost:5011")
    p.add_argument("--source", default="data/simulation")
    a = p.parse_args()
    print(json.dumps(run(a.origin, a.issued_at, a.output, a.tracking_uri, a.source), indent=2))


if __name__ == "__main__":
    main()
