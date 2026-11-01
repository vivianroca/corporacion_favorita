# Laboratorio 1 — Motor de Reposición de Inventario

Producto de ML para pronosticar ventas diarias P10/P50/P90 por tienda y familia,
calcular pedidos sugeridos con costos configurables y evaluar pronósticos contra
ventas disponibles. El horizonte es de siete días. Airflow orquesta ingesta,
pronóstico/pedidos y seguimiento; PostgreSQL conserva sus metadatos y MLflow los
modelos y evaluaciones. La reconstrucción reutiliza el Champion Random Forest
entrenado: **no requiere entrenar modelos**.

Esta es la guía de reconstrucción vigente. El detalle técnico está en
[bootstrap](docs/bootstrap.md) y [restauración del Champion](docs/restauracion_champion.md).

## 1. Requisitos

- Un checkout del proyecto que incluya `scripts/bootstrap.sh`, los DAGs,
  configuraciones, `requirements.lock` y los punteros DVC indicados más abajo.
- **Python 3.12**, accesible como `python3.12`. Se verificó Python 3.12.16 en
  macOS Apple Silicon. Para otro ejecutable, definir `LAB1_PYTHON` al invocar el script.
- **Docker Desktop/Engine activo y Docker Compose**. El proceso reutiliza las
  imágenes locales y descarga únicamente las que falten:
  `apache/airflow:3.3.2-python3.12`, `postgres:16` y `ghcr.io/mlflow/mlflow:v3.17.2`.
- Internet para instalar dependencias o recuperar objetos que no estén en caché.
- **Acceso de lectura al remoto DVC `google_drive` y autenticación local configurada**.
  La autorización OAuth inicial de la cuenta docente es un prerrequisito externo.
  No se distribuyen credenciales en el repositorio. `.dvc/config.local` y el almacén
  local de autenticación permanecen fuera de Git.

El script crea `.venv` dentro del repositorio si falta y comprueba su intérprete.
Instala `requirements.lock` con hashes y verifica las dependencias. No usa entornos
externos ni instala paquetes globalmente. El lock incluye DVC **3.67.1**,
`dvc-gdrive==3.0.1` y `PyDrive2==1.21.2`; no es necesario instalarlos globalmente.

En macOS Apple Silicon, si falta Python 3.12, instalarlo antes con Homebrew:

```bash
brew install python@3.12
```

Comprobaciones de prerrequisitos, sin iniciar servicios:

```bash
python3.12 --version
docker version
docker compose version
```

## 2. Colocar los cinco originales de Kaggle

El docente descarga y extrae estos archivos en la raíz del proyecto:

```text
data/original/
├── train.csv
├── stores.csv
├── holidays_events.csv
├── oil.csv
└── transactions.csv
```

`test.csv` y `sample_submission.csv` no son entradas del laboratorio.
El bootstrap recibe los originales localmente: no los descarga de Kaggle ni
necesita recuperarlos del remoto DVC. Los lee sin modificarlos; los CSV permanecen
fuera de Git. Los contratos y las políticas de disponibilidad están en
`configs/contracts.yaml` y `configs/availability.yaml`.

## 3. Reconstruir con un único comando

Desde la raíz del repositorio, ejecutar el comando probado:

```bash
sh scripts/bootstrap.sh --origin 2017-03-19 --instance repro-limpio
```

El proceso realiza automáticamente:

1. Preparación de `.venv`, instalación bloqueada y recuperación de pesos/calibración desde DVC.
2. Generación determinista del histórico y las entregas simuladas desde los cinco CSV.
   Una generación compatible existente se verifica y reutiliza.
3. Inicialización de una bandeja propia y liberación progresiva de entregas,
   conservando disponibilidad, revisiones y checksums. Solo el publicador escribe
   en ella; el pipeline la monta como solo lectura.
4. Creación de secretos locales, configuración de replay y recursos Docker propios.
   Construye la imagen de Airflow/inferencia directamente desde la imagen oficial.
5. Arranque de PostgreSQL y MLflow vacíos y restauración idempotente del Champion,
   incluyendo sus cuatro validaciones para calibrar los cuantiles.
