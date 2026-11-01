"""Pedidos sobre escenarios conjuntos de cuantiles existentes; sin modelos ni Airflow."""

import argparse
import csv
import hashlib
import json
import math
import platform
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import scipy
import yaml
from scipy.special import ndtr

from reposicion.forecast_publication import atomic_publish
from reposicion.forecast_time import validate_origin
from reposicion.ingestion import _verify_bundle
from reposicion.source_io import canonical_bytes, checksum

METHOD = "piecewise_quantile_gaussian_copula"


def number(value, name, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or (positive and value == 0)
    ):
        raise ValueError(
            f"{name}: se requiere número finito {'positivo' if positive else 'no negativo'}"
        )
    return float(value)


def validate_costs(config):
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Configuración de costos incompatible")
    for key in ["shortage_cost_per_unit", "merma_cost_per_unit"]:
        number(config.get(key), key, positive=True)
    if (
        config.get("horizon_days") != 7
        or type(config.get("lead_time_days")) is not int
        or not 0 <= config["lead_time_days"] < 7
    ):
        raise ValueError("Horizonte siete; plazo entero entre cero y seis días")
    if not isinstance(config.get("monetary_unit"), str) or not config["monetary_unit"].strip():
        raise ValueError("Indicar unidad monetaria común de los costos")
    inventory = config.get("inventory")
    if not isinstance(inventory, dict):
        raise TypeError("Definir supuestos de inventario")
    if (
        inventory.get("policy") != "lost_sales"
        or inventory.get("source") != "assumed_known_at_forecast_issue"
        or inventory.get("terminal_merma_fraction") != 1
    ):
        raise ValueError(
            "Política admitida: inventario conocido al corte, ventas perdidas y merma total al cierre"
        )
    for key in ["on_hand_default", "inbound_at_arrival_default", "quantity_step"]:
        number(inventory.get(key), key)
    overrides = inventory.get("per_series")
    if not isinstance(overrides, list):
        raise TypeError("per_series debe ser una lista")
    seen = set()
    for row in overrides:
        if (
            not isinstance(row, dict)
            or set(row) != {"store_nbr", "family", "on_hand", "inbound_at_arrival"}
            or type(row["store_nbr"]) is not int
            or row["store_nbr"] <= 0
            or not isinstance(row["family"], str)
            or not row["family"].strip()
        ):
            raise ValueError("Override de inventario inválido")
        key = row["store_nbr"], row["family"]
        if key in seen:
            raise ValueError("Inventario por serie duplicado")
        seen.add(key)
        number(row["on_hand"], "on_hand")
        number(row["inbound_at_arrival"], "inbound_at_arrival")
    distribution = config.get("demand_distribution")
    if not isinstance(distribution, dict):
        raise TypeError("Definir distribución de demanda")
    if distribution.get("method") != METHOD:
        raise ValueError("Distribución no soportada")
    rho = number(distribution.get("daily_latent_correlation"), "daily_latent_correlation")
    if rho >= 1:
        raise ValueError("Correlación latente debe estar en [0,1)")
    number(distribution.get("tail_spread_multiplier"), "tail_spread_multiplier", positive=True)
    n = distribution.get("scenario_count")
    if type(n) is not int or not 128 <= n <= 1000000 or n % 2:
        raise ValueError("scenario_count debe ser par y estar entre 128 y 1000000")
    if type(distribution.get("seed")) is not int or distribution["seed"] < 0:
        raise ValueError("Semilla entera no negativa requerida")
    return config


def load_costs(path):
    return validate_costs(yaml.safe_load(Path(path).read_bytes()))


