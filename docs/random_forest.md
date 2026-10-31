# Primer candidato: Random Forest

El módulo `src/reposicion/random_forest.py` implementa un modelo global para todas
las tiendas y familias. El horizonte es de siete días y los cortes y claves se
obtienen de los artefactos del baseline, sin seleccionar otra semana de evaluación.
Se verifica el SHA-256 del catálogo y los contratos, se reproduce el baseline al
corte original y se exige coincidencia exacta de los registros de evaluación.

## Variables y disponibilidad temporal

Cada fila incluye tienda y familia como categorías, día de semana y mes conocidos,
horizonte 1–7, ventas del día objetivo menos 7, 14, 21 y 28 días, promedio y cantidad
de observaciones disponibles de los siete días previos al origen. Ninguna venta
del horizonte entra como variable y no se sustituyen rezagos con valores reales
observados después de emitir. No hay actualización recursiva con ventas futuras.

Hay ocho orígenes semanales anteriores al 8 de enero de 2017. Para cada uno se
reconstruyen sus variables con la última revisión disponible a las 12:00 UTC de
ese origen, equivalentes a las 07:00 de Ecuador. Las etiquetas de entrenamiento
solo pueden tener fecha anterior al primer objetivo y estar disponibles al corte
de entrenamiento, 2017-01-08T12:00:00Z. Es válido aprender con etiquetas conocidas
posteriormente al origen de cada ejemplo histórico: nunca se usan como variables.
Las revisiones posteriores al corte de entrenamiento permanecen excluidas.

Los rezagos ausentes se conservan como NaN con indicadores explícitos. Las medianas
se aprenden solo con las filas de entrenamiento dentro del pipeline; los ceros
observados siguen siendo ceros. Para columnas totalmente ausentes, SimpleImputer
con `keep_empty_features=True` conserva una constante y el indicador de ausencia.
Un promedio sobre observaciones disponibles lleva su conteo, sin asumir que los
días ausentes vendieron cero. Las etiquetas ausentes se excluyen y se contabilizan;
los reales de evaluación deben cubrir exactamente todas las claves del baseline.
Esto permite manejar, entre otros, el 25 de diciembre ausente en el origen.

## Entrenamiento y reproducibilidad

Se usa DictVectorizer para codificar categorías, SimpleImputer para los valores
ausentes y RandomForestRegressor con 64 árboles, profundidad máxima 16, mínimo
5 muestras por hoja, `max_features=0.7`, `random_state=42` y dos workers.
Los parámetros se fijaron antes de observar los resultados de evaluación. No se
realizó búsqueda de hiperparámetros, partición aleatoria ni selección por esta semana.
La documentación de los componentes está en
[RandomForestRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html)
y [DictVectorizer](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.DictVectorizer.html).

Las dependencias se fijan en `pyproject.toml` y se bloquean con hashes en
`requirements.lock`, generado con Python 3.12 del proyecto. Para ejecutar:

```bash
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m reposicion.random_forest \
  --baseline reports/baseline/2017-01-08 \
  --output reports/random_forest/2017-01-08 \
  --tracking-uri http://localhost:5011
```

Si se repite, usar una nueva carpeta de salida. Los artefactos quedan fuera de Git.
MLflow registra parámetros y versiones, MAE, WAPE como fracción, número de
observaciones y suma de ventas reales. El experimento del candidato está separado
del experimento del baseline; se incluye el ID del run de referencia.

Se guardan el pipeline entrenado `model.joblib`, lock de dependencias, pronósticos,
evaluación por clave, importancia de variables, trazabilidad de entregas y revisiones,
comparación CSV/JSON, y gráficas PNG de reales frente a pronósticos y errores con
signo y absolutos. La curva agregada muestra las ventas totales por día; otra curva
muestra la primera serie por orden tienda/familia, elegida sin consultar sus errores.
El modelo se guarda como artefacto del run, sin asignar alias ni promover versiones.
El archivo `run.json` local contiene el ID de la ejecución.

Una sola semana es una comparación inicial: los resultados no justifican todavía
promoción, generalización a otros períodos ni decisiones de inventario. Airflow,
DVC, las entregas simuladas y los CSV originales permanecen sin cambios.

## Resultado comprobado

Entrenamiento: 98.010 filas de ocho orígenes entre 2016-11-13 y 2017-01-01.
Se excluyeron las 1.782 etiquetas ausentes del 2016-12-25. Los reales de evaluación
se consultaron al 2017-02-10T12:00Z; la emisión fue 2017-01-08T12:00Z.

| Modelo | MAE | WAPE | Observaciones |
|---|---:|---:|---:|
| Baseline semanal | 230,355045 | 48,544283 % | 12.474 |
| Random Forest | 191,136342 | 40,279459 % | 12.474 |

La reducción relativa es 17,025328 % para ambas métricas, que comparten numerador
y universo de evaluación. La gráfica agregada aún muestra sobrepronóstico varios
días; la mejora frente al baseline no elimina ese sesgo.

Run del candidato: `b9628a0e6bf94d2a878ffa2c82ed0fdd`, experimento
`corporacion_favorita-candidatos`, ID 2, estado `FINISHED`.
Se verificaron métricas por API y SHA-256 de los doce artefactos descargados.
El baseline original, run `b9e248ac36984fa893ada7b81b375892`, se conserva intacto.

Verificación: 129 pruebas aprobadas, Ruff y formato correctos, `pip check` sin
incompatibilidades. Las pruebas cubren exclusión de ventas dentro del horizonte,
ceros frente a ausencias, etiquetas posteriores al corte, revisiones, reproducibilidad
y serialización del pipeline, además de las pruebas existentes de disponibilidad.

## Instrumentación de los próximos entrenamientos

El código ahora abre el run antes de preparar las filas, mediante el contexto
`training_run` de `src/reposicion/system_metrics.py`, y activa el monitor oficial
con `log_system_metrics=True`. El muestreo es de un segundo y una muestra por registro.
CPU y memoria describen el host de entrenamiento; no son métricas de uso exclusivo
del proceso ni del servidor de MLflow. Las métricas llevan el prefijo `system/`.
El SDK también recoge disco/red cuando están disponibles; no se configura GPU.

Se agregan `training_duration_seconds` y `execution_duration_seconds`, manteniendo
MAE, WAPE y todos los artefactos anteriores. El tiempo de entrenamiento incluye todo
`model.fit`; el total abarca preparación, ajuste, evaluación, gráficas y subida de
artefactos. La validación previa del baseline y la detención del monitor quedan
fuera de ese intervalo. No se alteran los cortes ni la matriz de variables.

`psutil` 7.2.2 ya estaba instalado; ahora es una dependencia explícita fijada.
Se agregó `mlflow-skinny` 3.17.2, compatible con la versión del servidor existente.
El lock se regeneró con Python 3.12, conservando hashes. No es suficiente establecer
una variable de entorno para el cliente REST anterior: el run debe existir mientras
se ejecuta el entrenamiento para recoger sus recursos.

La verificación utilizó el colector nativo de CPU/RAM y pruebas de ciclo de vida
con el SDK simulado, sin escribir runs de prueba en el servidor. No se reentrenaron
los modelos existentes. La comprobación de nuevas métricas publicadas en MLflow
queda para la próxima ejecución autorizada, no se presenta como realizada ahora.

La suite actual aprueba 134 pruebas. También se verificó por API que los dos runs
existentes conservaron íntegramente su estado anterior a esta preparación.
