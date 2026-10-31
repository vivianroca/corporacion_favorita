# CatBoost: candidato inicial sin optimización

`src/reposicion/catboost_candidate.py` entrena un nuevo CatBoostRegressor por cada
uno de los cuatro folds definidos en `configs/walk_forward.yaml`: 8, 15, 22 y 29 de
enero de 2017 a las 12:00 UTC, horizonte siete días. La última ventana termina el
4 de febrero. Se conservan ocho semanas móviles, las 98.010 etiquetas conocidas
por corte y los cortes de evaluación del 10, 17 y 24 de febrero y 3 de marzo.

No reentrena RF/HGB, no cambia el baseline ni modifica resultados previos. La
referencia de comparación es `reports/walk_forward/temporal_v2_january_2017`.

## Igualdad de variables y disponibilidad

Se reutilizan `TemporalFeatures` y `SeriesFamilyImputer`: feriados aplicables por
ubicación conocidos al origen, rezagos 7/14/21/28, ceros, ausencias, fechas
excepcionales, referencias semanales ordinarias y medias recientes. El calendario
se reconstruye para cada origen histórico; no se leen eventos publicados después.
La imputación se ajusta solo con entrenamiento, por serie o respaldo de la misma
familia, y conserva los ceros observados.

La primera versión utiliza **la misma codificación DictVectorizer que RF/HGB v2**,
en lugar de introducir simultáneamente categorías nativas y sus estadísticas de
objetivo. Mantiene las variables y su representación numérica comparables. Esto no
aprovecha aún todas las alternativas de tratamiento categórico de CatBoost.

Antes de ajustar, se comprueba la igualdad de cortes, contratos, catálogo, código
de variables, trazabilidad, hash de las filas/etiquetas y calendario respecto de RF
v2. Los reales se cargan después de predecir y sus claves/valores deben coincidir
con RF e HistGradientBoosting v2. No hay filtrado de casos para favorecer al modelo.

## Parámetros iniciales

