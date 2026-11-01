# Pronóstico semanal del Champion

> Actualización: la orquestación actual usa Assets y el catálogo de publicaciones confirmadas. Ver [dependencias y migración](dependencias_assets.md); las pruebas de las etapas previas se conservan como historial.

`lab1_pronostico_reposicion` usa Airflow 3.3.2 y no entrena modelos. Su tarea
`generar_publicacion` llama a lógica independiente de Airflow mediante un Python
3.12 aislado, reutilizando `uncertainty`, `SalesHistory`, `TemporalFeatures` y los
contratos existentes. El DAG de ingesta permanece intacto.

## Programación y corte

`configs/pronostico.yaml`: domingos 06:00, `America/Guatemala`, cron `0 6 * * 0`,
`catchup: false`. Editar esa configuración y reconstruir la imagen de pronóstico
permite cambiar la frecuencia. `LAB1_FORECAST_SCHEDULE` también admite un cron si
se define en el entorno de los procesos Airflow. No se consulta MLflow al parsear
el DAG. Las ejecuciones programadas usan el corte histórico fijo declarado en
`simulation_calendar`, separado del intervalo físico del scheduler.
[Política y prueba real del reloj simulado](reloj_simulado.md).

Para un backfill manual usar `origin`, `issued_at`, `snapshot_id` y, opcionalmente,
`model_version` para fijar una versión registrada. Sin esta última, se resuelve
`champion` al ejecutar y se fija su versión antes de inferir. Esto permite repetir
una versión anterior sin depender de cambios posteriores del alias. No reconstruye
la historia del alias: la disponibilidad se interpreta según el calendario
histórico simulado de entrenamiento y evaluación, no la creación física en 2026.
No se admiten versiones entrenadas/evaluadas después del corte ni residuos futuros.
Los cortes anteriores a la disponibilidad del Champion actual se rechazan.

Ejemplo ya probado:

```bash
docker exec lab1-airflow-scheduler-1 airflow dags trigger lab1_pronostico_reposicion \
  --run-id MI_BACKFILL_UNICO \
  --conf '{"origin":"2017-03-05","issued_at":"2017-03-05T12:00:00Z","snapshot_id":"645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0","model_version":"4"}'
```

## Entradas y publicación

Se consumen exclusivamente bundles publicados por la ingesta:
`operational/snapshots/<id>` y `operational/automatic/*/publications/<id>`.
Se verifican todos los checksums, contrato, recibos disponibles y el vínculo con
la validación histórica cuando existe. El snapshot debe tener `as_of <= issued_at`;
un snapshot posterior jamás se convierte en histórico filtrando sus filas.
Se exigen recibos de los 28 días previos y la cobertura de series del Champion.
Con empates de fecha se exige `snapshot_id` explícito. La ausencia individual se
conserva como ausencia; los ceros permanecen ceros en las variables existentes.
La bandeja, CSV originales y snapshots se leen sin modificarlos.

Los residuos se descargan de los runs walk-forward RF temporal v2, del grupo del
Champion, únicamente si `evaluated_at <= issued_at` y el período terminó antes del
origen. La calibración agrupa por familia y horizonte, sin mezclar familias.
P10/P50/P90 son cuantiles empíricos ordenados y no negativos, no una garantía de
cobertura. P50 incluye corrección mediana del error.

Destino persistente en el volumen `lab1_operational`:
`/opt/lab1/operational/forecasts/<publication_id>/` con `forecast_quantiles.csv`,
`lineage.json` y `manifest.json`. El linaje incluye snapshot/corte, recibos, versión
MLflow/run/model source, tags DVC/Git originales, calibración y hashes del código.
No se crean modelos, runs de entrenamiento ni cambios de alias.

La identidad incluye origen, corte, snapshot/hash, contrato, versión del modelo,
calibración/hashes y código. Lock de archivo y rename atómico evitan publicaciones
parciales o concurrentes. Un reintento verifica y reutiliza el bundle; una nueva
revisión/modelo/código crea otra identidad. Nunca se sobrescriben resultados.
Se detecta corrupción de un bundle ya publicado y se falla explícitamente.

## Despliegue sin reemplazar el DAG de ingesta

La imagen `lab1-airflow-pronostico:3.3.2` extiende la imagen **local desplegada**
`lab1-airflow:3.3.2`; solo agrega el nuevo DAG y el proyecto de inferencia bajo
`/opt/lab1/forecast_project`. No reconstruir la imagen base en esta etapa: se
conserva su DAG de ingesta actual, incluyendo programación y zona horaria.
El Python de Airflow no se cambia: `/opt/lab1/inference` contiene las dependencias
bloqueadas con hashes en `docker/requirements.forecast.lock`, extraídas del lock
existente de Python 3.12 para el cierre Linux sin extras. `pip check` pasó.