def demand_scenarios(quantiles, config, series_key):
    """Copula normal equicorrelacionada + inversas marginales monótonas acotadas."""
    q = np.asarray(quantiles, dtype=float)
    if (
        q.shape != (7, 3)
        or not np.isfinite(q).all()
        or (q < 0).any()
        or (np.diff(q, axis=1) < 0).any()
    ):
        raise ValueError("Se requieren siete días con 0 <= P10 <= P50 <= P90")
    d = config["demand_distribution"]
    # Los costos/inventario no entran en la semilla: escenarios comunes al comparar costos.
    seed = int.from_bytes(
        hashlib.sha256(canonical_bytes([d["seed"], *series_key])).digest()[:16], "big"
    )
    rng = np.random.Generator(np.random.PCG64(seed))
    half = d["scenario_count"] // 2
    rho = d["daily_latent_correlation"]
    latent = math.sqrt(rho) * rng.standard_normal((half, 1)) + math.sqrt(
        1 - rho
    ) * rng.standard_normal((half, 7))
    uniforms = ndtr(np.concatenate([latent, -latent], axis=0))
    result = np.empty_like(uniforms)
    for day in range(7):
        p10, p50, p90 = q[day]
        lower = max(0, p10 - d["tail_spread_multiplier"] * (p50 - p10))
        upper = p90 + d["tail_spread_multiplier"] * (p90 - p50)
        if not math.isfinite(upper):
            raise ValueError("Cola fuera de rango numérico")
        result[:, day] = np.interp(
            uniforms[:, day], [0, 0.1, 0.5, 0.9, 1], [lower, p10, p50, p90, upper]
        )
    return result


def decision(scenarios, config, on_hand, inbound):
    """Óptimo empírico de costo lineal; recepción tras L días dentro del horizonte."""
    if (
        scenarios.ndim != 2
        or scenarios.shape[0] == 0
        or scenarios.shape[1] != 7
        or not np.isfinite(scenarios).all()
        or (scenarios < 0).any()
    ):
        raise ValueError("Escenarios inválidos")
    on_hand = number(on_hand, "on_hand")
    inbound = number(inbound, "inbound")
    lead = config["lead_time_days"]
    before = scenarios[:, :lead].sum(axis=1)
    after = scenarios[:, lead:].sum(axis=1)
    unavoidable = np.maximum(before - on_hand, 0)
    available = np.maximum(on_hand - before, 0) + inbound
    net = after - available
    if not np.isfinite(net).all() or not np.isfinite(before).all():
        raise ValueError("Demanda acumulada fuera de rango numérico")
    cu, co = config["shortage_cost_per_unit"], config["merma_cost_per_unit"]
    scale = max(cu, co)
    alpha = (cu / scale) / ((cu / scale) + (co / scale))
    target = float(np.quantile(net, alpha, method="inverted_cdf"))
    quantity = max(0, target)

    def loss(q):
        return float(np.mean(cu * np.maximum(net - q, 0) + co * np.maximum(q - net, 0)))

    step = config["inventory"]["quantity_step"]
    if step:
        candidates = {
            max(0, math.floor(quantity / step) * step),
            max(0, math.ceil(quantity / step) * step),
        }
        quantity = min(candidates, key=lambda q: (loss(q), q))
    shortage = float(np.mean(unavoidable + np.maximum(net - quantity, 0)))
    merma = float(np.mean(np.maximum(quantity - net, 0)))
    cumulative = scenarios.sum(axis=1)
    summary = np.quantile(cumulative, [0.1, 0.5, 0.9], method="inverted_cdf")
    result = {
        "critical_fractile": alpha,
        "net_demand_target": target,
        "suggested_order": quantity,
        "demand_7d_p10": float(summary[0]),
        "demand_7d_p50": float(summary[1]),
        "demand_7d_p90": float(summary[2]),
        "expected_unavoidable_shortage_before_arrival": float(np.mean(unavoidable)),
        "expected_shortage_units": shortage,
        "expected_merma_units": merma,
        "expected_shortage_cost": cu * shortage,
        "expected_merma_cost": co * merma,
        "expected_total_cost": cu * shortage + co * merma,
    }
    if any(not math.isfinite(x) for x in result.values()):
        raise ValueError("Resultado fuera de rango numérico")
    return result


