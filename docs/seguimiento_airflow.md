# Seguimiento diario de pronósticos publicados

> Actualización: la orquestación actual usa Assets y el catálogo de publicaciones confirmadas. Ver [dependencias y migración](dependencias_assets.md); las pruebas de las etapas previas se conservan como historial.

DAG `lab1_seguimiento`, Airflow 3.3.2: **08:00 America/Guatemala**, cron
`0 8 * * *`, `catchup=False`, una ejecución activa y un reintento. Configuración
en `configs/seguimiento.yaml`; reconstruir la imagen para aplicar cambios.
`LAB1_MONITORING_SCHEDULE` permite un cron alternativo en el entorno de Airflow.
No se modifica ninguno de los otros DAGs ni se cargan/entrenan modelos.

## Métricas y disponibilidad

`reposicion.monitoring` lee publicaciones de `operational/forecasts` y snapshots
validados de la ingesta (`snapshots` y `automatic/*/publications`). Comprueba
checksums, contratos, validación histórica, claves, cuantiles y recibos disponibles.
No lee la bandeja ni los CSV originales. Nunca altera predicciones/publicaciones.

Evalúa por clave `(date, store_nbr, family)` sobre **P50**:

- MAE = suma de errores absolutos / pares observados.
- WAPE = suma de errores absolutos / suma de ventas reales, en escala fracción.
- `coverage_p10_p90` = proporción de pares con `P10 <= real <= P90`.
- `data_completion_fraction` = pares observados / filas pronosticadas.

Los días todavía abiertos al corte local no se evalúan. Se distinguen
`future_date`, `not_delivered`, `absent_record` y `evaluated`. Una venta cero es
una observación válida; una ausencia no se imputa con cero. WAPE es indefinido
si las ventas suman cero, y no se registra esa métrica. Si no existen pares,
no se crean métricas ficticias ni un run MLflow; el estado pendiente queda local.

Sin snapshot explícito se combinan snapshots disponibles al corte, eligiendo
**la mayor revisión por fecha** de ventas, con recibos conocidos. Una partición
corregida reemplaza la anterior completa: una fila eliminada no reaparece desde
una revisión vieja. Se conservan las demás fechas de snapshots anteriores.
Se rechaza la misma revisión con checksums contradictorios. Un snapshot posterior
al corte nunca se filtra para simular conocimiento pasado. `snapshot_id` permite
fijar un único snapshot para replay.

## Resultados, versiones e idempotencia

Se publican bundles en el volumen `lab1_operational`, bajo
`/opt/lab1/operational/monitoring/<evaluation_id>/`:
`evaluation.csv`, `metrics.json`, `lineage.json` y `manifest.json`.
La identidad incluye publicación/hash de predicciones, verdad efectiva y recibos
con revisión/checksums, contrato y código evaluador. El paso del tiempo sin cambios
no crea otro run; nuevas ventas, correcciones o cambios de elegibilidad producen
una evaluación nueva. Las evaluaciones anteriores permanecen intactas.

La publicación reutiliza lock y rename atómico existentes. Un lock adicional
abarca el registro remoto. MLflow busca por `tags.evaluation_id`: recupera el mismo
run tras un fallo, completa solo parámetros/métricas/artefactos faltantes y
comprueba igualdad si ya existen. Nunca duplica eventos métricos en un retry.
La fecha almacenada en el linaje es la primera evaluación de esa verdad; los
DAG Runs posteriores documentan los cortes solicitados aunque reutilicen el run.

Experimento: `corporacion_favorita-seguimiento`. Cada run tiene métricas reales,
los cuatro artefactos, publicación fuente, modelo/versión/run, referencias DVC del
modelo y snapshots/recibos reales. No se cambia el Champion ni se registran modelos.
La cobertura observada no implica garantía de cobertura futura.

## Ejecución histórica

Para un trigger manual usar `as_of` con zona horaria, y opcionalmente
`forecast_id` y `snapshot_id`. Sin `forecast_id` se revisan todas las publicaciones
anteriores al corte. Las ejecuciones programadas usan `data_interval_end`.

```bash
docker exec lab1-airflow-scheduler-1 airflow dags trigger lab1_seguimiento \
  --run-id MI_SEGUIMIENTO_HISTORICO_UNICO \
  --conf '{"as_of":"2017-04-02T12:00:00Z","forecast_id":"de2ddbae6c7f48e932d7b2260f1eb2e1491ba46529da7ed4f45898d4ccf1f77e"}'
```

Para preparar la prueba se ejecutó el DAG de ingesta existente, sin modificarlo,
con corte 2017-04-02T12:00Z y referencias 2017-03-05 a 2017-03-11. Creó el snapshot
`1a87a6e7b4ec739577325d6a0b7eb2cf6b58ce23f47e8d5b5daec4636856257e`.
No se regeneraron entregas. Las pruebas evalúan los pronósticos 5–11 marzo,
Champion v4, originalmente publicados antes de conocer esas ventas finales.

## Despliegue y pruebas

Se amplía `docker/Dockerfile.forecast` con el nuevo DAG, usando el venv de
inferencia existente y sin agregar dependencias. Se conservan bytes de los otros
DAGs, PostgreSQL/MLflow y volúmenes; se recrean solo los tres procesos Airflow.

```bash
docker build --pull=false -f docker/Dockerfile.forecast -t lab1-airflow-pronostico:3.3.2 .
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.forecast.yaml \
  up -d --no-build --pull never --no-deps airflow-api airflow-scheduler airflow-dag-processor
.venv/bin/pytest -q tests/test_monitoring.py tests/test_forecast_publication.py
```

Nueve pruebas específicas sin entrenamiento: ceros/ausencias, WAPE indefinido,
cobertura, retrasos/correcciones, días futuros, unicidad, combinación de snapshots,
reemplazo de particiones e idempotencia/integridad/publicación recuperable.


## Resultados comprobados

- DAG Run `seguimiento_historico_final_20170402`: success, primer intento.
- DAG Run `seguimiento_historico_final_reintento`: success, `reused=True`.
- Evaluación `d45e9e65afa0067c0f1326d7a4cdfcd6916950c50ca53150f41dd832f6d700a6`.
- [Run MLflow](http://localhost:5011/#/experiments/8/runs/683aca87742145d48322ad3f04b353c6), FINISHED.
- 12.474 pares observados, 100 % de datos evaluables, cero pendientes.
- MAE P50 **77.2637968451**, WAPE **0.1617374141** (16.17374141 %).
- Cobertura P10–P90 **0.8002244669** (80.02244669 %).

Los cuatro artefactos remotos se comprobaron contra el manifiesto; la evaluación
mantiene un solo run por evaluation_id. Predicciones y publicaciones originales
conservan todos sus hashes. Ambos DAGs anteriores conservan sus bytes, sin errores
de importación; servicios saludables. Las pruebas incluyen además la separación
de mensajes del SDK MLflow y la salida JSON del subprocess: un fallo inicial en
esa frontera se corrigió antes de las dos ejecuciones finales. Se conservan los
runs de evaluación de las versiones intermedias como historial, sin sobrescribir.
Informe local ignorado por Git: `reports/seguimiento/verificacion.json`.
