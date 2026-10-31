# Evidencia de la etapa 3

Esta es la evidencia de la primera implementación por corte. El automatismo posterior
se documenta en [ingesta_automatica_resultados.md](ingesta_automatica_resultados.md).

## Infraestructura levantada

| Contenedor | Estado comprobado | Puerto de host |
|---|---|---|
| `lab1-postgres-1` | healthy | ninguno |
| `lab1-mlflow-1` | healthy | 127.0.0.1:5011 |
| `lab1-airflow-api-1` | healthy | 127.0.0.1:8082 |
| `lab1-airflow-scheduler-1` | healthy | ninguno |
| `lab1-airflow-dag-processor-1` | healthy | ninguno |

`lab1-airflow-init-1` terminó correctamente. Airflow 3.3.2 usa PostgreSQL 16 y
LocalExecutor. MLflow 3.17.2 usa SQLite y un volumen separado para artefactos.
Las tres bases se encontraron localmente y no se descargaron otra vez. La imagen
derivada `lab1-airflow:3.3.2` contiene el código del laboratorio sin instalar paquetes.

Se verificaron login de Airflow y lectura autenticada de DAG runs mediante API,
healthchecks de los cinco contenedores y HTTP 200 de MLflow desde Airflow.
La importación del DAG devolvió `[]` en `list-import-errors`.
El montaje `/opt/lab1/source` se verificó como filesystem de solo lectura.

MLflow: **0 runs**. Solo existe el experimento `Default` inicializado por el servidor;
no se registraron experimentos, métricas ni modelos de prueba.

## Pruebas automatizadas

`.venv/bin/python -m pytest -q`: **72 passed in 1.43s**.

Se incluyen las 52 pruebas de contratos/simulación y 20 casos nuevos del pipeline:
filtrado temporal, revisiones, backfill, ceros/nulos/ausencias, claves globales,
cuarentena, integridad de landing y snapshots, ventanas, cortes inválidos y CLI.
Los escenarios modifican exclusivamente sus fixtures temporales, nunca los datos reales.

Ruff y formato: sin errores. `pip check`: sin incompatibilidades.

## Ejecuciones reales en Airflow

Las ejecuciones fueron manuales a través del scheduler y su Execution API, con
fecha de referencia limitada a **2017-01-18**. Las fechas de conocimiento de abajo
son cortes históricos, no fechas de ejecución real ni timestamps fabricados.

| Run ID | Corte de conocimiento UTC | Estado |
|---|---|---|
| `lab1_etapa3_inicial` | 2017-01-20T12:00:00Z | success |
| `lab1_etapa3_corregido` | 2017-01-27T12:00:00Z | success |
| `lab1_etapa3_repetido` | 2017-01-20T12:00:00Z | success |

Las tareas `descubrir`, `ingestar`, `validar` y `publicar_snapshot` se completaron.
La corrección de ventas ya existía en el manifiesto, con disponibilidad
2017-01-26T11:00:00Z. No se regeneró ni agregó ninguna entrega al origen.

| Fuente | Filas al primer corte | Filas al segundo corte |
|---|---:|---:|
| Ventas | 1.782 | 1.782 |
| Tiendas | 54 | 54 |
| Petróleo | 1 | 1 |
| Transacciones | 0 | 53 |
| Feriados/eventos | 0 | 0 |

Las transacciones aún no estaban disponibles al primer corte; posteriormente
llegaron 53 registros, sin inventar uno para la tienda restante. No había eventos
en la ventana acotada. Ambas situaciones se registraron sin provocar un fallo.

## Identidades y trazabilidad

- Snapshot inicial: `c763e13c52f540dffe2b7fa4afe718852eec798dccb5fa338ae94a9965aca196`.
- Snapshot corregido: `388d763ded09b9fbb72003bfb054b1020b12b1222bef43b99275509d401a2dfe`.
- Hash de los módulos de procesamiento: `ed82fc2aaa7f8ff00062e8efa4cdc3af7c94b5d2799d4bc27fdb297c7ac5b72d`.

Se comprobó que el código del contenedor coincide con el del workspace. Los
manifiestos enlazan corte, ventana, generación del origen, contratos archivados,
recibos, revisiones y checksums. Los snapshots están en
`lab1_operational:/opt/lab1/operational/snapshots/<id>/`.

Ventas del primer snapshot coincide por SHA-256 con la revisión 1 seleccionada;
ventas del segundo coincide con la revisión 2. Solo cambia **una fila**, sin sumar
la revisión ni duplicar la partición. El primer snapshot se conserva.

## Idempotencia y protección de entradas

Se comparó el estado operativo antes y después de la tercera ejecución:
**31 archivos con el mismo contenido y mtime**, sin un tercer snapshot.
Los metadatos del DAG run sí se conservan en PostgreSQL, separados de estos artefactos.

Se compararon los **10.150 archivos** bajo `data/original/` y `data/simulation/`
antes y después del trabajo: mismo conjunto de rutas, SHA-256 y mtime.
Todos los datos y `.env` siguen excluidos de Git. No se hicieron commits ni publicaciones.

## Límites y pendientes

<!-- Las condiciones de esta sección describen el momento de la prueba inicial. -->
No hay problemas bloqueantes en la prueba realizada. Se ejecutó una ventana pequeña
como se solicitó; no se realizó una carga operativa completa de los tres millones
de ventas. El DAG permanece manual y habilitado para nuevos cortes explícitos.

El versionado remoto con DVC, CI en GitHub y los modelos siguen pendientes de su
alcance correspondiente. No se entrenaron modelos ni se avanzó a la siguiente etapa.
Comandos de inicio, parada, consulta y reprocesamiento: [etapa3_operacion.md](etapa3_operacion.md).
