# Modelos existentes publicados en MLflow

Se registraron los doce pipelines ya entrenados de la variante temporal v2: tres
algoritmos y cuatro folds. No se ejecutó `fit`, ningún entrenamiento ni nuevos runs.

| Registered Model | Versiones de los cuatro folds v2 | Estado |
|---|---|---|
| corporacion_favorita_random_forest | 1, 2, 3, 4 | READY |
| corporacion_favorita_hist_gradient_boosting | 2, 3, 4, 5 | READY |
| corporacion_favorita_catboost | 1, 2, 3, 4 | READY |

Las versiones siguen los cortes 2017-01-08, 15, 22 y 29, respectivamente. La versión
1 anterior de HistGradientBoosting se conserva; corresponde al experimento previo
con variables originales. No se registró el baseline como modelo ajustado.

Los modelos están disponibles tanto en **Logged Models** de los experimentos 4 y 5
como en [Model Registry](http://localhost:5011/#/models). Cada modelo contiene el
pipeline completo, formato sklearn/pyfunc, firma de entrada DataFrame, ejemplo de
entrada, código y dependencias fijadas. CatBoost conserva también su piso cero
como parte del pipeline. El modelo se vincula al run que realmente lo entrenó.

MAE y WAPE del fold se asociaron al Logged Model reutilizando el evento histórico
original: mismo valor, timestamp y step, sin duplicar ni alterar el historial del run.
Los parámetros, cortes y métricas de los 38 runs existentes permanecen intactos.
Se añadieron únicamente las asociaciones de salida de los doce modelos solicitados.
Las métricas globales del backtest siguen en los runs agregados; no se atribuye el
resultado de cuatro modelos distintos a una sola versión de fold.

No se asignaron aliases, stages de promoción ni Champion. READY significa que el
artefacto está disponible para cargar, no que el modelo haya sido elegido para producción.

## Repetir el registro sin entrenar

```bash
.venv/bin/python -m reposicion.register_models
```

La operación busca por Registered Model, run de origen y feature_set antes de crear
una versión. Se repitió y no generó duplicados: se mantienen doce modelos nuevos y
la versión previa de HGB. El mapa completo está en
`reports/model_registry/temporal_v2/registrations.json`, ignorado por Git.

Ejemplo de carga, sin entrenamiento:

```python
import mlflow.pyfunc

mlflow.set_tracking_uri("http://localhost:5011")
model = mlflow.pyfunc.load_model("models:/corporacion_favorita_random_forest/1")
# model.predict(features_dataframe)
```

Se verificaron las doce versiones cargándolas desde Registry mediante pyfunc: cada
una reproduce sus 12.474 predicciones guardadas, tolerancia 1e-12. Los estados de
Logged Models y versiones son READY y los MAE/WAPE coinciden con sus runs originales.
No se modificaron Airflow, DVC, originales, hiperparámetros ni pesos de modelos.
