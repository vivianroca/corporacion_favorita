"""Baseline semanal puntual, con información disponible al emitir el pronóstico."""

import argparse
import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from reposicion.contracts import Contracts
from reposicion.source_io import DeliveryCatalog, canonical_bytes, checksum, parse_instant


def weekly_forecast(history, start, horizon=7):
    """Exige la semana completa; ausencia de registro no equivale a venta cero."""
    if horizon != 7:
        raise ValueError("El horizonte autorizado es de siete días")
    indexed = {}
    series = set()
    for row in history:
        day = row["date"]
        if day >= start:
            raise ValueError("La historia contiene fechas del horizonte: leakage")
        key = day, row["store_nbr"], row["family"]
        value = float(row["sales"])
        if key in indexed or not math.isfinite(value) or value < 0:
            raise ValueError("Venta inválida o clave duplicada")
        indexed[key] = value
        series.add(key[1:])
    if not series:
        raise ValueError("No hay historia disponible")
    predictions = []
    for offset in range(horizon):
        target = start + timedelta(days=offset)
        lag = target - timedelta(days=7)
        for store, family in sorted(series):
            key = lag, store, family
            if key not in indexed:
                raise ValueError(f"Falta historia semanal: {key}")
            predictions.append(
                {
                    "date": target.isoformat(),
                    "store_nbr": store,
                    "family": family,
                    "lag_date": lag.isoformat(),
                    "prediction": indexed[key],
                }
            )
    return predictions


def evaluate(predictions, actuals):
    """MAE en unidades de ventas; WAPE es una fracción, indefinida si sum(y)=0."""
    truth = {}
    for row in actuals:
        key = row["date"].isoformat(), row["store_nbr"], row["family"]
        value = float(row["sales"])
        if key in truth or not math.isfinite(value) or value < 0:
            raise ValueError("Real inválido o duplicado")
        truth[key] = value
    evaluated = []
    seen = set()
    for prediction in predictions:
        key = prediction["date"], prediction["store_nbr"], prediction["family"]
        if key in seen or key not in truth:
            raise ValueError("Pronóstico duplicado o sin valor real")
        seen.add(key)
        actual = truth[key]
        evaluated.append(
            {
                **prediction,
                "actual": actual,
                "absolute_error": abs(actual - prediction["prediction"]),
            }
        )
    if not evaluated or seen != set(truth):
        raise ValueError("La evaluación exige cobertura idéntica y no vacía")
    error = math.fsum(row["absolute_error"] for row in evaluated)
    denominator = math.fsum(truth.values())
    return {
        "mae": error / len(evaluated),
        "wape": error / denominator if denominator else None,
        "observations": len(evaluated),
        "actual_sales_sum": denominator,
    }, evaluated


def read_sales(catalog, contracts, start, end, cutoff):
    """Selecciona primero por disponibilidad; verifica solo entregas seleccionadas."""
    receipts = [
        r
        for r in catalog.available(cutoff, latest=True)
        if r["source"] == "train" and start.isoformat() <= r["reference_date"] <= end.isoformat()
    ]
    expected = {(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)}
    if {r["reference_date"] for r in receipts} != expected:
        raise ValueError("Hay días sin entrega disponible al corte")
    rows = []
    for receipt in receipts:
        for raw in catalog.read(receipt, as_of=cutoff):
            row = contracts.validate_row("train", raw)
            if row["date"].isoformat() != receipt["reference_date"]:
                raise ValueError("Fecha incompatible con la entrega")
            rows.append(row)
    return rows, receipts


def run(source, contracts_path, start, issued_at, evaluated_at, output, tracking_uri):
    from reposicion.tracking import log_baseline

    issue = parse_instant(issued_at)
    evaluation = parse_instant(evaluated_at)
    if issue.astimezone(ZoneInfo("America/Guayaquil")).date() != start:
        raise ValueError("La emisión debe ocurrir en el primer día pronosticado (Ecuador)")
    if evaluation <= issue or evaluation.date() <= start + timedelta(days=6):
        raise ValueError("La evaluación debe ser posterior al horizonte")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    catalog = DeliveryCatalog(source)
    contracts = Contracts(contracts_path)
    history, inputs = read_sales(
        catalog, contracts, start - timedelta(days=7), start - timedelta(days=1), issued_at
    )
    predictions = weekly_forecast(history, start)
    # La verdad se lee únicamente después de construir los pronósticos.
    actuals, targets = read_sales(
        catalog, contracts, start, start + timedelta(days=6), evaluated_at
    )
    metrics, evaluated = evaluate(predictions, actuals)
    parameters = {
        "baseline": "seasonal_naive_weekly",
        "seasonal_period_days": 7,
        "horizon_days": 7,
        "forecast_start": start.isoformat(),
        "issued_at": issued_at,
        "evaluated_at": evaluated_at,
        "sales_timezone": "America/Guayaquil",
        "missing_policy": "error",
        "wape_scale": "fraction",
        "series_count": len(predictions) // 7,
    }
    lineage = {
        "manifest_sha256": checksum(Path(source) / "manifest.json"),
        "contracts_sha256": checksum(contracts_path),
        "code_sha256": checksum(__file__),
        "training_deliveries": inputs,
        "evaluation_deliveries": targets,
    }
    for name, value in (
        ("parameters.json", parameters),
        ("metrics.json", metrics),
        ("lineage.json", lineage),
    ):
        (output / name).write_bytes(canonical_bytes(value))
    for name, rows in (("forecast.csv", predictions), ("evaluation.csv", evaluated)):
        with (output / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    run_id = log_baseline(tracking_uri, parameters, metrics, output)
    result = {"run_id": run_id, "tracking_uri": tracking_uri, **metrics}
    (output / "run.json").write_bytes(canonical_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/simulation")
    parser.add_argument("--contracts", default="configs/contracts.yaml")
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--issued-at", required=True)
    parser.add_argument("--evaluated-at", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.source,
                args.contracts,
                args.start,
                args.issued_at,
                args.evaluated_at,
                args.output,
                args.tracking_uri,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