6. Inicialización de Airflow, catálogo vacío de seguimiento y habilitación de los tres DAGs.
7. Carga histórica inicial, snapshot del corte, pronósticos/pedidos y evaluación
   posterior de ventas y correcciones. Espera publicaciones y consumidores exitosos.

No requiere imágenes personalizadas anteriores, volúmenes del laboratorio original
ni IDs de snapshots conocidos. El snapshot se descubre en la ejecución y se fija
automáticamente para los siguientes replays semanales.

La emisión predeterminada es **12:00 UTC del origen (06:00 Guatemala)** y la evaluación,
28 días después. Se pueden indicar `--issued-at` y `--evaluated-at` explícitos.
El origen debe disponer de 28 días previos, un horizonte completo dentro del
histórico y un Champion evaluado al corte; el actual estuvo disponible desde
`2017-03-03T12:00:00Z`. La ausencia de entregas no se convierte en ventas cero.
Si falta historia por una demora simulada, el proceso falla sin adelantar la emisión
ni incorporar datos futuros. El reloj físico del scheduler no se usa como fecha de ventas.

Cada instancia queda fijada a un escenario. Repetir exactamente el comando reutiliza
runs y publicaciones. Para otro corte, usar otro `--instance` y puertos disponibles
mediante `--airflow-port` y `--mlflow-port`. Los valores predeterminados son 8083/5013;
no reutilizar esos puertos si otra instancia continúa activa.

### Assets y servicios

| DAG | Activación y función |
|---|---|
| `lab1_ingesta_temporal` | Carga histórica por corte y sondeo cada tres horas; confirma snapshots y ventas evaluables. |
| `lab1_pronostico_reposicion` | Cron semanal, domingo 06:00 Guatemala, más solicitudes explícitas por Asset. Espera el snapshot confirmado y publica pronósticos y pedidos conjuntamente. |
| `lab1_seguimiento` | Pronósticos confirmados **OR** ventas evaluables; evalúa publicaciones válidas y correcciones sin cambiar las predicciones. |

El bootstrap solicita el pronóstico mediante `lab1.pronostico_solicitado`, emitido
por la ingesta exitosa. Los snapshots de cada sondeo no disparan por sí solos
pronósticos cada tres horas. Un fallo de pedidos impide confirmar la publicación.

Para la instancia del comando anterior:

- Airflow: **http://localhost:8083**, usuario `admin`; contraseña en
  `data/bootstrap/repro-limpio/.env`, con permisos 0600.
- MLflow: **http://localhost:5013**.
- Proyecto/red/volúmenes con prefijo `lab1-repro-limpio`; PostgreSQL no expone puerto al host.
- Simulación, bandeja, snapshots y publicaciones en `data/bootstrap/repro-limpio/`.
- Resultado: `result.json`; verificación: `verification.json`; logs: `logs/commands.log`.

Todo ese directorio está ignorado por Git. El MLflow original en 5011 y Airflow
original en 8082 no son dependencias de la reconstrucción.

Para consultar o detener esta instancia conservando datos:

```bash
docker compose --env-file data/bootstrap/repro-limpio/.env \
  -f data/bootstrap/repro-limpio/compose.yaml ps
docker compose --env-file data/bootstrap/repro-limpio/.env \
  -f data/bootstrap/repro-limpio/compose.yaml stop
```

Usar siempre el Compose generado de la instancia, no los antiguos `make infra-*`.
Un fallo se informa sin declarar éxito; los detalles y límites de reintento están
en [docs/bootstrap.md](docs/bootstrap.md).

## 4. Evidencia real: corte nuevo del 19 de marzo

Prueba ejecutada el **2026-11-01** con el comando anterior y una simulación,
bases y volúmenes nuevos; los cortes de datos fueron históricos:

