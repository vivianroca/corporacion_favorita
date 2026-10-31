"""Walk-forward pareado: cuatro ventanas, reentrenamiento y métricas micro/macro."""

import argparse
import csv
import hashlib
import itertools
import json
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import fmean, pstdev
from time import perf_counter
from uuid import uuid4

import joblib
import pandas as pd
import yaml
from threadpoolctl import threadpool_limits

from reposicion.baseline import evaluate, read_sales, weekly_forecast
from reposicion.contracts import Contracts
from reposicion.hist_gradient_boosting import MODEL_PARAMS
from reposicion.hist_gradient_boosting import model_pipeline as boosting_pipeline
from reposicion.random_forest import (
    FOREST_PARAMS,
    SalesHistory,
    features,
    model_pipeline,
    plots,
    training_data,
    write_csv,
)
from reposicion.source_io import DeliveryCatalog, canonical_bytes, checksum
from reposicion.system_metrics import training_run
from reposicion.tracking import log_experiment

EXPERIMENT = "corporacion_favorita-walk-forward"
MODELS = ("baseline_semanal", "random_forest", "hist_gradient_boosting")
LABELS = ("Baseline semanal", "Random Forest", "HistGradientBoosting")


def load_windows(path):
    config = yaml.safe_load(Path(path).read_text())
    starts = [date.fromisoformat(value) for value in config["forecast_starts"]]
    if (
        config["schema_version"] != 1
        or len(starts) != 4
        or any(day.year != 2017 or day.month != 1 for day in starts)
        or any(b - a != timedelta(days=7) for a, b in itertools.pairwise(starts))
        or config["horizon_days"] != 7
        or config["training_window"] != "rolling"
        or config["issue_time_utc"] != "12:00:00Z"
        or type(config["training_weeks"]) is not int
        or not 1 <= config["training_weeks"] <= 52
        or type(config["evaluation_delay_days"]) is not int
        or config["evaluation_delay_days"] <= 6
    ):
        raise ValueError("Configuración walk-forward inválida")
    return config, [
        {
            "forecast_start": str(day),
            "forecast_end": str(day + timedelta(days=6)),
            "issued_at": str(day) + "T" + config["issue_time_utc"],
            "evaluated_at": str(day + timedelta(days=config["evaluation_delay_days"]))
            + "T"
            + config["issue_time_utc"],
            "training_start": str(day - timedelta(weeks=config["training_weeks"])),
            "training_end": str(day - timedelta(days=1)),
        }
        for day in starts
    ]


def aggregate_metrics(windows):
    """Micro MAE/WAPE de errores crudos; macro media/desviación de las ventanas."""
    if not windows or any(not rows for rows in windows):
        raise ValueError("No se agregan ventanas vacías")
    seen = set()
    for rows in windows:
        for row in rows:
            key = row["date"], row["store_nbr"], row["family"]
            if key in seen:
                raise ValueError("Hay observaciones repetidas entre ventanas")
            seen.add(key)
    errors = [math.fsum(row["absolute_error"] for row in rows) for rows in windows]
    sales = [math.fsum(row["actual"] for row in rows) for rows in windows]
    counts = [len(rows) for rows in windows]
    maes = [error / n for error, n in zip(errors, counts, strict=True)]
    wapes = [error / total for error, total in zip(errors, sales, strict=True) if total]
    total_sales = math.fsum(sales)
    total_error = math.fsum(errors)
    return {
        "mae": total_error / sum(counts),
        "wape": total_error / total_sales if total_sales else None,
        "observations": sum(counts),
        "absolute_error_sum": total_error,
        "actual_sales_sum": total_sales,
        "windows": len(windows),
        "mae_mean": fmean(maes),
        "mae_std": pstdev(maes),
        "wape_mean": fmean(wapes) if wapes else None,
        "wape_std": pstdev(wapes) if wapes else None,
        "wape_defined_windows": len(wapes),
    }


def evaluation_signature(rows):
    """No incluye predicciones: todos los modelos deben evaluar idénticas claves y verdad."""
    return [(r["date"], r["store_nbr"], r["family"], r["actual"]) for r in rows]


def fit_predict(name, x, y, test_x, *, pipeline_factory=None):
    """Una nueva instancia y preprocesamiento ajustado solo a este corte, sin warm start."""
    if name not in {"random_forest", "hist_gradient_boosting"}:
        raise ValueError("Candidato ML desconocido")
    model = (
        pipeline_factory(name)
        if pipeline_factory is not None
        else model_pipeline()
        if name == "random_forest"
        else boosting_pipeline()
    )
    train_input = x if name == "random_forest" else pd.DataFrame(x)
    predict_input = test_x if name == "random_forest" else pd.DataFrame(test_x)
    started = perf_counter()
    with threadpool_limits(limits=2):
        model.fit(train_input, y)
    duration = perf_counter() - started
    with threadpool_limits(limits=2):
        predictions = model.predict(predict_input)
    return model, predictions, duration


