"""Estimador CatBoost serializable también al ejecutar la CLI con python -m."""

import numpy as np
from catboost import CatBoostRegressor
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_is_fitted


class CatBoostSalesRegressor(RegressorMixin, BaseEstimator):
    """El pipeline persistido incluye piso cero, sin alterar etiquetas de entrenamiento."""

    def __init__(self, parameters):
        self.parameters = parameters

    def fit(self, x, y):
        self.model_ = CatBoostRegressor(**self.parameters)
        self.model_.fit(x, y)
        return self

    def predict(self, x):
        check_is_fitted(self, "model_")
        return np.maximum(self.model_.predict(x), 0.0)