| Verificación | Resultado registrado |
|---|---|
| Carga inicial, conocida al `2017-01-01T05:00:00Z` | 2.594.592 filas históricas de ventas validadas |
| Emisión | `2017-03-19T12:00:00Z` |
| Horizonte | 19–25 marzo 2017 |
| Evaluación | `2017-04-16T12:00:00Z` |
| Pronósticos / pedidos | 12.474 filas / 1.782 tiendas-familias |
| Seguimiento | 12.474 pares evaluados, cero pendientes |
| MAE | 61.40209713412655 |
| WAPE | 0.12776200891752645 (12.776201 %) |
| Cobertura P10–P90 | 0.820266153599487 (82.026615 %) |

Los tres runs de ingesta terminaron en `success`. El pronóstico fue
`asset_triggered__2026-11-01T23:23:27.648839+00:00_um5dMBsj`; hubo dos runs nativos
de seguimiento, también exitosos. Los nombres completos constan en
[docs/bootstrap.md](docs/bootstrap.md).

| Publicación | Identificador |
|---|---|
| Pronóstico | `97db0822ef96ef36af59071811d8d96341886c6cfbd120c5202d99f32d2afdc1` |
| Pronóstico y pedidos confirmados | `a9b399e3e7baa4d285b48d54e68e93e96e39c222b1d3a1aadde9da1b5b8c18f2` |
| Seguimiento | `351230006eed62e39c246750a595b5602605d1078d80ecfd8e59d90fcd254cb3` |

SHA-256 del CSV de pronósticos de esa ejecución:
`1408e40f440dbeca870cdfa1605ab18db292c773ca7379b9335aeaa500053a96`.

Se repitió exactamente el comando: se conservaron **3/1/2 DAG Runs** de
ingesta/pronóstico/seguimiento, **5 runs de MLflow** (cuatro restauraciones y una
evaluación), **una versión del modelo** y los hashes de **25 archivos de salida**.
No se agregaron publicaciones ni se reentrenó. Los recibos y residuos utilizados
estaban disponibles al corte. Los originales, pesos, entrega archivada y MLflow
original conservaron sus verificaciones.

Evidencia local existente: `data/bootstrap/repro-limpio/result.json` y
`data/bootstrap/repro-limpio/verification.json`. Estos informes se generan al
reconstruir y están ignorados; no se presupone que existan en un clon nuevo.

## 5. Pronóstico pasado con DVC: recuperar y recalcular son pruebas distintas

### A. Recuperar artefactos existentes

| Puntero | Contenido | Archivos | Bytes | MD5 de directorio DVC |
|---|---|---:|---:|---|
| `models/current.dvc` | Doce pipelines y cuatro CBM existentes; se usa RF fold 4. | 16 | 35.544.890 | `6758afd54f231ee0e194603f381b7567.dir` |
| `models/champion_restore.dvc` | Cuatro validaciones originales, metadatos, probe y manifiesto. | 7 | 4.024.988 | `b4b67d267efc7d97bd7dff86c7e363c3.dir` |
| `data/entrega.dvc` | Pronósticos/pedidos 5–11 marzo 2017, seguimiento y trazabilidad. | 17 | 3.621.130 | `13f375fa5bd804bc83ba5b7a3b76546e.dir` |

El remoto `google_drive` está definido en `.dvc/config`. `storage` es local a la
máquina original y no se necesita para reproducir desde otra computadora.
Con el entorno instalado y acceso al remoto, las instrucciones de recuperación son:

```bash
.venv/bin/dvc pull models/current.dvc models/champion_restore.dvc --remote google_drive
.venv/bin/dvc pull data/entrega.dvc --remote google_drive
.venv/bin/python -m reposicion.champion_restore verify
```

Los dos primeros punteros se recuperan automáticamente dentro del bootstrap.
`data/entrega` es una referencia archivada opcional: el flujo de corte nuevo no la necesita.
**Descargar un CSV publicado no vuelve a generar un pronóstico.**

Estos fueron los comandos de sincronización/verificación ejecutados en las etapas previas:

```bash
.venv/bin/dvc push data/entrega.dvc --remote google_drive
.venv/bin/dvc status data/entrega.dvc --cloud --remote google_drive --json
.venv/bin/dvc push models/champion_restore.dvc models/current.dvc --remote google_drive
.venv/bin/dvc status models/champion_restore.dvc models/current.dvc --remote google_drive --cloud --json
```

