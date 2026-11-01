"""Comparación de métricas obtenidas solo de runs existentes, sin cargar ni ajustar modelos."""

import argparse
import csv
import json
import math
import os
import re
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import yaml
from mlflow import MlflowClient

from reposicion.source_io import canonical_bytes, checksum, parse_instant
from reposicion.tracking import log_experiment

MODELS = ("baseline_semanal", "random_forest", "hist_gradient_boosting", "catboost")
COLORS = ("#666666", "#2574A9", "#E67E22", "#239B56")


def scores(values):
    """Normalización relativa: mayor es mejor; cero óptimo no se sustituye por epsilon."""
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("La normalización requiere errores finitos y no negativos")
    best = min(values)
    if best == 0:
        return [1.0 if x == 0 else 0.0 for x in values]
    return [best / x for x in values]


def metric_row(run, model, label, scope, fold, window):
    metrics = run.data.metrics
    for key in ("mae", "wape", "observations", "actual_sales_sum"):
        if key not in metrics or not math.isfinite(metrics[key]) or metrics[key] < 0:
            raise ValueError(f"Run {run.info.run_id}: métrica ausente/indefinida/inválida: {key}")
    if metrics["observations"] <= 0 or metrics["actual_sales_sum"] <= 0:
        raise ValueError("La comparación requiere cobertura y ventas positivas")
    return {
        "model": model,
        "label": label,
        "scope": scope,
        "fold": fold,
        **window,
        "mae": metrics["mae"],
        "wape": metrics["wape"],
        "wape_percentage": 100 * metrics["wape"],
        "observations": int(metrics["observations"]),
        "actual_sales_sum": metrics["actual_sales_sum"],
        "source_run_id": run.info.run_id,
        "source_experiment_id": run.info.experiment_id,
        "source_group": run.data.params["walk_forward_id"],
    }