```bash
docker build --pull=false -f docker/Dockerfile.forecast -t lab1-airflow-pronostico:3.3.2 .
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.forecast.yaml \
  up -d --no-build --pull never --no-deps airflow-api airflow-scheduler airflow-dag-processor
```

Usar ambos archivos Compose en futuros comandos de infraestructura para conservar
esta imagen. PostgreSQL/MLflow y sus volúmenes no se recrean ni se eliminan.
Los servicios Airflow se recrearon para aplicar la imagen, conservando sus datos.

## Verificación real

La ingesta existente, sin cambios, creó el snapshot requerido con el DAG Run
`pronostico_snapshot_20170305` (success), corte 2017-03-05T12:00:00Z y referencias
2017-02-05 a 2017-03-11. Esto incorpora historia y feriados conocidos al corte.
El DAG nuevo ejecutó `prueba_pronostico_20170305` con éxito: 12.474 filas únicas,
1.782 series y siete días (5–11 marzo), con `0 <= P10 <= P50 <= P90`.

Publicación: `9d1027c938284a2604b84a0ff2b2ae17e9ec3035d4c5fb793b46cc6d93873594`.
El run `prueba_pronostico_20170305_reintento` también terminó en success y devolvió
`reused=True`; existe una única publicación y sus checksums permanecen iguales.

El scheduler creó automáticamente `scheduled__2026-10-25T12:00:00+00:00`, que falló
sin publicar: los datos simulados no contienen los 28 días previos de octubre de
2026. Es una restricción real de disponibilidad, no un entrenamiento pendiente.
Ese fallo pertenece a la versión previa al reloj simulado. El DAG actual usa
replay histórico explícito y conserva el backfill, sin exigir datos de 2026.

Sin errores de importación en Airflow; cron/zona/catchup comprobados en el runtime.
Seis pruebas específicas pasan sin fit: cuantiles, exclusión de residuos futuros,
idempotencia/revisiones, integridad, recuperación de un fallo, selección temporal
y lectura de snapshots conservando ceros/rechazando historia incompleta.

## Corrección de fechas de emisión y runs manuales

El día de `origin` se compara con `issued_at` convertido a **America/Guatemala**,
tanto en publicación como en incertidumbre. Por ejemplo, `2017-03-06T00:30:00Z`
corresponde todavía al 5 de marzo en Guatemala: `origin=2017-03-05` es válido.
Se rechazan fechas realmente distintas y timestamps sin zona horaria.

Un run manual sin `origin` ni `issued_at` selecciona el último snapshot validado
con 28 días de historia en su propio corte. Usa su `as_of` como emisión y deriva
el origen local de esa misma fecha. Un `snapshot_id` explícito fija la selección.
Los snapshots incompletos no se usan; los corruptos fallan explícitamente.
La resolución actual usa el calendario histórico configurado, sin fallback a
logical_date ni a la hora actual como corte. El replay manual de snapshot explícito
limita la búsqueda al calendario histórico, y vuelve a validar su fecha resuelta.

Con solo `origin`, el corte es 06:00 Guatemala de ese día. Con `issued_at`
explícito, se respeta ese corte y se deriva el origen local si falta. La ejecución
programada conserva su fecha lógica física como auditoría y utiliza el replay
histórico explícito para los datos. Para replay estable fijar corte, snapshot y versión.

La historia 2013–2017 no significa que todo origen sea válido para el Champion
actual: su última evaluación simulada es 2017-03-03. No se puede retroceder el
modelo a 2013 sin fuga temporal. Tampoco puede utilizarse un snapshot de marzo
para reconstruir un conocimiento de enero. Estas validaciones siguen activas.


Pruebas de la corrección en Airflow:

| DAG Run | Resultado | Corte efectivo | Filas |
|---|---|---|---:|
| correccion_historica_20170305_utc | success | 2017-03-06T00:30:00Z (5 marzo Guatemala) | 12.474 |
| correccion_manual_sin_conf | success | 2017-03-05T12:00:00Z (del snapshot) | 12.474 |

Ambos usan el snapshot 645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0,
Champion v4, horizonte 5–11 marzo. Publicaciones nuevas:
55cd6e960a20f1c29f1de57c2380fdfc12b1dccb4bc055305a554cc7b362028c y
de2ddbae6c7f48e932d7b2260f1eb2e1491ba46529da7ed4f45898d4ccf1f77e.
Se verificaron checksums y orden/no negatividad de los cuantiles en todas las filas.
Diez pruebas específicas pasan sin entrenamiento. El run fallido anterior se
conserva como historial; la corrección se validó con runs nuevos.


La confirmación actual exige también pedidos completos y costos/inventario
versionados: [integración y prueba de extremo a extremo](pedidos_en_airflow.md).