Resultados registrados: 18 objetos subidos para la entrega y ocho objetos nuevos
para la calibración/restauración; los pesos ya estaban disponibles. Los estados
cloud fueron `{}`. Además, lecturas directas del remoto a directorios temporales,
sin usar la caché de contenidos local, comprobaron los 17 archivos de la entrega
y los 23 archivos de pesos/calibración por hashes. Esa lectura independiente usó
la API del almacenamiento DVC; no se presenta como una inferencia ni como un
`dvc pull` adicional ejecutado.

Informes locales: `reports/entrega/verificacion_dvc.json` y
`reports/champion_restore/cloud_verification.json`. Los hashes `.dir` de la tabla
son índices MD5 de DVC; los SHA-256 de contenido se muestran más abajo.

### B. Restaurar el Champion y recalcular el pronóstico del 5 de marzo

La prueba de restauración/inferencia utilizó los pesos y las cuatro validaciones
versionadas, un **MLflow temporal vacío** y la simulación ya existente. No fue una
prueba de bootstrap completo desde cero: esa prueba corresponde al apartado 4.

Comandos usados en el servidor aislado; la restauración se ejecutó cuando el
servicio ya estaba disponible. El bootstrap realiza esa espera automáticamente:

```bash
docker run --pull never --rm -d --name lab1-mlflow-restore-test \
  -p 127.0.0.1:5012:5000 ghcr.io/mlflow/mlflow:v3.17.2 \
  mlflow server --host 0.0.0.0 --port 5000 --workers 1 \
  --backend-store-uri sqlite:////tmp/restore.db --serve-artifacts \
  --artifacts-destination /tmp/artifacts --allowed-hosts 'localhost:*,127.0.0.1:*'
.venv/bin/python -m reposicion.champion_restore restore --uri http://localhost:5012
```

La restauración se repitió y conservó cuatro runs `restoration_only`, una versión
`READY` y `champion → 1`. La versión fuente es **4**, del run original
`f6062df6a53549a79125fd208aab381d`; los nuevos IDs se vinculan a los originales
mediante tags y un mapa de runs. Las métricas copiadas son históricas, no nuevas
mediciones de entrenamiento. El bootstrap aplica esta misma restauración a su MLflow.

Llamada de inferencia ejecutada dentro de la verificación, sin `fit`:

```python
from reposicion.uncertainty import run

run("2017-03-05", "2017-03-05T12:00:00Z",
    "reports/champion_restore/inference", "http://localhost:5012")
```

El entorno Python usado fue `.venv`; el resultado se contrastó con
`data/entrega/publicacion/forecast_quantiles.csv`, emparejando fecha, tienda y familia.
Se compararon `point_prediction`, `p10`, `p50`, `p90`:

- **12.474 filas**, horizonte **5–11 marzo 2017**.
- Diferencia absoluta máxima registrada: **0.0**; cuantiles ordenados y no negativos.
- Tolerancia de la comparación numérica: `rtol=1e-12`, `atol=1e-9`.
- Solo residuos de ventanas anteriores y disponibles al corte; Champion evaluado
  desde el 3 de marzo. Las ventas posteriores de seguimiento no alimentan la inferencia.
- Sin entrenamiento ni cambios en el MLflow original (51 runs y Champion v4).

El servidor temporal se detuvo con `docker stop lab1-mlflow-restore-test`.
La salida no se sobrescribe: para repetir esa inferencia elegir una carpeta nueva
si `reports/champion_restore/inference` ya existe. El informe registrado es
`reports/champion_restore/verification.json`; detalles en
[docs/restauracion_champion.md](docs/restauracion_champion.md).

### C. Hashes de la reproducción pasada

Comando de lectura ejecutado también al actualizar esta documentación:

```bash
shasum -a 256 models/current/random_forest/fold_4/model.joblib \
  data/entrega/publicacion/forecast_quantiles.csv \
  reports/champion_restore/inference/forecast_quantiles.csv
```

