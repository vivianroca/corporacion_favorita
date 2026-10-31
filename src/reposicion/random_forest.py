"""Candidato Random Forest global con evaluación pareada contra el baseline semanal."""

import argparse
import csv
import json
import math
import os
import platform
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

import joblib
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from reposicion.baseline import evaluate, read_sales, weekly_forecast
from reposicion.contracts import Contracts
from reposicion.source_io import DeliveryCatalog, canonical_bytes, checksum, parse_instant
from reposicion.system_metrics import training_run

LAGS = (7, 14, 21, 28)
FOREST_PARAMS = {
    "n_estimators": 64,
    "max_depth": 16,
    "min_samples_leaf": 5,
    "max_features": 0.7,
    "random_state": 42,
    "n_jobs": 2,
    "criterion": "squared_error",
    "bootstrap": True,
}


class SalesHistory:
    """Acceso por corte a versiones inmutables; nunca imputa observaciones ausentes."""

    def __init__(self, catalog, contracts):
        self.catalog = catalog
        self.contracts = contracts
        self.used = {}
        self.cache = {}

    def _read(self, delivery_id):
        if delivery_id in self.cache:
            return self.cache[delivery_id]
        receipt = next(r for r in self.catalog.records if r["delivery_id"] == delivery_id)
        rows = {}
        for raw in self.catalog.read(receipt, as_of=receipt["available_at"]):
            row = self.contracts.validate_row("train", raw)
            key = row["date"], row["store_nbr"], row["family"]
            if key in rows or key[0].isoformat() != receipt["reference_date"]:
                raise ValueError("Clave duplicada o fecha inconsistente en ventas")
            rows[key] = float(row["sales"])
        self.cache[delivery_id] = rows
        return rows

    def window(self, start, end, cutoff):
        result, receipts = {}, []
        for receipt in self.catalog.available(cutoff, latest=True):
            if (
                receipt["source"] == "train"
                and start.isoformat() <= receipt["reference_date"] <= end.isoformat()
            ):
                result.update(self._read(receipt["delivery_id"]))
                receipts.append(receipt)
                self.used[receipt["delivery_id"]] = receipt
        return result, receipts


def features(history, origin, target, store, family):
    """Todas las ventas empleadas preceden al origen, incluso para horizonte siete."""
    horizon = (target - origin).days + 1
    if horizon not in range(1, 8):
        raise ValueError("Horizonte fuera de 1..7")
    result = {
        "store": str(store),
        "family": family,
        "weekday": str(target.weekday()),
        "horizon": horizon,
        "month": str(target.month),
    }
    for lag in LAGS:
        reference = target - timedelta(days=lag)
        assert reference < origin
        value = history.get((reference, store, family))
        result[f"lag_{lag}"] = float("nan") if value is None else value
        result[f"lag_{lag}_missing"] = int(value is None)
    recent = [
        history[(origin - timedelta(days=i), store, family)]
        for i in range(1, 8)
        if (origin - timedelta(days=i), store, family) in history
    ]
    result["recent_count"] = len(recent)
    result["recent_mean"] = math.fsum(recent) / len(recent) if recent else float("nan")
    return result


def model_pipeline(params=None):
    return Pipeline(
        [
            ("encode", DictVectorizer(sparse=False)),
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("forest", RandomForestRegressor(**(FOREST_PARAMS if params is None else params))),
        ]
    )


