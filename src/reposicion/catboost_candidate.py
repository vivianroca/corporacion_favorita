"""CatBoost inicial con variables temporales v2 y cuatro folds sin optimización."""

import argparse
import csv
import hashlib
import json
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import joblib
import numpy as np
import yaml
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

from reposicion.baseline import evaluate, read_sales
from reposicion.catboost_model import CatBoostSalesRegressor
from reposicion.contracts import Contracts
from reposicion.hist_gradient_boosting import verify_evaluation
from reposicion.random_forest import SalesHistory, plots, training_data, write_csv
from reposicion.source_io import DeliveryCatalog, canonical_bytes, checksum
from reposicion.system_metrics import training_run
from reposicion.temporal_features import SeriesFamilyImputer, TemporalFeatures
from reposicion.tracking import log_experiment
from reposicion.walk_forward import aggregate_metrics, load_windows

EXPERIMENT = "corporacion_favorita-catboost-temporal-v2"


def model_pipeline(parameters):
    return Pipeline(
        [
            ("series_impute", SeriesFamilyImputer()),
            ("encode", DictVectorizer(sparse=False)),
            ("estimator", CatBoostSalesRegressor(parameters)),
        ]
    )


def load_parameters(path):
    config = yaml.safe_load(Path(path).read_text())
    parameters = config["parameters"]
    if config["schema_version"] != 1 or parameters.get("use_best_model") is not False:
        raise ValueError("Se requiere configuración inicial sin selección de iteración")
    if any(key in parameters for key in ("early_stopping_rounds", "od_type", "od_pval", "od_wait")):
        raise ValueError("No se permite optimizar con detección de sobreajuste")
    if parameters.get("allow_writing_files") is not False or parameters.get("task_type") != "CPU":
        raise ValueError("Se requiere CPU sin salidas implícitas de CatBoost")
    return parameters


