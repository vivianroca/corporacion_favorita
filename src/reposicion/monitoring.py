"""Evaluación revisable de predicciones inmutables contra verdad conocida al corte."""

import argparse
import csv
import fcntl
import json
import math
import sys
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from reposicion.contracts import Contracts
from reposicion.forecast_publication import atomic_publish, publication_id
from reposicion.forecast_time import TIMEZONE
from reposicion.ingestion import _verify_bundle
from reposicion.random_forest import write_csv
from reposicion.snapshot_catalog import select_snapshot
from reposicion.source_io import IntegrityError, canonical_bytes, checksum, parse_instant


def compare(predictions, actuals, receipts, as_of):
    """MAE/WAPE de P50 y cobertura inclusiva solo sobre pares observados."""
    today = parse_instant(as_of).astimezone(ZoneInfo(TIMEZONE)).date()
    rows, seen = [], set()
    for raw in predictions:
        key = raw["date"], int(raw["store_nbr"]), raw["family"]
        if key in seen:
            raise ValueError("Predicción duplicada")
        seen.add(key)
        p10, p50, p90 = (float(raw[k]) for k in ("p10", "p50", "p90"))
        if not all(math.isfinite(x) for x in (p10, p50, p90)) or not 0 <= p10 <= p50 <= p90:
            raise ValueError("Cuantiles inválidos")
        receipt = receipts.get(key[0])
        status = (
            "future_date"
            if date.fromisoformat(key[0]) >= today
            else "not_delivered"
            if receipt is None
            else "absent_record"
            if key not in actuals
            else "evaluated"
        )
        actual = actuals.get(key) if status == "evaluated" else None
        if actual is not None and (not math.isfinite(actual) or actual < 0):
            raise ValueError("Venta real inválida")
        rows.append(
            {
                "date": key[0],
                "store_nbr": key[1],
                "family": key[2],
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "actual": actual,
                "status": status,
                "absolute_error": abs(actual - p50) if actual is not None else None,
                "covered": int(p10 <= actual <= p90) if actual is not None else None,
                "actual_delivery_id": receipt["delivery_id"] if receipt else None,
            }
        )
    paired = [r for r in rows if r["status"] == "evaluated"]
    n = len(paired)
    sales = math.fsum(r["actual"] for r in paired)
    error = math.fsum(r["absolute_error"] for r in paired)
    metrics = {
        "forecast_rows": len(rows),
        "evaluated_rows": n,
        "pending_rows": len(rows) - n,
        "data_completion_fraction": n / len(rows) if rows else 0,
        "actual_sales_sum": sales,
        "mae": error / n if n else None,
        "wape": error / sales if n and sales else None,
        "coverage_p10_p90": sum(r["covered"] for r in paired) / n if n else None,
    }
    return rows, metrics


def truth_snapshot(directory, contracts_path, cutoff, dates):
    manifest = _verify_bundle(directory)
    if manifest["contracts_sha256"] != checksum(contracts_path):
        raise IntegrityError("Contrato incompatible")
    if parse_instant(manifest["as_of"]) > parse_instant(cutoff):
        raise ValueError("Snapshot posterior a la evaluación")
    if "validation_manifest_sha256" in manifest:
        validated = directory.parent.parent / "validated" / directory.name
        report = _verify_bundle(validated)
        if (
            checksum(validated / "manifest.json") != manifest["validation_manifest_sha256"]
            or report["plan_id"] != manifest["plan_id"]
        ):
            raise IntegrityError("Snapshot sin validación correspondiente")
    receipts = {}
    for r in manifest.get("active_receipts", manifest.get("deliveries", [])):
        if parse_instant(r["available_at"]) > parse_instant(manifest["as_of"]):
            raise IntegrityError("Recibo posterior al snapshot")
        if r["source"] == "train" and r["reference_date"] in dates:
            if r["reference_date"] in receipts:
                raise IntegrityError("Revisiones activas ambiguas")
            receipts[r["reference_date"]] = r
    contracts = Contracts(contracts_path)
    actuals = {}
    with (directory / "train.csv").open(newline="") as stream:
        for raw in csv.DictReader(stream):
            if raw["date"] not in dates:
                continue
            if raw["date"] not in receipts:
                raise IntegrityError("Venta sin recibo disponible")
            row = contracts.validate_row("train", raw)
            key = str(row["date"]), row["store_nbr"], row["family"]
            if key in actuals:
                raise IntegrityError("Venta duplicada")
            actuals[key] = float(row["sales"])
    return manifest, receipts, actuals