def run(
    source,
    contracts_path,
    config_path,
    output,
    tracking_uri,
    *,
    feature_builder=None,
    pipeline_factory=None,
    experiment_name=EXPERIMENT,
    baseline_reference=None,
):
    config, windows = load_windows(config_path)
    catalog, contracts = DeliveryCatalog(source), Contracts(contracts_path)
    # Preflight de las cuatro ventanas, sin leer ventas ni revisiones futuras.
    for window in windows:
        start = date.fromisoformat(window["forecast_start"])
        expected = {str(start - timedelta(days=i)) for i in range(1, 8)}
        available = {
            r["reference_date"]
            for r in catalog.available(window["issued_at"], latest=True)
            if r["source"] == "train"
        }
        if not expected <= available:
            raise ValueError("Faltan entregas para el baseline; no se omiten ventanas")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    validation_id = uuid4().hex
    evaluations = {name: [] for name in MODELS}
    fold_results = []
    initial_series = None
    for index, window in enumerate(windows, start=1):
        start = date.fromisoformat(window["forecast_start"])
        history = SalesHistory(catalog, contracts)
        if feature_builder is not None:
            feature_builder.begin_window()
        baseline_history, baseline_receipts = read_sales(
            catalog,
            contracts,
            start - timedelta(days=7),
            start - timedelta(days=1),
            window["issued_at"],
        )
        template = weekly_forecast(baseline_history, start)
        if baseline_reference is not None:
            reference_path = Path(baseline_reference) / f"window_{index}" / "baseline_semanal"
            with (reference_path / "forecast.csv").open(newline="") as stream:
                saved = list(csv.DictReader(stream))
            if saved != [{k: str(v) for k, v in row.items()} for row in template]:
                raise ValueError("El baseline difiere del experimento anterior")
        series = sorted({(p["store_nbr"], p["family"]) for p in template})
        if initial_series is not None and series != initial_series:
            raise ValueError("El universo de series cambia entre ventanas")
        initial_series = series
        x, y, train_lineage = training_data(
            history,
            start,
            window["issued_at"],
            series,
            config["training_weeks"],
            feature_builder=feature_builder,
        )
        train_hash = hashlib.sha256(
            json.dumps({"x": x, "y": y}, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        past, feature_receipts = history.window(
            start - timedelta(days=28), start - timedelta(days=1), window["issued_at"]
        )
        test_x = [
            (
                features(past, start, date.fromisoformat(p["date"]), p["store_nbr"], p["family"])
                if feature_builder is None
                else feature_builder.enrich(
                    past,
                    start,
                    date.fromisoformat(p["date"]),
                    p["store_nbr"],
                    p["family"],
                    window["issued_at"],
                )
            )
            for p in template
        ]
        reference_keys = None
        for name, label in zip(MODELS, LABELS, strict=True):
            print(
                f"Ventana {index}/4 {window['forecast_start']}: {name}, entrenamiento={len(y)}",
                flush=True,
            )
            directory = output / f"window_{index}" / name
            directory.mkdir(parents=True)
            with training_run(
                tracking_uri,
                experiment_name=experiment_name,
                run_name=f"{name}-{start}-{validation_id[:8]}",
            ) as active:
                active.client.set_tag(active.run_id, "walk_forward_id", validation_id)
                active.client.set_tag(active.run_id, "run_role", "window")
                model, duration = None, 0.0
                predictions = template
                if name != "baseline_semanal":
                    if pipeline_factory is None:
                        model, values, duration = fit_predict(name, x, y, test_x)
                    else:
                        model, values, duration = fit_predict(
                            name, x, y, test_x, pipeline_factory=pipeline_factory
                        )
                    predictions = [
                        {**p, "prediction": float(value)}
                        for p, value in zip(template, values, strict=True)
                    ]
                actuals, truth_receipts = read_sales(
                    catalog, contracts, start, start + timedelta(days=6), window["evaluated_at"]
                )
                metrics, rows = evaluate(predictions, actuals)
                if baseline_reference is not None and name == "baseline_semanal":
                    with (reference_path / "evaluation.csv").open(newline="") as stream:
                        saved_evaluation = list(csv.DictReader(stream))
                    if saved_evaluation != [{k: str(v) for k, v in row.items()} for row in rows]:
                        raise ValueError(
                            "Los reales del baseline difieren del experimento anterior"
                        )
                signature = evaluation_signature(rows)
                if reference_keys is not None and signature != reference_keys:
                    raise ValueError("La evaluación no está pareada entre modelos")
                reference_keys = signature
                metrics["training_duration_seconds"] = duration
                parameters = {
                    **window,
                    "walk_forward_id": validation_id,
                    "window_index": index,
                    "model": name,
                    "horizon_days": 7,
                    "training_window": "rolling",
                    "training_weeks": config["training_weeks"],
                    "training_rows": len(y) if model is not None else 0,
                    "series_count": len(series),
                    "wape_scale": "fraction",
                    "missing_policy": "error"
                    if model is None
                    else "training_median_with_explicit_missing_flags",
                    "shared_training_sha256": train_hash if model is not None else "not_applicable",
                }
                if name == "random_forest":
                    parameters.update(FOREST_PARAMS)
                elif name == "hist_gradient_boosting":
                    parameters.update(MODEL_PARAMS)
                if feature_builder is not None and model is not None:
                    parameters.update(
                        {
                            "feature_set": "temporal_v2",
                            "missing_policy": "same_series_comparable_then_series_then_same_family",
                        }
                    )
                lineage = {
                    "manifest_sha256": checksum(catalog.root / "manifest.json"),
                    "contracts_sha256": checksum(contracts.path),
                    "config_sha256": checksum(config_path),
                    "code_sha256": checksum(__file__),
                    "shared_features_code_sha256": checksum(
                        Path(__file__).with_name("random_forest.py")
                    ),
                    "hgb_pipeline_code_sha256": checksum(
                        Path(__file__).with_name("hist_gradient_boosting.py")
                    ),
                    "baseline_receipts": baseline_receipts,
                    "training": train_lineage if model is not None else None,
                    "training_and_feature_receipts": list(history.used.values())
                    if model is not None
                    else [],
                    "forecast_feature_receipts": feature_receipts
                    if model is not None
                    else baseline_receipts,
                    "evaluation_receipts": truth_receipts,
                }
                if feature_builder is not None and model is not None:
                    lineage["calendar"] = feature_builder.lineage()
                    lineage["temporal_features_code_sha256"] = checksum(
                        Path(__file__).with_name("temporal_features.py")
                    )
                for filename, data in (
                    ("metrics.json", metrics),
                    ("parameters.json", parameters),
                    ("lineage.json", lineage),
                ):
                    (directory / filename).write_bytes(canonical_bytes(data))
                write_csv(directory / "forecast.csv", predictions)
                write_csv(directory / "evaluation.csv", rows)
                (directory / "requirements.lock").write_bytes(
                    Path("requirements.lock").read_bytes()
                )
                if model is not None:
                    joblib.dump(model, directory / "model.joblib", compress=3)
                plots(directory, rows, model_label=label)
                active.log_results(parameters, metrics, directory)
                record = {
                    "model": name,
                    "window_index": index,
                    **window,
                    "run_id": active.run_id,
                    **metrics,
                }
                fold_results.append(record)
                evaluations[name].append(rows)
                (directory / "run.json").write_bytes(canonical_bytes(record))
    aggregate_results = []
    for name in MODELS:
        metrics = aggregate_metrics(evaluations[name])
        directory = output / "aggregates" / name
        directory.mkdir(parents=True)
        records = [record for record in fold_results if record["model"] == name]
        write_csv(directory / "windows.csv", records)
        write_csv(directory / "evaluation.csv", [row for rows in evaluations[name] for row in rows])
        (directory / "metrics.json").write_bytes(canonical_bytes(metrics))
        (directory / "walk_forward.yaml").write_bytes(Path(config_path).read_bytes())
        parameters = {
            "walk_forward_id": validation_id,
            "model": name,
            "run_role": "aggregate",
            "horizon_days": 7,
            "window_count": 4,
            "training_weeks": config["training_weeks"],
            "aggregation": "pooled_errors_and_sales",
            "macro_std_ddof": 0,
            "wape_scale": "fraction",
            "selection": "none",
        }
        run_id = log_experiment(
            tracking_uri,
            parameters,
            metrics,
            directory,
            experiment_name=experiment_name,
            run_name=f"aggregate-{name}-{validation_id[:8]}",
        )
        aggregate_results.append({"model": name, "run_id": run_id, **metrics})
    write_csv(output / "windows.csv", fold_results)
    write_csv(output / "comparison.csv", aggregate_results)
    result = {
        "walk_forward_id": validation_id,
        "tracking_uri": tracking_uri,
        "windows": fold_results,
        "aggregates": aggregate_results,
    }
    (output / "results.json").write_bytes(canonical_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/simulation")
    parser.add_argument("--contracts", default="configs/contracts.yaml")
    parser.add_argument("--config", default="configs/walk_forward.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.source, args.contracts, args.config, args.output, args.tracking_uri), indent=2
        )
    )


if __name__ == "__main__":
    main()