| Archivo | SHA-256 verificado |
|---|---|
| Pipeline RF fold 4 | `bb71d5bf8116b80c8b1fb409b7420a514b2dae90e93e87d064f6235e178583ef` |
| Pronóstico archivado en DVC | `64c2375c90fac0298a964e425148d40b988fbd09c57de5a9908950a116f14d8d` |
| Pronóstico recalculado contra MLflow restaurado | `64c2375c90fac0298a964e425148d40b988fbd09c57de5a9908950a116f14d8d` |

Los dos CSV existentes coinciden en la comparación directa de bytes y en SHA-256.
La comprobación numérica permite tolerancias entre plataformas; no se exige igualar
IDs de runs ni versiones de Registry entre servidores vacíos. Recuperación,
restauración e inferencia están documentadas por separado para no confundirlas.

## 6. Pruebas y archivos del proyecto

La validación enfocada de implementación aprobó **183 pruebas sin entrenamiento**.
Al preparar el PR final se ejecutó también la suite completa: **249 pruebas
aprobadas, con tres advertencias no bloqueantes**, junto con Ruff, formato,
`pip check`, sintaxis del wrapper y auditoría de publicación. Los tests de modelos
utilizan datos sintéticos y no reentrenan los modelos existentes del laboratorio.
Comandos usados, reproducibles desde el entorno preparado:

```bash
.venv/bin/python -m pytest -q tests/test_bootstrap.py tests/test_forecast_clock.py \
  tests/test_orchestration.py tests/test_champion_restore.py tests/test_ingestion.py \
  tests/test_automatic.py tests/test_source_simulator.py tests/test_monitoring.py \
  tests/test_forecast_publication.py tests/test_orders.py \
  tests/test_replenishment_publication.py tests/test_publication_audit.py \
  tests/test_uncertainty.py
.venv/bin/ruff check src tests scripts dags docker/init_airflow.py
.venv/bin/ruff format --check src tests scripts dags docker/init_airflow.py
.venv/bin/python -m pip check
.venv/bin/python scripts/auditar_publicacion.py --working-tree
sh -n scripts/bootstrap.sh
```

Para publicar esta guía se revisaron informes y hashes existentes y se ejecutó
la suite completa con `.venv/bin/python -m pytest -q`; **no se volvieron a ejecutar
el bootstrap, la inferencia ni entrenamientos del laboratorio**.

| Ruta | Responsabilidad |
|---|---|
| `scripts/bootstrap.sh`, `src/reposicion/bootstrap.py` | Preparación del entorno y coordinación reproducible. |
| `src/reposicion/` | Contratos, simulador, ingesta, pronóstico, pedidos, seguimiento y restauración. |
| `dags/` | Orquestación Airflow; la lógica de negocio permanece en módulos independientes. |
| `configs/` | Contratos, disponibilidad, cortes y costos/inventario externos. |
| `docker/Dockerfile.bootstrap` | Airflow e inferencia desde la imagen oficial, con lock de dependencias. |
| `tests/` | Pruebas sintéticas y verificaciones enfocadas. |
| `*.dvc`, `data/original/*.dvc`, `models/*.dvc`, `data/entrega.dvc` | Metadatos de versionado; los contenidos permanecen fuera de Git. |
| `AGENTS.md`, `DECISIONES.md` | Reglas del proyecto, decisiones y bloqueos. |

Git conserva código, configuración, DAGs, documentación y metadatos DVC. No conserva
CSV, pesos, publicaciones, secretos, bases, volúmenes, cachés ni `.venv`.
Para diseño, supuestos e historia de los modelos, consultar [diagnóstico](docs/diagnostico_fuentes.md),
[walk-forward](docs/walk_forward.md), [variables temporales](docs/variables_temporales_v2.md),
[Registry](docs/model_registry.md), [pedidos](docs/motor_pedidos.md) y
[DECISIONES.md](DECISIONES.md). Estos documentos no sustituyen el procedimiento
único de reconstrucción descrito aquí.
