"""Candidato HistGradientBoosting con variables y evaluación comunes, y Model Registry."""

import argparse
import csv
import json
import platform
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer
from threadpoolctl import threadpool_limits

from reposicion.baseline import evaluate, read_sales
from reposicion.contracts import Contracts
from reposicion.random_forest import (
    LAGS,
    SalesHistory,
    features,
    load_reference,
    plots,
    training_data,
    write_csv,
)
from reposicion.source_io import DeliveryCatalog, canonical_bytes, checksum
from reposicion.system_metrics import training_run

MODEL_NAME = "corporacion_favorita_hist_gradient_boosting"
MODEL_PARAMS = {
    "loss": "poisson",
    "learning_rate": 0.08,
    "max_iter": 150,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 20,
    "l2_regularization": 1.0,
    "max_bins": 255,
    "early_stopping": False,
    "categorical_features": None,
    "random_state": 42,
}


def model_pipeline(params=None):
    """La interfaz DataFrame permite servir el pipeline completo desde MLflow pyfunc."""
    return Pipeline(
        [
            ("records", FunctionTransformer(pd.DataFrame.to_dict, kw_args={"orient": "records"})),
            ("encode", DictVectorizer(sparse=False)),
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            (
                "boosting",
                HistGradientBoostingRegressor(**(MODEL_PARAMS if params is None else params)),
            ),
        ]
    )


def verify_evaluation(path, rows):
    with (path / "evaluation.csv").open(newline="", encoding="utf-8") as stream:
        saved = list(csv.DictReader(stream))
    if len(saved) != len(rows):
        raise ValueError("La cobertura difiere del modelo de referencia")
    for original, current in zip(saved, rows, strict=True):
        for key in ("date", "store_nbr", "family", "actual"):
            if original[key] != str(current[key]):
                raise ValueError("Las claves o reales difieren del modelo de referencia")


