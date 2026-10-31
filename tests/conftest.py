"""Fuentes sintéticas pequeñas, sin dependencia de los CSV de Kaggle."""

import csv
from pathlib import Path

import pytest
import yaml

from reposicion.contracts import Contracts
from reposicion.source_simulator import simulate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def contracts():
    return Contracts(ROOT / "configs/contracts.yaml")


@pytest.fixture
def synthetic(tmp_path, contracts):
    originals = tmp_path / "original"
    originals.mkdir()
    rows = {
        "stores": [
            [1, "Quito", "Pichincha", "A", 1],
            [2, "Guayaquil", "Guayas", "B", 2],
        ],
        "train": [
            [0, "2016-12-29", 1, "DAIRY", "0", 0],
            [1, "2016-12-29", 1, "GROCERY I", "1.25", 2],
            [2, "2016-12-29", 2, "DAIRY", "10", 0],
            [3, "2016-12-30", 1, "DAIRY", "0", 0],
            [4, "2017-01-01", 1, "DAIRY", "5.5", 0],
            [5, "2017-01-02", 1, "DAIRY", "8", 0],
        ],
        "transactions": [["2016-12-29", 1, 12], ["2017-01-02", 1, 9]],
        "oil": [["2016-12-29", ""], ["2016-12-30", "50.1"], ["2017-01-02", "52.2"]],
        "holidays_events": [
            ["2017-01-01", "Holiday", "National", "Ecuador", "Año nuevo", "False"],
            ["2017-01-01", "Transfer", "Local", "Quito", "Traslado local", "False"],
            ["2017-01-02", "Event", "National", "Ecuador", "Evento inesperado", "False"],
            ["2017-01-02", "Holiday", "Regional", "Guayas", "Regional", "True"],
        ],
    }
    for source, records in rows.items():
        with (originals / f"{source}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(contracts.columns(source))
            writer.writerows(records)
    policy = yaml.safe_load((ROOT / "configs/availability.yaml").read_text())
    policy["historical_at"] = "2016-12-31T23:59:59-05:00"
    policy["stores_reference_date"] = "2016-01-01"
    for spec in policy["sources"].values():
        spec["late_percent"] = 0
        spec["correction_percent"] = 0
    settings = tmp_path / "availability.yaml"

    def build(*, output=None):
        settings.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        return simulate(originals, output or tmp_path / "simulation", contracts.path, settings)

    return {
        "originals": originals,
        "output": tmp_path / "simulation",
        "policy": policy,
        "settings": settings,
        "build": build,
    }