def merged_truth(work_root, contracts_path, cutoff, dates):
    """Última revisión disponible por fecha, incluso con snapshots parciales."""
    root = Path(work_root)
    paths = sorted(
        list((root / "snapshots").glob("*/manifest.json"))
        + list((root / "automatic").glob("*/publications/*/manifest.json"))
    )
    chosen = {}
    for path in paths:
        header = json.loads(path.read_text())
        if parse_instant(header["as_of"]) > parse_instant(cutoff):
            continue
        _, receipts, actuals = truth_snapshot(path.parent, contracts_path, cutoff, dates)
        for day, receipt in receipts.items():
            revision = int(receipt["revision"])
            previous = chosen.get(day)
            if previous and revision == int(previous[0]["revision"]):
                if receipt["payload_sha256"] != previous[0]["payload_sha256"]:
                    raise IntegrityError("Misma revisión con contenido diferente")
                continue
            if previous and revision < int(previous[0]["revision"]):
                continue
            rows = {k: v for k, v in actuals.items() if k[0] == day}
            chosen[day] = (
                receipt,
                rows,
                {
                    "snapshot_id": path.parent.name,
                    "manifest_sha256": checksum(path),
                    "as_of": header["as_of"],
                },
            )
    receipts = {day: value[0] for day, value in chosen.items()}
    actuals = {k: v for _, rows, _ in chosen.values() for k, v in rows.items()}
    sources = sorted(
        {v[2]["snapshot_id"]: v[2] for v in chosen.values()}.values(),
        key=lambda r: r["snapshot_id"],
    )
    return (
        {"as_of": max((r["as_of"] for r in sources), key=parse_instant, default=cutoff)},
        receipts,
        actuals,
        sources,
    )


def register(uri, directory):
    """Recupera el mismo run tras un fallo, sin duplicar métricas ni artefactos."""
    import mlflow

    from reposicion.uncertainty import artifact_bytes

    manifest = _verify_bundle(directory)
    eid = manifest["publication_id"]
    client = mlflow.MlflowClient(tracking_uri=uri)
    name = "corporacion_favorita-seguimiento"
    experiment = client.get_experiment_by_name(name)
    experiment_id = experiment.experiment_id if experiment else client.create_experiment(name)
    found = client.search_runs(
        [experiment_id], filter_string=f"tags.evaluation_id = '{eid}'", max_results=100
    )
    if len(found) > 1:
        raise IntegrityError("Runs de evaluación duplicados")
    run = (
        found[0]
        if found
        else client.create_run(
            experiment_id,
            tags={
                "evaluation_id": eid,
                "mlflow.runName": "seguimiento-" + eid[:12],
                "training_performed": "false",
            },
        )
    )
    rid = run.info.run_id
    metrics = json.loads((directory / "metrics.json").read_text())
    lineage = json.loads((directory / "lineage.json").read_text())
    params = {
        "evaluation_id": eid,
        "forecast_publication_id": lineage["forecast_publication_id"],
        "forecast_sha256": lineage["forecast_sha256"],
        "snapshot_id": lineage["snapshot_id"],
        "evaluated_as_of": lineage["evaluated_as_of"],
        "model_run_id": lineage["model_run_id"],
        "model_version": lineage["model_version"],
        "point_metric": "p50",
        "wape_scale": "fraction",
        "wape_defined": str(metrics["wape"] is not None).lower(),
        "coverage_definition": "p10 <= actual <= p90, observed pairs only",
        "model_dvc_tags": json.dumps(lineage["model_dvc_tags"], sort_keys=True),
    }
    for key, value in params.items():
        if key in run.data.params:
            if run.data.params[key] != str(value):
                raise IntegrityError("Parámetro remoto incompatible")
        else:
            client.log_param(rid, key, value)
    for key, value in metrics.items():
        if value is None:
            continue
        if key in run.data.metrics:
            if run.data.metrics[key] != value:
                raise IntegrityError("Métrica remota incompatible")
        else:
            client.log_metric(rid, key, value)
    existing = {a.path for a in client.list_artifacts(rid)}
    for path in sorted(directory.iterdir()):
        if path.name in existing:
            if artifact_bytes(uri, run, path.name) != path.read_bytes():
                raise IntegrityError("Artefacto remoto incompatible")
        else:
            client.log_artifact(rid, str(path))
    if run.info.status != "FINISHED":
        client.set_terminated(rid, "FINISHED")
    return {"mlflow_run_id": rid, "experiment_id": str(experiment_id)}