def training_data(history, start, issued_at, series, weeks=8, *, feature_builder=None):
    if not 1 <= weeks <= 52:
        raise ValueError("training_weeks debe estar entre 1 y 52")
    labels, label_receipts = history.window(
        start - timedelta(weeks=weeks), start - timedelta(days=1), issued_at
    )
    x, y, lineage = [], [], []
    for week in range(weeks, 0, -1):
        origin = start - timedelta(weeks=week)
        cutoff = origin.isoformat() + "T12:00:00Z"
        if parse_instant(cutoff) >= parse_instant(issued_at):
            raise ValueError("Origen de entrenamiento posterior a la emisión")
        past, receipts = history.window(
            origin - timedelta(days=28), origin - timedelta(days=1), cutoff
        )
        count, missing_labels = 0, 0
        for offset in range(7):
            target = origin + timedelta(days=offset)
            assert target < start
            for store, family in series:
                value = labels.get((target, store, family))
                if value is None:
                    missing_labels += 1
                    continue
                x.append(
                    features(past, origin, target, store, family)
                    if feature_builder is None
                    else feature_builder.enrich(past, origin, target, store, family, cutoff)
                )
                y.append(value)
                count += 1
        lineage.append(
            {
                "origin": origin.isoformat(),
                "issued_at": cutoff,
                "rows": count,
                "missing_labels_skipped": missing_labels,
                "feature_deliveries": [r["delivery_id"] for r in receipts],
            }
        )
    if not y:
        raise ValueError("No hay etiquetas de entrenamiento disponibles")
    return x, y, {"origins": lineage, "label_deliveries": label_receipts, "label_as_of": issued_at}


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_reference(path, catalog, contracts):
    parameters = json.loads((path / "parameters.json").read_text())
    lineage = json.loads((path / "lineage.json").read_text())
    if lineage["manifest_sha256"] != checksum(catalog.root / "manifest.json"):
        raise ValueError("El catálogo difiere del baseline")
    if lineage["contracts_sha256"] != checksum(contracts.path):
        raise ValueError("Los contratos difieren del baseline")
    start = date.fromisoformat(parameters["forecast_start"])
    if parameters["horizon_days"] != 7:
        raise ValueError("Se requiere baseline de siete días")
    issued = parse_instant(parameters["issued_at"])
    if issued.date() != start or parse_instant(parameters["evaluated_at"]) <= issued:
        raise ValueError("Cortes temporales inválidos")
    rows, _ = read_sales(
        catalog,
        contracts,
        start - timedelta(days=7),
        start - timedelta(days=1),
        parameters["issued_at"],
    )
    predictions = weekly_forecast(rows, start)
    with (path / "forecast.csv").open(newline="") as stream:
        saved = list(csv.DictReader(stream))
    expected = [{k: str(v) for k, v in p.items()} for p in predictions]
    if saved != expected:
        raise ValueError("Los pronósticos del baseline no coinciden con el catálogo al corte")
    return parameters, predictions