`configs/catboost.yaml` fija 300 iteraciones, profundidad 6, learning_rate=0.05,
loss_function=RMSE, eval_metric=MAE, random_seed=42, thread_count=2, CPU,
boosting_type=Plain y has_time=True. `use_best_model=False` y no se entrega eval_set
ni se configura detector de sobreajuste. No hay búsqueda, selección de iteración,
optimización ni reajuste tras observar los folds. Se conserva el orden cronológico
de las filas de entrenamiento. Los defaults efectivos también se guardan mediante
`get_all_params()`, además de los parámetros explícitos del archivo YAML.
[Referencia oficial](https://catboost.ai/docs/en/concepts/python-reference_catboostregressor).

Para respetar el dominio de ventas no negativas, la salida aplica un piso fijo de
cero, independiente de la validación. No se redondean etiquetas ni predicciones.
El piso forma parte del pipeline persistido; se registra la cantidad de predicciones
crudas negativas por fold. El CBM nativo conserva el estimador crudo: para reproducir
los pronósticos requiere la transformación guardada y el piso de cero. El joblib
incluye todo el pipeline y devuelve directamente las predicciones evaluadas.

## Ejecución y tracking

CatBoost 1.2.10 se añade como dependencia fijada, con wheel Python 3.12 macOS
universal2. El lock se genera con el Python 3.12 del proyecto y conserva hashes.

```bash
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m reposicion.catboost_candidate \
  --previous reports/walk_forward/temporal_v2_january_2017 \
  --output reports/walk_forward/catboost_january_2017 \
  --tracking-uri http://localhost:5011
```

Cada repetición requiere una carpeta nueva. Se crean cinco runs en el experimento
independiente `corporacion_favorita-catboost-temporal-v2`: cuatro folds y un agregado.
No se crean versiones de Registry ni se asigna Champion o cualquier alias.

Cada fold incluye parámetros, configuración resuelta, MAE, WAPE como fracción,
CPU/RAM mediante System Metrics, duración, pipeline joblib, CatBoost nativo CBM,
predicciones, evaluación por clave, importancias con nombres de columnas,
trazabilidad, lock, YAML de parámetros y gráficas. El agregado guarda métricas
micro, medias/desvíos de folds y comparación con los tres modelos previos. MAE y
WAPE globales se calculan con errores y ventas agrupados, sin promediar porcentajes.

Los artefactos quedan en reports/ ignorado por Git. `allow_writing_files=False`
evita la carpeta implícita catboost_info. No se modifican datos originales,
simulación, Airflow ni DVC. Los resultados de enero siguen siendo una comparación
de desarrollo sobre ventanas ya inspeccionadas, sin evaluación final independiente.

## Pruebas y verificación

La transformación se compara numéricamente con la temporal v2 de RF. Se prueba
persistencia del pipeline, recuperación de CBM con su transformación, número fijo
de árboles y predicciones no negativas. Una prueba espía exige que fit reciba
únicamente entrenamiento, sin eval_set; otra rechaza early stopping en el YAML.
Se mantiene la suite existente de disponibilidad, geografía y separación de familias.

La clase del estimador vive en `src/reposicion/catboost_model.py`, para que el pipeline
sea recuperable también cuando el entrenamiento se ejecuta con `python -m`.
La verificación inicial detectó una referencia a `__main__`; se corrigió y se
volvieron a serializar los cuatro estados ya entrenados, sin repetir fit ni alterar
sus CBM originales, predicciones o métricas. El ajuste de persistencia se registra
en lineage.json y en el tag pipeline_persistence. Se añadió una prueba de regresión
que ejecuta la entrada bajo otro nombre de módulo y recupera su pipeline.

## Resultados reales

Grupo `f34f181e5d82463db7c2aba64ce572d9` en el [experimento MLflow 5](http://localhost:5011/#/experiments/5).

| Horizonte | MAE | WAPE | Predicciones crudas negativas | Run |
|---|---:|---:|---:|---|
| 2017-01-08–2017-01-14 | 130,750 | 27,554 % | 2416 | [Ver](http://localhost:5011/#/experiments/5/runs/b6776962cac647739871626354ba600f) |
| 2017-01-15–2017-01-21 | 93,462 | 19,630 % | 2029 | [Ver](http://localhost:5011/#/experiments/5/runs/0a48d14703934941ad4bbbba9cc8b5df) |
| 2017-01-22–2017-01-28 | 63,840 | 13,999 % | 3037 | [Ver](http://localhost:5011/#/experiments/5/runs/a77a689bce76475a9b4e124722da22c1) |
| 2017-01-29–2017-02-04 | 80,480 | 16,115 % | 1991 | [Ver](http://localhost:5011/#/experiments/5/runs/a71fb9fef6e84187866bb4dfb309ac12) |
| **Global: 49.896 observaciones** | **92,133** | **19,335 %** | 9473 | [Ver](http://localhost:5011/#/experiments/5/runs/066429cd32674702ae53ef134f8709fc) |

Las métricas usan las predicciones finales con piso cero. Hay 12.474 registros por fold.

| Modelo | MAE global | WAPE global |
|---|---:|---:|
| Baseline semanal | 107,077 | 22,471 % |
| Random Forest temporal v2 | 90,563 | 19,005 % |
| HistGradientBoosting temporal v2 | 102,022 | 21,410 % |
| CatBoost temporal v2 | 92,133 | 19,335 % |

Se verificaron cinco runs FINISHED, CPU/RAM y duración en los cuatro ajustes,
300 árboles por fold, ninguna selección de mejor iteración y ausencia de eval_set.
Los cuatro modelos tienen hashes CBM distintos. Tanto pipeline recuperado como CBM
con su preprocesamiento y piso reproducen las 49.896 predicciones, tolerancia 1e-12.
Las medianas por serie/familia y las columnas codificadas coinciden con RF v2.
Los 59 artefactos se descargaron y verificaron por SHA-256. Los 33 runs previos,
Registry y código baseline conservan su estado. La suite aprueba 154 pruebas;
Ruff, formato y pip check pasan. No se selecciona Champion.