def evaluate(
    work_root,
    forecasts_root,
    output_root,
    contracts_path,
    as_of,
    uri,
    snapshot_id=None,
    forecast_id=None,
):
    directory = select_snapshot(work_root, as_of, snapshot_id) if snapshot_id else None
    snapshot_label = directory.name if directory else "composite"
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    publications = sorted(Path(forecasts_root).glob("*/manifest.json"))
    if forecast_id:
        publications = [p for p in publications if p.parent.name == forecast_id]
        if not publications:
            raise ValueError("Pronóstico no publicado")
    result = []
    # Serializa tanto publicación local como creación/reparación del run remoto.
    with (root / ".monitoring.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for path in publications:
            forecast = _verify_bundle(path.parent)
            identity = forecast["identity"]
            if parse_instant(identity["issued_at"]) > parse_instant(as_of):
                continue
            with (path.parent / "forecast_quantiles.csv").open(newline="") as stream:
                predictions = list(csv.DictReader(stream))
            dates = {r["date"] for r in predictions}
            if directory:
                truth, receipts, actuals = truth_snapshot(directory, contracts_path, as_of, dates)
                sources = [
                    {
                        "snapshot_id": directory.name,
                        "manifest_sha256": checksum(directory / "manifest.json"),
                        "as_of": truth["as_of"],
                    }
                ]
            else:
                truth, receipts, actuals, sources = merged_truth(
                    work_root, contracts_path, as_of, dates
                )
            rows, metrics = compare(predictions, actuals, receipts, as_of)
            # Identidad basada en la verdad efectiva; un día sin novedades no duplica runs.
            state = {
                "forecast_publication_id": path.parent.name,
                "forecast_sha256": checksum(path.parent / "forecast_quantiles.csv"),
                "truth_receipts": sorted(receipts.values(), key=lambda r: r["reference_date"]),
                "paired_rows_sha256": publication_id(rows),
                "contracts_sha256": checksum(contracts_path),
                "evaluation_code_sha256": checksum(__file__),
            }

            def generate(
                stage,
                rows=rows,
                metrics=metrics,
                path=path,
                state=state,
                identity=identity,
                truth=truth,
                sources=sources,
            ):
                write_csv(stage / "evaluation.csv", rows)
                (stage / "metrics.json").write_bytes(canonical_bytes(metrics))
                (stage / "lineage.json").write_bytes(
                    canonical_bytes(
                        {
                            "forecast_publication_id": path.parent.name,
                            "forecast_sha256": state["forecast_sha256"],
                            "forecast_manifest_sha256": checksum(path),
                            "evaluated_as_of": as_of,
                            "snapshot_id": snapshot_label,
                            "snapshot_manifests_sha256": publication_id(sources),
                            "snapshots": sources,
                            "snapshot_as_of": truth["as_of"],
                            "actual_receipts": state["truth_receipts"],
                            "model_run_id": identity["model_run_id"],
                            "model_version": identity["model_version"],
                            "model_dvc_tags": json.loads(
                                (path.parent / "lineage.json").read_text()
                            ).get("model_tags", {}),
                            "metrics_policy": "P50; observed closed-day pairs; zero is observed; missing is never zero",
                        }
                    )
                )

            published = atomic_publish(root, state, generate)
            target = Path(published["path"])
            remote = register(uri, target) if metrics["evaluated_rows"] else {"mlflow_run_id": None}
            result.append({**published, **remote, "metrics": metrics})
    return {"evaluated_as_of": as_of, "snapshot_id": snapshot_label, "evaluations": result}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("work-root", "forecasts-root", "output-root", "contracts-path", "as-of", "uri"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--snapshot-id")
    p.add_argument("--forecast-id")
    with redirect_stdout(sys.stderr):
        result = evaluate(**vars(p.parse_args()))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