def validate_model(global_row, folds):
    """Contrasta el agregado existente con numeradores/denominadores de sus folds."""
    count = sum(r["observations"] for r in folds)
    sales = math.fsum(r["actual_sales_sum"] for r in folds)
    error = math.fsum(r["mae"] * r["observations"] for r in folds)
    if global_row["observations"] != count or not math.isclose(
        global_row["actual_sales_sum"], sales, rel_tol=1e-12
    ):
        raise ValueError("El agregado no conserva la cobertura de sus folds")
    for row in folds + [global_row]:
        expected = row["mae"] * row["observations"] / row["actual_sales_sum"]
        if not math.isclose(row["wape"], expected, rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("MAE y WAPE son inconsistentes con sus denominadores")
    if not math.isclose(global_row["mae"], error / count, rel_tol=1e-10) or not math.isclose(
        global_row["wape"], error / sales, rel_tol=1e-10
    ):
        raise ValueError("El agregado no corresponde a las sumas ponderadas")


def collect(client, config):
    if config["schema_version"] != 1 or tuple(config["models"]) != MODELS:
        raise ValueError("Se requieren exactamente los cuatro modelos configurados")
    starts = config["forecast_starts"]
    if len(starts) != 4:
        raise ValueError("Se requieren cuatro folds")
    global_rows, fold_rows, snapshots = [], [], {}
    reference = None
    for model, source in config["models"].items():
        if not re.fullmatch(r"[a-f0-9]{32}", source["group"]):
            raise ValueError("Identificador de grupo inválido")
        experiment = client.get_experiment_by_name(source["experiment"])
        if experiment is None:
            raise ValueError("No existe el experimento fuente")
        found = client.search_runs(
            [experiment.experiment_id],
            filter_string=f"params.walk_forward_id = '{source['group']}'",
            max_results=1000,
        )
        selected = [
            client.get_run(r.info.run_id)
            for r in found
            if r.data.params.get("model") == source["source_model"]
        ]
        if len(selected) != 5 or any(r.info.status != "FINISHED" for r in selected):
            raise ValueError(f"{model}: se requieren cuatro folds y un agregado FINISHED únicos")
        aggregates = [r for r in selected if r.data.params.get("run_role") == "aggregate"]
        folds = [r for r in selected if r.data.params.get("window_index") is not None]
        if len(aggregates) != 1 or len(folds) != 4:
            raise ValueError("Fuentes ambiguas o incompletas")
        folds.sort(key=lambda r: int(r.data.params["window_index"]))
        rows = []
        for i, run in enumerate(folds, start=1):
            params = run.data.params
            if (
                int(params["window_index"]) != i
                or params["forecast_start"] != starts[i - 1]
                or int(params["horizon_days"]) != 7
            ):
                raise ValueError("Fold, fecha u horizonte incompatible")
            origin = date.fromisoformat(params["forecast_start"])
            if (
                params["forecast_end"] != str(origin + timedelta(days=6))
                or params["training_end"] >= params["forecast_start"]
            ):
                raise ValueError("Ventana temporal inválida")
            if parse_instant(params["evaluated_at"]) <= parse_instant(params["issued_at"]):
                raise ValueError("La evaluación precede a la emisión")
            window = {
                key: params[key]
                for key in ("forecast_start", "forecast_end", "issued_at", "evaluated_at")
            }
            rows.append(metric_row(run, model, source["label"], "fold", i, window))
        summary = metric_row(
            aggregates[0],
            model,
            source["label"],
            "global",
            0,
            {
                "forecast_start": rows[0]["forecast_start"],
                "forecast_end": rows[-1]["forecast_end"],
                "issued_at": "per_fold",
                "evaluated_at": "per_fold",
            },
        )
        validate_model(summary, rows)
        coverage = [
            tuple(
                row[k]
                for k in (
                    "fold",
                    "forecast_start",
                    "forecast_end",
                    "issued_at",
                    "evaluated_at",
                    "observations",
                    "actual_sales_sum",
                )
            )
            for row in rows
        ]
        if reference is not None and coverage != reference:
            raise ValueError("Los modelos no comparten cortes, cobertura y sumas de reales")
        reference = coverage
        global_rows.append(summary)
        fold_rows.extend(rows)
        snapshots.update((r.info.run_id, r.to_dictionary()) for r in selected)
    return global_rows, fold_rows, snapshots


def csv_file(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def normalized_rows(global_rows, fold_rows):
    result = []
    for fold in range(5):
        selected = global_rows if fold == 0 else [r for r in fold_rows if r["fold"] == fold]
        normalized = {metric: scores([r[metric] for r in selected]) for metric in ("mae", "wape")}
        for i, row in enumerate(selected):
            result.append(
                {
                    "model": row["model"],
                    "fold": fold,
                    "scope": "global" if fold == 0 else "fold",
                    "mae_score": normalized["mae"][i],
                    "wape_score": normalized["wape"][i],
                }
            )
    return result


def plots(folder, global_rows, fold_rows, normalized):
    os.environ.setdefault("MPLCONFIGDIR", str(folder.parent / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    def save(fig, name):
        fig.savefig(folder / (name + ".png"), dpi=180, bbox_inches="tight")
        fig.savefig(folder / (name + ".svg"), bbox_inches="tight")
        plt.close(fig)

    labels = [r["label"] for r in global_rows]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), layout="constrained")
    for ax, key, title, factor in zip(
        axes, ("mae", "wape"), ("MAE global — ventas", "WAPE global — %"), (1, 100), strict=True
    ):
        bars = ax.barh(labels, [factor * r[key] for r in global_rows], color=COLORS)
        ax.bar_label(bars, fmt="%.3f", padding=3)
        ax.invert_yaxis()
        ax.set_xlim(left=0)
        ax.set_title(title)
        ax.margins(x=0.18)
        ax.grid(axis="x", alpha=0.2)
    save(fig, "barras_globales")
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), layout="constrained")
    x = np.arange(4)
    width = 0.19
    for ax, key, title, factor in zip(
        axes, ("mae", "wape"), ("MAE por fold — ventas", "WAPE por fold — %"), (1, 100), strict=True
    ):
        for i, (model, label, color) in enumerate(zip(MODELS, labels, COLORS, strict=True)):
            rows = sorted((r for r in fold_rows if r["model"] == model), key=lambda r: r["fold"])
            bars = ax.bar(
                x + (i - 1.5) * width,
                [factor * r[key] for r in rows],
                width,
                label=label,
                color=color,
            )
            ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=2)
        ax.set_xticks(x, ["8–14 ene", "15–21 ene", "22–28 ene", "29 ene–4 feb"])
        ax.set_ylim(bottom=0)
        ax.set_title(title)
        ax.margins(y=0.15)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(ncol=2)
    save(fig, "barras_por_fold")
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), subplot_kw={"projection": "polar"})
    angles = np.linspace(0, 2 * np.pi, 5, endpoint=False).tolist()
    closed = angles + [angles[0]]
    for ax, key, title in zip(
        axes, ("mae_score", "wape_score"), ("MAE normalizado", "WAPE normalizado"), strict=True
    ):
        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        for model, label, color in zip(MODELS, labels, COLORS, strict=True):
            values = [
                r[key]
                for r in sorted(
                    (r for r in normalized if r["model"] == model), key=lambda r: r["fold"]
                )
            ]
            ax.plot(closed, values + [values[0]], label=label, color=color, marker="o")
            ax.fill(closed, values + [values[0]], color=color, alpha=0.04)
        ax.set_xticks(angles, ["Global", "Fold 1", "Fold 2", "Fold 3", "Fold 4"])
        ax.set_ylim(0, 1.05)
        ax.set_title(title, pad=25)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, 0.03))
    fig.suptitle("Error mínimo del eje / error del modelo: 1 = menor error", y=0.98)
    fig.text(
        0.5,
        0.01,
        "MAE y WAPE son proporcionales por eje con iguales observaciones y ventas; los perfiles no son evidencias independientes.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(bottom=0.19, wspace=0.35, top=0.82)
    save(fig, "radar_metricas_normalizadas")


def run(config_path, output, uri):
    config = yaml.safe_load(Path(config_path).read_text())
    client = MlflowClient(tracking_uri=uri)
    global_rows, fold_rows, snapshots = collect(client, config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    folder = output / "artifacts"
    folder.mkdir()
    report_id = uuid4().hex
    normalized = normalized_rows(global_rows, fold_rows)
    for name, rows in (
        ("comparacion_global.csv", global_rows),
        ("comparacion_por_fold.csv", fold_rows),
        ("comparacion_completa.csv", global_rows + fold_rows),
        ("metricas_normalizadas.csv", normalized),
    ):
        csv_file(folder / name, rows)
    lines = [
        "# Comparación de resultados existentes",
        "",
        "Sin entrenamiento ni selección de Champion.",
        "",
        "| Modelo | MAE global | WAPE global | Fuente |",
        "|---|---:|---:|---|",
    ]
    for row in global_rows:
        lines.append(
            f"| {row['label']} | {row['mae']:.6f} | {row['wape_percentage']:.6f} % | {row['source_run_id']} |"
        )
    lines += [
        "",
        "| Modelo | Fold | Horizonte | MAE | WAPE | Fuente |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in fold_rows:
        lines.append(
            f"| {row['label']} | {row['fold']} | {row['forecast_start']}–{row['forecast_end']} | {row['mae']:.6f} | {row['wape_percentage']:.6f} % | {row['source_run_id']} |"
        )
    lines += [
        "",
        "MAE/WAPE se copian directamente de los runs; no se reemplazan por promedios simples.",
        "Radar: score=min(error del eje)/error del modelo. Mayor es mejor; si el mínimo es cero, score=1 para ceros y 0 para los demás.",
        "Con iguales observaciones y ventas reales, MAE y WAPE son proporcionales por eje; sus perfiles normalizados coinciden.",
        "Los resultados corresponden a ventanas ya usadas para desarrollo, sin evaluación final independiente.",
    ]
    (folder / "comparacion_modelos.md").write_text("\n".join(lines) + "\n")
    (folder / "fuentes_mlflow.json").write_bytes(canonical_bytes(snapshots))
    (folder / "normalizacion.json").write_bytes(
        canonical_bytes(
            {
                "formula": "min_error_per_axis / model_error",
                "larger_is_better": True,
                "zero_minimum_policy": "zero_error=1;positive_error=0",
                "axes": ["global", "fold_1", "fold_2", "fold_3", "fold_4"],
                "redundancy": "MAE/WAPE proportional for shared counts/sales",
            }
        )
    )
    (folder / "config.yaml").write_bytes(Path(config_path).read_bytes())
    plots(folder, global_rows, fold_rows, normalized)
    target = config["experiment_name"]
    if target != "comparacion_modelos":
        raise ValueError("Experimento destino incorrecto")
    registered = []
    for summary in global_rows:
        folds = [r for r in fold_rows if r["model"] == summary["model"]]
        metrics = {key: summary[key] for key in ("mae", "wape", "observations", "actual_sales_sum")}
        for row in folds:
            metrics[f"fold_{row['fold']}/mae"] = row["mae"]
            metrics[f"fold_{row['fold']}/wape"] = row["wape"]
        params = {
            "model": summary["model"],
            "comparison_id": report_id,
            "comparison_only": True,
            "source_global_run_id": summary["source_run_id"],
            "source_fold_run_ids": ",".join(r["source_run_id"] for r in folds),
            "source_experiment_id": summary["source_experiment_id"],
            "source_group": summary["source_group"],
            "horizon_days": 7,
            "fold_count": 4,
            "wape_scale": "fraction",
            "training_performed": False,
            "forecast_start": summary["forecast_start"],
            "forecast_end": summary["forecast_end"],
            "config_sha256": checksum(config_path),
            "code_sha256": checksum(__file__),
        }
        new_id = log_experiment(
            uri,
            params,
            metrics,
            folder,
            experiment_name=target,
            run_name=summary["model"] + "-comparacion-" + report_id[:8],
        )
        registered.append(
            {
                "model": summary["model"],
                "run_id": new_id,
                "source_run_id": summary["source_run_id"],
                **metrics,
            }
        )
    for run_id, before in snapshots.items():
        if client.get_run(run_id).to_dictionary() != before:
            raise RuntimeError("Un run de origen cambió durante la comparación")
    result = {
        "comparison_id": report_id,
        "experiment_id": client.get_experiment_by_name(target).experiment_id,
        "tracking_uri": uri,
        "runs": registered,
        "source_run_count": len(snapshots),
    }
    (output / "runs.json").write_bytes(canonical_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/comparacion_modelos.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output, args.tracking_uri), indent=2))


if __name__ == "__main__":
    main()
