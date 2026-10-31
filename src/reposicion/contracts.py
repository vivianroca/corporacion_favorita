"""Contratos de los CSV reales, sin imputación ni conversión de ausencia a cero."""

import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml


class ContractError(ValueError):
    """Una fuente incumple un contrato de datos o una relación declarada."""


class Contracts:
    def __init__(self, path):
        self.path = Path(path)
        document = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise ContractError("Versión de contratos no soportada")
        self.sources = document["sources"]
        for source, spec in self.sources.items():
            for key in [spec["primary_key"], *spec.get("unique_keys", [])]:
                if not key or not set(key) <= spec["columns"].keys():
                    raise ContractError(f"{source}: clave de contrato inválida")
            if any(
                field["type"] not in {"integer", "decimal", "date", "text", "boolean"}
                for field in spec["columns"].values()
            ):
                raise ContractError(f"{source}: tipo de contrato desconocido")

    def columns(self, source):
        return list(self.sources[source]["columns"])

    def keys(self, source):
        spec = self.sources[source]
        return [spec["primary_key"], *spec.get("unique_keys", [])]

    def validate_row(self, source, row):
        columns = self.sources[source]["columns"]
        if set(row) != set(columns):
            raise ContractError(f"{source}: columnas incorrectas")
        typed = {}
        for name, spec in columns.items():
            raw = row[name]
            if not isinstance(raw, str):
                raise ContractError(f"{source}.{name}: valor no textual en CSV")
            if not raw.strip():
                if spec.get("nullable", False):
                    typed[name] = None
                    continue
                raise ContractError(f"{source}.{name}: nulo no permitido")
            try:
                kind = spec["type"]
                if kind == "integer":
                    if not re.fullmatch(r"[+-]?\d+", raw):
                        raise ValueError("se esperaba entero")
                    value = int(raw)
                elif kind == "decimal":
                    value = Decimal(raw)
                    if not value.is_finite():
                        raise ValueError("decimal no finito")
                elif kind == "date":
                    value = date.fromisoformat(raw)
                    if value.isoformat() != raw:
                        raise ValueError("fecha no canónica")
                elif kind == "boolean":
                    if raw not in {"True", "False"}:
                        raise ValueError("se esperaba True o False")
                    value = raw == "True"
                else:
                    value = raw
                if "minimum" in spec and value < spec["minimum"]:
                    raise ValueError("valor inferior al mínimo")
                if "enum" in spec and value not in spec["enum"]:
                    raise ValueError("categoría desconocida")
            except (ValueError, InvalidOperation) as error:
                raise ContractError(f"{source}.{name}: {raw!r}: {error}") from error
            typed[name] = value
        return typed

    def iter_csv(self, source, path):
        """Valida estructura y filas; claves globales se controlan en el generador."""
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames
            if (
                header is None
                or len(header) != len(set(header))
                or set(header) != set(self.columns(source))
            ):
                raise ContractError(f"{source}: cabecera incompatible: {header}")
            try:
                for number, row in enumerate(reader, 2):
                    try:
                        typed = self.validate_row(source, row)
                    except ContractError as error:
                        raise ContractError(f"{path}:{number}: {error}") from error
                    yield row, typed
            except csv.Error as error:
                raise ContractError(f"{path}: CSV mal formado: {error}") from error


def validate_relation(source, row, stores):
    """Comprueba referencias sin exigir actividad ni completar pares ausentes."""
    if source in {"train", "transactions"} and row["store_nbr"] not in stores:
        raise ContractError(f"{source}: tienda desconocida {row['store_nbr']}")
    if source == "holidays_events":
        locale, name = row["locale"], row["locale_name"]
        allowed = {
            "National": {"Ecuador"},
            "Regional": {s["state"] for s in stores.values()},
            "Local": {s["city"] for s in stores.values()},
        }
        if name not in allowed[locale]:
            raise ContractError(f"{source}: ámbito geográfico sin referencia: {locale}/{name}")


def event_applies(event, store):
    """Solo alcance geográfico; no decide si el día fue descanso efectivo."""
    return {
        "National": event["locale_name"] == "Ecuador",
        "Regional": event["locale_name"] == store["state"],
        "Local": event["locale_name"] == store["city"],
    }[event["locale"]]
