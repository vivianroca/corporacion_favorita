"""Calendario por disponibilidad y relleno histórico sin mezclar escalas de familias."""

import math
from collections import defaultdict
from datetime import timedelta
from statistics import fmean, median

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

from reposicion.hist_gradient_boosting import model_pipeline as old_boosting_pipeline
from reposicion.random_forest import LAGS, features
from reposicion.random_forest import model_pipeline as old_forest_pipeline

SALE_FEATURES = (
    *[f"lag_{lag}" for lag in LAGS],
    "recent_mean",
    "normal_weekday_median",
    "recent_normal_mean",
)


class CalendarView:
    def __init__(self, stores, events):
        self.stores = stores
        self.events = events
        self.cache = {}

    def flags(self, day, store):
        if (day, store) in self.cache:
            return self.cache[day, store]
        if store not in self.stores:
            raise ValueError("Tienda sin ubicación conocida al corte")
        location = self.stores[store]
        applicable = [
            row
            for row in self.events.get(day, [])
            if row["locale"] == "National"
            or (row["locale"] == "Regional" and row["locale_name"] == location["state"])
            or (row["locale"] == "Local" and row["locale_name"] == location["city"])
        ]
        active = [
            r
            for r in applicable
            if r["type"] in {"Holiday", "Transfer", "Additional", "Bridge"} and not r["transferred"]
        ]
        result = {
            "exceptional": int(bool(applicable)),
            "holiday_active": int(bool(active)),
            "transferred": int(any(r["transferred"] for r in applicable)),
            "work_day": int(any(r["type"] == "Work Day" for r in applicable)),
            "event": int(any(r["type"] == "Event" for r in applicable)),
        }
        for scope in ("National", "Regional", "Local"):
            result["holiday_" + scope.lower()] = int(any(r["locale"] == scope for r in active))
        self.cache[day, store] = result
        return result


class TemporalFeatures:
    """Cada contexto selecciona primero por as-of; la fecha del feriado puede ser futura."""

    def __init__(self, catalog, contracts):
        self.catalog, self.contracts = catalog, contracts
        self.payloads = {}
        self.views = {}
        self.begin_window()

    def begin_window(self):
        self.contexts = {}
        self.receipts = {}

    def prepare(self, origin, cutoff):
        key = origin.isoformat(), cutoff
        if key in self.contexts:
            return self.views[key][0]
        if key not in self.views:
            start, end = origin - timedelta(days=28), origin + timedelta(days=6)
            selected = [
                r
                for r in self.catalog.available(cutoff, latest=True)
                if r["source"] == "stores"
                or (
                    r["source"] == "holidays_events"
                    and start.isoformat() <= r["reference_date"] <= end.isoformat()
                )
            ]
            stores, events = {}, defaultdict(list)
            for receipt in selected:
                rid = receipt["delivery_id"]
                if rid not in self.payloads:
                    self.payloads[rid] = [
                        self.contracts.validate_row(receipt["source"], row)
                        for row in self.catalog.read(receipt, as_of=cutoff)
                    ]
                for row in self.payloads[rid]:
                    if receipt["source"] == "stores":
                        stores[row["store_nbr"]] = row
                    else:
                        events[row["date"]].append(row)
            self.views[key] = CalendarView(stores, events), selected
        view, receipts = self.views[key]
        self.contexts[key] = {
            "origin": key[0],
            "as_of": cutoff,
            "delivery_ids": [r["delivery_id"] for r in receipts],
        }
        self.receipts.update((r["delivery_id"], r) for r in receipts)
        return view

    def enrich(self, history, origin, target, store, family, cutoff):
        row = features(history, origin, target, store, family)
        calendar = self.prepare(origin, cutoff)
        row.update({"target_" + k: v for k, v in calendar.flags(target, store).items()})
        comparable = []
        for lag in LAGS:
            day = target - timedelta(days=lag)
            flags = calendar.flags(day, store)
            row.update({f"lag_{lag}_" + k: v for k, v in flags.items()})
            value = history.get((day, store, family))
            row[f"lag_{lag}_observed_zero"] = int(value == 0) if value is not None else 0
            if value is not None and not flags["exceptional"]:
                comparable.append(value)
        normal = [
            history[(origin - timedelta(days=i), store, family)]
            for i in range(1, 8)
            if (origin - timedelta(days=i), store, family) in history
            and not calendar.flags(origin - timedelta(days=i), store)["exceptional"]
        ]
        row["normal_weekday_median"] = median(comparable) if comparable else float("nan")
        row["normal_weekday_count"] = len(comparable)
        row["recent_normal_mean"] = fmean(normal) if normal else float("nan")
        row["recent_normal_count"] = len(normal)
        for key in ("normal_weekday_median", "recent_normal_mean", "recent_mean"):
            row[key + "_missing"] = int(not math.isfinite(row[key]))
        return row

    def lineage(self):
        return {
            "contexts": list(self.contexts.values()),
            "receipts": list(self.receipts.values()),
            "meaning": "flags describe known events only; no record is not proof of no event",
        }


def records(value):
    return value.to_dict("records") if isinstance(value, pd.DataFrame) else value


class SeriesFamilyImputer(TransformerMixin, BaseEstimator):
    """Solo reemplaza ausencias: misma serie, luego misma familia; nunca mediana global."""

    def fit(self, x, y=None):
        by_series, by_family = defaultdict(list), defaultdict(list)
        for row in records(x):
            for key in SALE_FEATURES:
                value = row[key]
                if not math.isfinite(value) or (
                    key.startswith("lag_") and row[key + "_exceptional"]
                ):
                    continue
                by_series[row["store"], row["family"], key].append(value)
                by_family[row["family"], key].append(value)
        self.series_ = {key: median(values) for key, values in by_series.items()}
        self.families_ = {key: median(values) for key, values in by_family.items()}
        return self

    def transform(self, x):
        check_is_fitted(self, "series_")
        result = []
        for raw in records(x):
            row = dict(raw)
            for key in SALE_FEATURES:
                if math.isfinite(row[key]):
                    continue
                # Los otros rezagos comparables son historia de esa misma serie conocida al emitir.
                comparable = (
                    raw["normal_weekday_median"] if key.startswith("lag_") else float("nan")
                )
                if math.isfinite(comparable):
                    row[key] = comparable
                else:
                    series_key = row["store"], row["family"], key
                    family_key = row["family"], key
                    if series_key in self.series_:
                        row[key] = self.series_[series_key]
                    elif family_key in self.families_:
                        row[key] = self.families_[family_key]
                    else:
                        raise ValueError(f"Sin historia de la serie/familia para imputar {key}")
            result.append(row)
        return result


def temporal_pipeline(name):
    if name == "random_forest":
        estimator = old_forest_pipeline().named_steps["forest"]
    elif name == "hist_gradient_boosting":
        estimator = old_boosting_pipeline().named_steps["boosting"]
    else:
        raise ValueError("Candidato desconocido")
    return Pipeline(
        [
            ("series_impute", SeriesFamilyImputer()),
            ("encode", DictVectorizer(sparse=False)),
            ("estimator", estimator),
        ]
    )