def run(source, contracts_path, windows_path, parameters_path, previous, output, tracking_uri):
    config, windows = load_windows(windows_path)
    parameters = load_parameters(parameters_path)
    catalog, contracts = DeliveryCatalog(source), Contracts(contracts_path)
    builder = TemporalFeatures(catalog, contracts)
    previous, output = Path(previous), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    validation_id = uuid4().hex
    records, evaluated_windows = [], []
    for index, window in enumerate(windows, start=1):
        reference = previous / f"window_{index}" / "random_forest"
        reference_parameters = json.loads((reference / "parameters.json").read_text())
        reference_lineage = json.loads((reference / "lineage.json").read_text())
        for key, value in window.items():
            if reference_parameters[key] != value:
                raise ValueError("Los cortes difieren de la variante temporal v2")
        for key, path in (
            ("manifest_sha256", catalog.root / "manifest.json"),
            ("contracts_sha256", contracts.path),
            ("temporal_features_code_sha256", Path(__file__).with_name("temporal_features.py")),
        ):
            if reference_lineage[key] != checksum(path):
                raise ValueError("La fuente, contratos o variables temporales difieren de v2")
        with (reference / "forecast.csv").open(newline="") as stream:
            template = [
                {
                    "date": row["date"],
                    "store_nbr": int(row["store_nbr"]),
                    "family": row["family"],
                    "lag_date": row["lag_date"],
                }
                for row in csv.DictReader(stream)
            ]
        series = sorted({(row["store_nbr"], row["family"]) for row in template})
        directory = output / f"window_{index}" / "catboost"
        directory.mkdir(parents=True)
        with training_run(
            tracking_uri,
            experiment_name=EXPERIMENT,
            run_name=f"catboost-{window['forecast_start']}-{validation_id[:8]}",
        ) as active:
            builder.begin_window()
            active.client.set_tag(active.run_id, "walk_forward_id", validation_id)
            active.client.set_tag(active.run_id, "run_role", "window")
            history = SalesHistory(catalog, contracts)
            start = date.fromisoformat(window["forecast_start"])
            x, y, training_lineage = training_data(
                history,
                start,
                window["issued_at"],
                series,
                config["training_weeks"],
                feature_builder=builder,
            )
            fingerprint = hashlib.sha256(
                json.dumps({"x": x, "y": y}, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if (
                fingerprint != reference_parameters["shared_training_sha256"]
                or training_lineage != reference_lineage["training"]
            ):
                raise ValueError("Las filas/etiquetas de entrenamiento difieren de RF/HGB v2")
            past, feature_receipts = history.window(
                start - timedelta(days=28), start - timedelta(days=1), window["issued_at"]
            )
            test_x = [
                builder.enrich(
                    past,
                    start,
                    date.fromisoformat(row["date"]),
                    row["store_nbr"],
                    row["family"],
                    window["issued_at"],
                )
                for row in template
            ]
            if builder.lineage() != reference_lineage["calendar"]:
                raise ValueError("El calendario conocido difiere de RF/HGB v2")
            print(f"CatBoost fold {index}/4, corte={start}, entrenamiento={len(y)}", flush=True)
            model = model_pipeline(parameters)
            started = perf_counter()
            model.fit(x, y)
            fit_duration = perf_counter() - started
            values = model.predict(test_x)
            raw_values = model.named_steps["estimator"].model_.predict(model[:-1].transform(test_x))
            predictions = [
                {**row, "prediction": float(value)}
                for row, value in zip(template, values, strict=True)
            ]
            # No se entrega eval_set: reales solo después del entrenamiento y la predicción.
            actuals, truth_receipts = read_sales(
                catalog, contracts, start, start + timedelta(days=6), window["evaluated_at"]
            )
            metrics, evaluated = evaluate(predictions, actuals)
            metrics["training_duration_seconds"] = fit_duration
            metrics["negative_raw_predictions"] = int(np.sum(raw_values < 0))
            verify_evaluation(reference, evaluated)
            verify_evaluation(previous / f"window_{index}" / "hist_gradient_boosting", evaluated)
            logged_parameters = {
                **window,
                **parameters,
                "walk_forward_id": validation_id,
                "window_index": index,
                "model": "CatBoostRegressor",
                "feature_set": "temporal_v2",
                "training_weeks": config["training_weeks"],
                "training_rows": len(y),
                "horizon_days": 7,
                "series_count": len(series),
                "catboost_version": version("catboost"),
                "shared_training_sha256": fingerprint,
                "wape_scale": "fraction",
                "categorical_encoding": "same_DictVectorizer_as_RF_HGB_v2",
                "prediction_floor": 0,
                "hyperparameter_search": "none",
                "reference_rf_run_id": json.loads((reference / "run.json").read_text())["run_id"],
            }
            lineage = {
                "manifest_sha256": checksum(catalog.root / "manifest.json"),
                "contracts_sha256": checksum(contracts.path),
                "code_sha256": checksum(__file__),
                "estimator_code_sha256": checksum(Path(__file__).with_name("catboost_model.py")),
                "parameters_sha256": checksum(parameters_path),
                "windows_sha256": checksum(windows_path),
                "temporal_features_code_sha256": checksum(
                    Path(__file__).with_name("temporal_features.py")
                ),
                "training": training_lineage,
                "training_and_feature_receipts": list(history.used.values()),
                "forecast_feature_receipts": feature_receipts,
                "calendar": builder.lineage(),
                "evaluation_receipts": truth_receipts,
            }
            for filename, data in (
                ("parameters.json", logged_parameters),
                ("metrics.json", metrics),
                ("lineage.json", lineage),
                (
                    "resolved_catboost_parameters.json",
                    model.named_steps["estimator"].model_.get_all_params(),
                ),
            ):
                (directory / filename).write_bytes(canonical_bytes(data))
            joblib.dump(model, directory / "model.joblib", compress=3)
            model.named_steps["estimator"].model_.save_model(str(directory / "model.cbm"))
            names = model.named_steps["encode"].get_feature_names_out()
            write_csv(
                directory / "feature_importances.csv",
                [
                    {"feature": str(name), "importance": float(importance)}
                    for name, importance in zip(
                        names,
                        model.named_steps["estimator"].model_.feature_importances_,
                        strict=True,
                    )
                ],
            )
            write_csv(directory / "forecast.csv", predictions)
            write_csv(directory / "evaluation.csv", evaluated)
            (directory / "requirements.lock").write_bytes(Path("requirements.lock").read_bytes())
            (directory / "catboost.yaml").write_bytes(Path(parameters_path).read_bytes())
            plots(directory, evaluated, model_label="CatBoost")
            active.log_results(logged_parameters, metrics, directory)
            record = {"window_index": index, **window, "run_id": active.run_id, **metrics}
            records.append(record)
            evaluated_windows.append(evaluated)
            (directory / "run.json").write_bytes(canonical_bytes(record))
    metrics = aggregate_metrics(evaluated_windows)
    directory = output / "aggregates" / "catboost"
    directory.mkdir(parents=True)
    previous_result = json.loads((previous / "results.json").read_text())
    comparison = [
        {"model": r["model"], "mae": r["mae"], "wape": r["wape"], "observations": r["observations"]}
        for r in previous_result["aggregates"]
    ]
    comparison.append(
        {
            "model": "catboost",
            "mae": metrics["mae"],
            "wape": metrics["wape"],
            "observations": metrics["observations"],
        }
    )
    for filename, data in (("metrics.json", metrics), ("comparison.json", comparison)):
        (directory / filename).write_bytes(canonical_bytes(data))
    write_csv(directory / "windows.csv", records)
    write_csv(directory / "evaluation.csv", [row for rows in evaluated_windows for row in rows])
    write_csv(directory / "comparison.csv", comparison)
    (directory / "catboost.yaml").write_bytes(Path(parameters_path).read_bytes())
    (directory / "walk_forward.yaml").write_bytes(Path(windows_path).read_bytes())
    aggregate_run = log_experiment(
        tracking_uri,
        {
            **parameters,
            "walk_forward_id": validation_id,
            "run_role": "aggregate",
            "model": "CatBoostRegressor",
            "feature_set": "temporal_v2",
            "horizon_days": 7,
            "window_count": 4,
            "wape_scale": "fraction",
            "aggregation": "pooled_errors_and_sales",
            "selection": "none",
        },
        metrics,
        directory,
        experiment_name=EXPERIMENT,
        run_name="aggregate-catboost-" + validation_id[:8],
    )
    result = {
        "walk_forward_id": validation_id,
        "tracking_uri": tracking_uri,
        "windows": records,
        "aggregate": {"run_id": aggregate_run, **metrics},
        "comparison": comparison,
    }
    (output / "results.json").write_bytes(canonical_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/simulation")
    parser.add_argument("--contracts", default="configs/contracts.yaml")
    parser.add_argument("--windows", default="configs/walk_forward.yaml")
    parser.add_argument("--parameters", default="configs/catboost.yaml")
    parser.add_argument("--previous", default="reports/walk_forward/temporal_v2_january_2017")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.source,
                args.contracts,
                args.windows,
                args.parameters,
                args.previous,
                args.output,
                args.tracking_uri,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