def read_forecasts(directory):
    directory = Path(directory)
    if (directory / "manifest.json").exists():
        _verify_bundle(directory)
    lineage = json.loads((directory / "lineage.json").read_text())
    origin = validate_origin(lineage["origin"], lineage["issued_at"])
    if lineage["horizon_days"] != 7:
        raise ValueError("Se requieren siete días de pronósticos")
    groups = {}
    count = 0
    with (directory / "forecast_quantiles.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            day = date.fromisoformat(row["date"])
            store = int(row["store_nbr"])
            family = row["family"]
            offset = (day - origin).days
            if (
                store <= 0
                or not family.strip()
                or not 0 <= offset < 7
                or ("horizon" in row and int(row["horizon"]) != offset + 1)
            ):
                raise ValueError("Clave/horizonte de pronóstico inválido")
            days = groups.setdefault((store, family), {})
            if offset in days:
                raise ValueError("Pronóstico duplicado")
            days[offset] = [float(row[k]) for k in ["p10", "p50", "p90"]]
            count += 1
    if (
        not groups
        or count != lineage["rows"]
        or any(set(days) != set(range(7)) for days in groups.values())
    ):
        raise ValueError("Cada serie debe tener siete fechas completas; no se imputan ausencias")
    return (
        origin,
        lineage,
        {key: [days[i] for i in range(7)] for key, days in sorted(groups.items())},
    )


def recommend(forecast_dir, costs_path, output_root):
    forecast_dir = Path(forecast_dir)
    config_bytes = Path(costs_path).read_bytes()
    config = validate_costs(yaml.safe_load(config_bytes))
    if Path(output_root).resolve().is_relative_to(forecast_dir.resolve()):
        raise ValueError("El destino debe estar separado del directorio de pronósticos")
    hashes = {
        name: checksum(forecast_dir / name) for name in ["forecast_quantiles.csv", "lineage.json"]
    }
    origin, lineage, groups = read_forecasts(forecast_dir)
    overrides = {(r["store_nbr"], r["family"]): r for r in config["inventory"]["per_series"]}
    if set(overrides) - set(groups):
        raise ValueError("Override de inventario para una serie desconocida")
    identity = {
        "schema_version": 1,
        "forecast_files_sha256": hashes,
        "costs_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "code_sha256": checksum(__file__),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "python_version": platform.python_version(),
    }

    def generate(stage):
        rows = []
        for (store, family), quantiles in groups.items():
            override = overrides.get((store, family), {})
            stock = override.get("on_hand", config["inventory"]["on_hand_default"])
            inbound = override.get(
                "inbound_at_arrival", config["inventory"]["inbound_at_arrival_default"]
            )
            scenarios = demand_scenarios(quantiles, config, [str(origin), store, family])
            rows.append(
                {
                    "origin": str(origin),
                    "horizon_end": str(origin + timedelta(days=6)),
                    "store_nbr": store,
                    "family": family,
                    "arrival_date": str(origin + timedelta(days=config["lead_time_days"])),
                    "days_covered_after_arrival": 7 - config["lead_time_days"],
                    "on_hand": stock,
                    "inbound_at_arrival": inbound,
                    "shortage_cost_per_unit": config["shortage_cost_per_unit"],
                    "merma_cost_per_unit": config["merma_cost_per_unit"],
                    **decision(scenarios, config, stock, inbound),
                }
            )
        with (stage / "suggested_orders.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        if (
            any(checksum(forecast_dir / name) != digest for name, digest in hashes.items())
            or Path(costs_path).read_bytes() != config_bytes
        ):
            raise ValueError("Entradas cambiaron durante el cálculo")
        (stage / "costs.yaml").write_bytes(config_bytes)
        (stage / "lineage.json").write_bytes(
            canonical_bytes(
                {
                    "identity": identity,
                    "forecast_lineage": lineage,
                    "forecast_path": str(forecast_dir),
                    "assumptions": config,
                    "series_count": len(rows),
                    "method": "joint daily scenarios; quantile of net post-arrival demand; empirical linear underage/overage optimum",
                    "limitations": [
                        "Daily dependence and tails are explicit assumptions, not identified by P10/P50/P90.",
                        "Horizon is seven days from origin, including lead time; not lead time plus seven.",
                        "Lost sales before arrival cannot be recovered by this order.",
                        "All remaining stock is treated as merma at horizon end; no salvage or later replenishment.",
                        "Quantities retain fractional sales units; no empirical inventory observations used.",
                    ],
                }
            )
        )

    return atomic_publish(output_root, identity, generate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-dir", required=True)
    parser.add_argument("--costs", default="configs/costs.yaml")
    parser.add_argument("--output-root", default="reports/orders")
    args = parser.parse_args()
    print(json.dumps(recommend(args.forecast_dir, args.costs, args.output_root), indent=2))


if __name__ == "__main__":
    main()
