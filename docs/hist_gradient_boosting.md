# HistGradientBoosting: segundo candidato

El módulo `src/reposicion/hist_gradient_boosting.py` reutiliza `SalesHistory`,
`features`, `training_data`, la evaluación MAE/WAPE y las gráficas existentes.
No reentrena el baseline ni Random Forest. La preparación numérica coincide
exactamente con Random Forest: categorías codificadas, indicadores de ausencia y
medianas aprendidas exclusivamente con entrenamiento.

Se conservan las ventas fraccionarias y los ceros. Las variables son tienda,
familia, día de semana, mes, horizonte 1–7, rezagos de ventas 7/14/21/28 días y
promedio/conteo de los siete días anteriores al origen. Cada ejemplo histórico
reconstruye sus variables con las revisiones disponibles en su propio origen.
Las etiquetas se conocen al corte final de entrenamiento y preceden al horizonte.

El código exige igualdad de los cortes y la trazabilidad de entrenamiento con
Random Forest, y de las claves y reales evaluados con ambos modelos anteriores.
Los reales del horizonte se leen después de ajustar y predecir. No hay partición
aleatoria ni ajuste de hiperparámetros contra la semana evaluada.

## Parámetros fijados antes de la evaluación

Se utiliza `HistGradientBoostingRegressor` con pérdida Poisson, tasa de aprendizaje
0,08, 150 iteraciones, máximo 31 hojas, mínimo 20 muestras por hoja, regularización
L2 de 1,0, 255 bins y semilla 42. La pérdida elegida permite predicciones no negativas;
no se redondean las etiquetas a enteros ni se aplica recorte posterior. La prueba
sintética incluye ceros y ventas fraccionarias.

`early_stopping=False` evita una selección aleatoria interna de validación.
Las categorías ya están codificadas mediante DictVectorizer, de modo que
`categorical_features=None`. Se limita el paralelismo numérico a dos hilos durante
fit/predict. [Referencia del estimador](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html).

## Ejecución

```bash
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m reposicion.hist_gradient_boosting \
  --baseline reports/baseline/2017-01-08 \
  --forest reports/random_forest/2017-01-08 \
  --output reports/hist_gradient_boosting/2017-01-08 \
  --tracking-uri http://localhost:5011
```

Cada repetición requiere otra carpeta para conservar los artefactos previos.
`pandas==3.1.0` se agrega y bloquea con hashes bajo Python 3.12 para utilizar el
formato sklearn de MLflow. No se modifica Airflow ni DVC.

## Comparación real

Entrenamiento: 98.010 filas, ocho orígenes semanales anteriores, del 13 de noviembre
de 2016 al 1 de enero de 2017. Se mantienen las 1.782 etiquetas excluidas del 25 de
diciembre, ausentes en el origen. Emisión: 2017-01-08T12:00:00Z. Reales disponibles
al corte de evaluación: 2017-02-10T12:00:00Z. Horizonte: 8–14 de enero de 2017.

| Modelo | MAE | WAPE | Observaciones |
|---|---:|---:|---:|
| Baseline semanal | 230,355045 | 48,544283 % | 12.474 |
| Random Forest | 191,136342 | 40,279459 % | 12.474 |
| HistGradientBoosting | 207,908913 | 43,814057 % | 12.474 |

El nuevo candidato mejora al baseline, pero Random Forest conserva el menor error
en esta semana. No se reajustan parámetros al observar este resultado ni se promueve
un modelo con esta comparación de un solo período.

## MLflow y Registry

Run `39562417052c45bb8dece31675763d19`, experimento
`corporacion_favorita-candidatos`, ID 2, estado `FINISHED`.

Se verificaron 16 muestras por métrica de CPU/RAM del host bajo `system/`,
`training_duration_seconds=5.730457833000401` y
`execution_duration_seconds=17.364074500001152`. La ejecución utiliza el contexto
oficial implementado antes del entrenamiento y no inventa métricas retrospectivas.

Artefactos del run: parámetros, MAE/WAPE, pronósticos, evaluación por clave,
comparación CSV/JSON, trazabilidad, modelo joblib, lock, dos PNG y `registry.json`.
Además se registra un MLflow Model con pipeline completo, firma e input example,
serializado explícitamente con cloudpickle y dependencias fijadas. Una adaptación
DataFrame → registros permite consumir las mismas variables con sklearn y pyfunc.
[Referencia de MLflow sklearn](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.sklearn.html).

Model Registry: `corporacion_favorita_hist_gradient_boosting`, versión **1**,
URI `models:/corporacion_favorita_hist_gradient_boosting/1`, estado **READY**.
Modelo interno: `models:/m-14657698bf6c457f8dfe206376ffea38`.
No se asigna ningún alias, incluido `champion`.

La suite completa aprueba 137 pruebas. Se comprueba igualdad de la transformación
con Random Forest, persistencia del pipeline y rechazo de comparaciones con reales
o claves distintas. Las advertencias de dependencias sobre inferencia de columnas
enteras, una futura operación de pandas y detección de núcleos en el sandbox no
impidieron las pruebas; los rezagos permiten ausencia y horizonte/indicadores son
enteros obligatorios en la firma.

Verificación posterior al registro: se descargó la versión 1 y se compararon sus
12.474 predicciones con las guardadas, tanto con `mlflow.sklearn.load_model` como
con `mlflow.pyfunc.load_model`; ambas coinciden con tolerancia 1e-12. Los doce
artefactos del run se descargaron y sus SHA-256 coinciden con los locales. Las
consultas completas de los runs anteriores conservan el mismo contenido previo.