def plots(output, rows, *, model_label="Random Forest"):
    os.environ.setdefault("MPLCONFIGDIR", str(output.parent / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    days = sorted({r["date"] for r in rows})
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    for name, label in (("actual", "Real"), ("prediction", model_label)):
        values = [math.fsum(r[name] for r in rows if r["date"] == day) for day in days]
        axes[0].plot(days, values, marker="o", label=label)
    axes[0].set(title="Ventas totales diarias — 54 tiendas × 33 familias", ylabel="Ventas")
    axes[0].legend()
    # Ejemplo determinista: primera serie, elegido sin consultar errores.
    first = min((r["store_nbr"], r["family"]) for r in rows)
    selected = [r for r in rows if (r["store_nbr"], r["family"]) == first]
    for name, label in (("actual", "Real"), ("prediction", model_label)):
        axes[1].plot(
            [r["date"] for r in selected], [r[name] for r in selected], marker="o", label=label
        )
    axes[1].set(title=f"Ejemplo: tienda {first[0]}, familia {first[1]}", ylabel="Ventas")
    axes[1].legend()
    fig.savefig(output / "real_vs_pronosticado.png", dpi=150)
    plt.close(fig)
    errors = [r["prediction"] - r["actual"] for r in rows]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    axes[0].hist(errors, bins=80)
    axes[0].axvline(0, color="red", linestyle="--")
    axes[0].set(title="Errores: pronóstico − real", xlabel="Error", ylabel="Frecuencia")
    axes[1].hist([abs(e) for e in errors], bins=80)
    axes[1].set(title="Errores absolutos", xlabel="Error absoluto", ylabel="Frecuencia")
    fig.savefig(output / "distribucion_errores.png", dpi=150)
    plt.close(fig)


def run(baseline, source, contracts_path, output, tracking_uri, weeks=8):
    baseline, output = Path(baseline), Path(output)
    catalog, contracts = DeliveryCatalog(source), Contracts(contracts_path)
    reference, baseline_predictions = load_reference(baseline, catalog, contracts)
    start = date.fromisoformat(reference["forecast_start"])
    output.mkdir(parents=True, exist_ok=False)
    with training_run(
        tracking_uri,
        experiment_name="corporacion_favorita-candidatos",
        run_name="random-forest-" + start.isoformat(),
    ) as active_run:
        history = SalesHistory(catalog, contracts)
        series = sorted({(p["store_nbr"], p["family"]) for p in baseline_predictions})
        x, y, training_lineage = training_data(
            history, start, reference["issued_at"], series, weeks
        )
        print(f"Entrenando {len(y)} ejemplos históricos, {len(series)} series", flush=True)
        model = model_pipeline()
        fit_started = perf_counter()
        model.fit(x, y)
        fit_duration = perf_counter() - fit_started
        past, feature_receipts = history.window(
            start - timedelta(days=28), start - timedelta(days=1), reference["issued_at"]
        )
        test_x = [
            features(past, start, date.fromisoformat(p["date"]), p["store_nbr"], p["family"])
            for p in baseline_predictions
        ]
        predictions = [
            {**p, "prediction": float(value)}
            for p, value in zip(baseline_predictions, model.predict(test_x), strict=True)
        ]
        # Evaluación cargada después de ajustar y predecir. Nunca participa en fit o transform.
        actuals, target_receipts = read_sales(
            catalog, contracts, start, start + timedelta(days=6), reference["evaluated_at"]
        )
        metrics, evaluated = evaluate(predictions, actuals)
        metrics["training_duration_seconds"] = fit_duration
        baseline_metrics, baseline_rows = evaluate(baseline_predictions, actuals)
        with (baseline / "evaluation.csv").open(newline="") as stream:
            saved = list(csv.DictReader(stream))
        if saved != [{k: str(v) for k, v in row.items()} for row in baseline_rows]:
            raise ValueError("La evaluación difiere de los registros originales del baseline")
        stored_metrics = json.loads((baseline / "metrics.json").read_text())
        if baseline_metrics != stored_metrics:
            raise ValueError("Las métricas del baseline no coinciden")
        parameters = {
            **reference,
            **FOREST_PARAMS,
            "model": "RandomForestRegressor",
            "training_weeks": weeks,
            "training_rows": len(y),
            "lags_days": str(LAGS),
            "missing_policy": "training_median_with_explicit_missing_flags",
            "training_features_as_of": "each_historical_origin_12Z",
            "training_labels_as_of": reference["issued_at"],
            "baseline_run_id": json.loads((baseline / "run.json").read_text())["run_id"],
            "python_version": platform.python_version(),
            "sklearn_version": sklearn.__version__,
        }
        parameters.pop("baseline", None)
        parameters.pop("seasonal_period_days", None)
        lineage = {
            "manifest_sha256": checksum(catalog.root / "manifest.json"),
            "contracts_sha256": checksum(contracts.path),
            "code_sha256": checksum(__file__),
            "baseline_evaluation_sha256": checksum(baseline / "evaluation.csv"),
            "training": training_lineage,
            "training_and_feature_receipts": list(history.used.values()),
            "forecast_feature_receipts": feature_receipts,
            "evaluation_receipts": target_receipts,
        }
        comparison = [
            {"model": name, "mae": m["mae"], "wape": m["wape"], "observations": m["observations"]}
            for name, m in (("baseline_semanal", baseline_metrics), ("random_forest", metrics))
        ]
        for name, value in (
            ("parameters.json", parameters),
            ("metrics.json", metrics),
            ("lineage.json", lineage),
            ("comparison.json", comparison),
        ):
            (output / name).write_bytes(canonical_bytes(value))
        write_csv(output / "forecast.csv", predictions)
        write_csv(output / "evaluation.csv", evaluated)
        write_csv(output / "comparison.csv", comparison)
        write_csv(
            output / "feature_importances.csv",
            [
                {"feature": name, "importance": float(value)}
                for name, value in sorted(
                    zip(
                        model.named_steps["encode"].get_feature_names_out(),
                        model.named_steps["forest"].feature_importances_,
                        strict=True,
                    ),
                    key=lambda pair: -pair[1],
                )
            ],
        )
        joblib.dump(model, output / "model.joblib", compress=3)
        (output / "requirements.lock").write_bytes(Path("requirements.lock").read_bytes())
        plots(output, evaluated)
        active_run.log_results(parameters, metrics, output)
        run_id = active_run.run_id
        result = {"run_id": run_id, "tracking_uri": tracking_uri, "comparison": comparison}
        (output / "run.json").write_bytes(canonical_bytes(result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="reports/baseline/2017-01-08")
    parser.add_argument("--source", default="data/simulation")
    parser.add_argument("--contracts", default="configs/contracts.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    parser.add_argument("--training-weeks", type=int, default=8)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.baseline,
                args.source,
                args.contracts,
                args.output,
                args.tracking_uri,
                args.training_weeks,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