def run(baseline, forest, source, contracts_path, output, tracking_uri):
    baseline, forest, output = Path(baseline), Path(forest), Path(output)
    catalog, contracts = DeliveryCatalog(source), Contracts(contracts_path)
    reference, baseline_predictions = load_reference(baseline, catalog, contracts)
    forest_parameters = json.loads((forest / "parameters.json").read_text())
    for key in ("issued_at", "evaluated_at", "forecast_start", "horizon_days"):
        if reference[key] != forest_parameters[key]:
            raise ValueError("Los cortes difieren de Random Forest")
    start = date.fromisoformat(reference["forecast_start"])
    output.mkdir(parents=True, exist_ok=False)
    with training_run(
        tracking_uri,
        experiment_name="corporacion_favorita-candidatos",
        run_name="hist-gradient-boosting-" + start.isoformat(),
    ) as active:
        history = SalesHistory(catalog, contracts)
        series = sorted({(p["store_nbr"], p["family"]) for p in baseline_predictions})
        weeks = forest_parameters["training_weeks"]
        x, y, training_lineage = training_data(
            history, start, reference["issued_at"], series, weeks
        )
        previous_lineage = json.loads((forest / "lineage.json").read_text())
        if (
            training_lineage != previous_lineage["training"]
            or len(y) != forest_parameters["training_rows"]
        ):
            raise ValueError("La historia de entrenamiento difiere de Random Forest")
        train_frame = pd.DataFrame(x)
        model = model_pipeline()
        print(f"Entrenando HistGradientBoosting: {len(y)} filas, {len(series)} series", flush=True)
        started = perf_counter()
        with threadpool_limits(limits=2):
            model.fit(train_frame, y)
        fit_duration = perf_counter() - started
        past, feature_receipts = history.window(
            start - timedelta(days=28), start - timedelta(days=1), reference["issued_at"]
        )
        test_frame = pd.DataFrame(
            [
                features(past, start, date.fromisoformat(p["date"]), p["store_nbr"], p["family"])
                for p in baseline_predictions
            ]
        )
        with threadpool_limits(limits=2):
            values = model.predict(test_frame)
        predictions = [
            {**p, "prediction": float(v)} for p, v in zip(baseline_predictions, values, strict=True)
        ]
        # Los reales se consultan después de fit/predict, sin intervenir en preparación ni ajuste.
        actuals, receipts = read_sales(
            catalog, contracts, start, start + timedelta(days=6), reference["evaluated_at"]
        )
        metrics, evaluated = evaluate(predictions, actuals)
        metrics["training_duration_seconds"] = fit_duration
        baseline_metrics, baseline_rows = evaluate(baseline_predictions, actuals)
        verify_evaluation(baseline, baseline_rows)
        verify_evaluation(forest, evaluated)
        with (forest / "forecast.csv").open(newline="") as stream:
            old_predictions = [
                {**r, "store_nbr": int(r["store_nbr"]), "prediction": float(r["prediction"])}
                for r in csv.DictReader(stream)
            ]
        forest_metrics, _ = evaluate(old_predictions, actuals)
        old_metrics = json.loads((forest / "metrics.json").read_text())
        for key in ("mae", "wape", "observations", "actual_sales_sum"):
            if old_metrics[key] != forest_metrics[key]:
                raise ValueError("Las métricas previas de Random Forest difieren")
        parameters = {
            **reference,
            **MODEL_PARAMS,
            "model": "HistGradientBoostingRegressor",
            "training_weeks": weeks,
            "training_rows": len(y),
            "lags_days": str(LAGS),
            "missing_policy": forest_parameters["missing_policy"],
            "training_features_as_of": "each_historical_origin_12Z",
            "training_labels_as_of": reference["issued_at"],
            "baseline_run_id": json.loads((baseline / "run.json").read_text())["run_id"],
            "forest_run_id": json.loads((forest / "run.json").read_text())["run_id"],
            "python_version": platform.python_version(),
            "sklearn_version": version("scikit-learn"),
            "thread_limit": 2,
        }
        parameters.pop("baseline", None)
        parameters.pop("seasonal_period_days", None)
        lineage = {
            "manifest_sha256": checksum(catalog.root / "manifest.json"),
            "contracts_sha256": checksum(contracts.path),
            "code_sha256": checksum(__file__),
            "shared_features_code_sha256": checksum(Path(__file__).with_name("random_forest.py")),
            "training": training_lineage,
            "training_and_feature_receipts": list(history.used.values()),
            "forecast_feature_receipts": feature_receipts,
            "evaluation_receipts": receipts,
            "baseline_evaluation_sha256": checksum(baseline / "evaluation.csv"),
            "forest_evaluation_sha256": checksum(forest / "evaluation.csv"),
        }
        comparison = [
            {"model": name, "mae": m["mae"], "wape": m["wape"], "observations": m["observations"]}
            for name, m in (
                ("baseline_semanal", baseline_metrics),
                ("random_forest", forest_metrics),
                ("hist_gradient_boosting", metrics),
            )
        ]
        for name, data in (
            ("parameters.json", parameters),
            ("metrics.json", metrics),
            ("lineage.json", lineage),
            ("comparison.json", comparison),
        ):
            (output / name).write_bytes(canonical_bytes(data))
        write_csv(output / "forecast.csv", predictions)
        write_csv(output / "evaluation.csv", evaluated)
        write_csv(output / "comparison.csv", comparison)
        joblib.dump(model, output / "model.joblib", compress=3)
        (output / "requirements.lock").write_bytes(Path("requirements.lock").read_bytes())
        plots(output, evaluated, model_label="HistGradientBoosting")
        active.log_results(parameters, metrics, output)
        example = test_frame.head(5)
        signature = infer_signature(example, values[:5])
        info = mlflow.sklearn.log_model(
            sk_model=model,
            serialization_format="cloudpickle",
            name="model",
            registered_model_name=MODEL_NAME,
            input_example=example,
            signature=signature,
            pip_requirements=[
                f"{name}=={version(name)}"
                for name in (
                    "mlflow-skinny",
                    "scikit-learn",
                    "pandas",
                    "numpy",
                    "scipy",
                    "cloudpickle",
                )
            ],
        )
        registry = {
            "name": MODEL_NAME,
            "version": str(info.registered_model_version),
            "model_uri": info.model_uri,
            "run_id": active.run_id,
        }
        (output / "registry.json").write_bytes(canonical_bytes(registry))
        active.client.log_artifact(active.run_id, str(output / "registry.json"))
        result = {
            "run_id": active.run_id,
            "tracking_uri": tracking_uri,
            "registry": registry,
            "comparison": comparison,
        }
        (output / "run.json").write_bytes(canonical_bytes(result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="reports/baseline/2017-01-08")
    parser.add_argument("--forest", default="reports/random_forest/2017-01-08")
    parser.add_argument("--source", default="data/simulation")
    parser.add_argument("--contracts", default="configs/contracts.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.baseline,
                args.forest,
                args.source,
                args.contracts,
                args.output,
                args.tracking_uri,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
