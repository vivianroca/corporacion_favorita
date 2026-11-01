# Laboratorio 1 — Motor de Reposición de Inventario

Producto propuesto para generar pronósticos y pedidos por tienda y familia con
trazabilidad mediante Git, DVC y Airflow. Están implementadas la base y la
**etapa 3: ingesta, validación y snapshots temporales con Airflow**. La infraestructura
exclusiva de lab1 incluye PostgreSQL y MLflow. Se añadieron pronósticos por tienda/familia con evaluación temporal, seguimiento
en MLflow y candidatos Random Forest, HistGradientBoosting y CatBoost.

## Estado actual

- Archivos de contexto, metadatos y configuración inicial creados.
- Python 3.12.16 disponible en `/opt/homebrew/bin/python3.12`; `.venv` local creado y verificado en ARM64.
- `lab1/.venv` es el único entorno oficial del laboratorio.
- Repositorio público: [corporacion_favorita](https://github.com/vivianroca/corporacion_favorita).
- Ingesta y versionado inicial de originales con DVC integrados en `main`.
- Docker CLI y Engine 29.9.2 accesibles; Compose v5.6.0 disponible. Imágenes oficiales previstas verificadas en linux/arm64.
- Dependencias instaladas y bloqueadas con hashes en `requirements.lock` para Python 3.12/macOS ARM64.
- pytest 9.2.0: 154 pruebas aprobadas, más integración real con el scheduler y recuperación aislada DVC.
- `pip check` sin incompatibilidades; instalación editable del proyecto completada.

## Requisitos y preparación del entorno

Python 3.12 ya está instalado en esta máquina. Para preparar otra máquina con Homebrew:

```sh
brew install python@3.12
/opt/homebrew/bin/python3.12 --version
```

Referencia: [fórmula oficial de Homebrew](https://formulae.brew.sh/formula/python%403.12).
La ruta corresponde a Homebrew en macOS Apple Silicon. Se invoca el binario explícito
para no depender del Python global ni de entornos de otros proyectos.

El entorno `.venv` ya existe en esta máquina. En una instalación nueva se crea así:

```sh
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python --version
```

Para activarlo en tu terminal:

```sh
source .venv/bin/activate
python --version
command -v python
```

Debe mostrar Python 3.12.16 y el ejecutable dentro de `lab1/.venv`.
Los comandos siguientes usan la ruta explícita del entorno incluso sin activarlo.

Para reproducir la instalación desde `lab1` con el lock existente:

```sh
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m pytest --version
```

El lock incluye DVC 3.67.1, dvc-gdrive 3.0.1 y PyDrive2 1.21.2.
Las credenciales OAuth se configuran localmente en `.dvc/config.local`, fuera de Git.
Se conserva la combinación instalada de pyOpenSSL 24.2.1, cryptography 43.0.3
y AsyncSSH 2.21.1 para compatibilidad con Google Drive y DVC.

Para regenerar deliberadamente el lock cuando cambien las dependencias:

```sh
.venv/bin/python -m pip install 'pip-tools==7.6.2'
.venv/bin/python -m piptools compile --extra dev --generate-hashes --allow-unsafe --output-file requirements.lock pyproject.toml
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m pytest --version
```

**La instalación ya se completó y verificó.** Los errores DNS de intentos anteriores
no se reprodujeron en el último intento. `requirements.lock` se generó bajo Python
3.12 con versiones transitivas y hashes, y está listo para versionarse en Git.
Los rangos de `pyproject.toml` no sustituyen ese archivo.
El bootstrap de pip-tools precede al lock; el entorno se considerará preparado solo
después de instalar el lock y verificarlo, como se hizo en este entorno. Se comprobará por separado la resolución
Linux/Python 3.12 al preparar CI y Docker.

El paquete `reposicion` se instala desde `src/` y expone la CLI `reposicion`.
La etapa 2 utiliza únicamente la biblioteca estándar y PyYAML; no añade dependencias.

## Infraestructura e ingesta con Airflow

```sh
make infra-prepare
make inbox-init
make infra-build
make infra-up
make infra-status
make test
make lint
```

- Airflow: http://localhost:8082, usuario `admin`; contraseña local en `.env`.
- MLflow: http://localhost:5011; cero runs, sin modelos ni experimentos de prueba.
- PostgreSQL es interno y exclusivo de lab1; no publica un puerto del host.
- DAG `lab1_ingesta_temporal`: descubrir → ingestar → validar → publicar snapshot.
- La simulación existente está montada en solo lectura; no se montan originales.
- El DAG sondea `data/operational_inbox` cada cinco minutos. Un ledger persistente
  registra IDs, revisiones y checksums; solo se ingieren archivos pendientes.
- Sin novedades termina con éxito sin crear publicaciones. Las correcciones crean
  otra versión sin sobrescribir publicaciones anteriores.
- Con `as_of` manual conserva el backfill por períodos sobre el catálogo maestro,
  separado del estado incremental vivo.

Para liberar copias de entregas existentes, sin regenerarlas ni disparar el DAG:

```sh
make inbox-init
make publish-next
make publish-next COUNT=3
.venv/bin/python -m reposicion.cli publish-next --delivery-id train/2017-01-18/r0002
```

Inicializar no vacía una bandeja existente. Publicar de nuevo un ID ya liberado es
una operación sin cambios. La simulación maestra y los originales permanecen intactos.

Configuración incremental, recuperación y comandos: [ingesta_automatica.md](docs/ingesta_automatica.md).
Prueba real del scheduler: [ingesta_automatica_resultados.md](docs/ingesta_automatica_resultados.md).

Parar conservando datos: `make infra-stop`. Retirar contenedores y red conservando
volúmenes: `make infra-down`. No usar `down -v` para una parada normal.

Guía y comandos del DAG: [etapa3_operacion.md](docs/etapa3_operacion.md).
Contenedores, ejecuciones, snapshots y verificaciones: [etapa3_resultados.md](docs/etapa3_resultados.md).

## Datos originales con DVC

DVC **3.67.1** está fijado en las dependencias de desarrollo y en el lock. Solo se
versionan `train.csv`, `stores.csv`, `holidays_events.csv`, `oil.csv` y
`transactions.csv`: **123.397.286 bytes**. Los CSV siguen fuera de Git; se guardan
sus cinco punteros `.csv.dvc`. `test.csv` y `sample_submission.csv` no se versionan.

```sh
.venv/bin/dvc status
.venv/bin/dvc push -r storage
.venv/bin/dvc pull -r storage
.venv/bin/python scripts/verificar_recuperacion_dvc.py
```

El remoto local `storage` está en `~/dvc-storage/corporacion_favorita`. Se verificaron
push de cinco objetos y recuperación en un clon con caché vacía, sin borrar ni
modificar originales o caché principal. El remoto local no es accesible desde otras
máquinas; se propone S3 para compartir con el docente, pendiente de configurar.

La simulación completa y los snapshots no se agregaron aún a DVC. Medición, estrategia,
comandos y cuidados de caché: [dvc.md](docs/dvc.md).

## Contratos y simulación del origen

Con los cinco originales en `data/original/`, ejecutar:

```sh
.venv/bin/python -m reposicion.cli simulate
.venv/bin/python -m reposicion.cli verify-source
.venv/bin/python -m pytest -q
```

Se generan `data/simulation/historical/`, `data/simulation/source_inbox/` y un
catálogo con metadatos y checksums por entrega. El corte inicial configurado es
`2017-01-01T00:00:00-05:00`. Se simulan frecuencias diferentes, demoras y revisiones.
La lectura por corte filtra por disponibilidad, sin convertir ausencias en ceros.

La generación existente se verifica y reutiliza sin reescritura. Cambios de datos o
configuración requieren otra ruta de salida (`simulate --output ...`); nunca se
sobrescribe una generación incompatible. El consumidor trata la bandeja como externa
y de solo lectura. La carga histórica es un lote preparado para la ingesta futura,
no una base operativa ni un snapshot del producto.

Detalles y supuestos: [etapa2_origen.md](docs/etapa2_origen.md).
Evidencia sobre los datos reales: [etapa2_resultados.md](docs/etapa2_resultados.md).

## Git y Docker

Git ya está inicializado en este directorio. Para una carpeta nueva sin repositorio:

```sh
git init -b main
git status --short
```

El remoto `origin` apunta al repositorio personal público `vivianroca/corporacion_favorita`.
GitHub Actions ejecuta pytest en cada PR a main; la rama se protege con PR y check
obligatorio. No se hace merge automáticamente. Política y auditoría:
[github.md](docs/github.md).

Verificaciones de Docker sin iniciar contenedores:

```sh
docker version
docker compose version
docker image ls
```

El último intento accedió correctamente al daemon. Se verificaron localmente
`apache/airflow:3.3.2-python3.12`, `postgres:16` y, como componente opcional,
`ghcr.io/mlflow/mlflow:v3.17.2`, todas con arquitectura `linux/arm64`.
Los contenedores de lab1 ya están levantados. Los identificadores de las bases
están registrados en `DECISIONES.md`; el estado actual está en la evidencia de etapa 3.

## Organización y configuración

- `AGENTS.md`: reglas y límites del trabajo asistido.
- `DECISIONES.md`: decisiones, alternativas y bloqueos.
- `configs/project.yaml`: entorno y bases de infraestructura previstas.
- `configs/sources.yaml`: rutas de originales, generación, contratos y políticas de las cinco fuentes.
- `configs/contracts.yaml`: esquemas, tipos, claves y nulabilidad de las cinco fuentes.
- `configs/availability.yaml`: corte inicial, frecuencias, demoras, correcciones y semilla.
- `configs/pipeline.yaml`: rutas de ingesta y snapshots; variables Docker sobreescriben montajes.
- `docker/compose.yaml`: infraestructura exclusiva de lab1 y persistencia.
- `dags/lab1_ingesta_temporal.py`: orquestación del pipeline temporal.
- `configs/forecasting.yaml`: parámetros preliminares de pronóstico.
- `configs/costs.yaml`: decisiones de negocio aún sin valores.
- `.env.example`: variables locales sin secretos; todavía no se carga automáticamente.
- `src/reposicion/` y `tests/`: contratos, generador, lector, pipeline, CLI y pruebas sintéticas.
- `release.py`: publicador externo de copias en la bandeja operativa.
- `automatic.py`: consumo incremental, ledger transaccional y publicaciones recuperables.
- `propuesta.md`: arquitectura general; su implementación completa no está autorizada.
- `docs/diagnostico_fuentes.md`: diagnóstico completo de las cinco fuentes originales.
- `scripts/diagnosticar_fuentes.py`: genera el diagnóstico sin modificar originales ni instalar dependencias adicionales.

Para repetir el diagnóstico sobre `data/original/`:

```sh
.venv/bin/python scripts/diagnosticar_fuentes.py
```

Se examinan todos los registros usando CSV y SQLite en memoria. El informe incluye
huellas SHA-256 antes y después; se excluyen `test.csv` y `sample_submission.csv`.
Este diagnóstico no implementa el sistema de ingesta ni los contratos futuros.

Los contratos y políticas del origen se cargan y validan en esta etapa.
Los parámetros `null` de pronóstico y costos siguen pendientes y no se usan en el simulador.

Datos, modelos, pronósticos, resultados y secretos se excluyen de Git. DVC guarda
los cinco originales en el remoto local; los demás artefactos y el remoto externo
se prepararán posteriormente. Ningún recurso del proyecto de bicicletas se reutiliza.

## Fuera del alcance actual

Permanecen pendientes los pedidos sugeridos y su evaluación por costos de negocio,
la optimización de modelos y un período final independiente. No se modifican
originales ni entregas existentes; el remoto DVC externo requiere configuración posterior.


## Baseline estacional semanal

La implementación independiente de Airflow está en `src/reposicion/baseline.py`.
Para cada tienda y familia pronostica siete días mediante `predicción(d) = venta(d - 7)`.
Lee únicamente la última revisión disponible **al momento de emisión** en el catálogo
simulado existente. Conserva ceros y ventas fraccionarias; una entrega o registro
faltante produce un error, sin imputación. Los valores reales se leen por separado,
con un corte posterior, exclusivamente para evaluar.

```bash
.venv/bin/python -m reposicion.baseline \
  --start 2017-01-08 \
  --issued-at 2017-01-08T12:00:00Z \
  --evaluated-at 2017-02-10T12:00:00Z \
  --output reports/baseline/2017-01-08 \
  --tracking-uri http://localhost:5011
```

Cada ejecución requiere una carpeta de salida nueva, para conservar los resultados
anteriores. Registra un run real en `corporacion_favorita-baselines`, usando la API
REST del MLflow existente, sin instalar dependencias adicionales. La carpeta local
`reports/` permanece fuera de Git. MLflow conserva parámetros, MAE, WAPE y artefactos
`forecast.csv`, `evaluation.csv`, `parameters.json`, `metrics.json` y `lineage.json`.
Este último contiene recibos, revisiones y checksums de entradas y evaluación.
`run.json` local permite encontrar la ejecución registrada.

MAE es el promedio del error absoluto. WAPE es `sum(abs(real-predicción))/sum(real)`:
se registra como fracción; multiplicar por 100 para expresarlo en porcentaje. Si
todas las ventas reales son cero, WAPE es indefinido y se omite esa métrica en MLflow,
con la etiqueta `wape_defined=false`; MAE sí se registra.

La evaluación del 8 al 14 de enero de 2017 abarcó 54 tiendas × 33 familias × 7 días:
12.474 observaciones, MAE **230,355045** y WAPE **48,544283 %**.
Run verificado `FINISHED`: `b9e248ac36984fa893ada7b81b375892`.
[Ver run en MLflow local](http://localhost:5011/#/experiments/1/runs/b9e248ac36984fa893ada7b81b375892).
Es una evaluación de una sola semana, no una estimación de desempeño general.

La emisión se expresa como instante con zona horaria. Las fechas de venta se
interpretan en `America/Guayaquil`, correspondiente al origen ecuatoriano; esto
no cambia la zona de Airflow. No se modificaron Airflow, DVC ni datos originales.
El archivo `configs/forecasting.yaml` conserva el borrador del producto completo;
este baseline utiliza los parámetros explícitos del comando y deja su copia en MLflow.

## Random Forest: primer candidato

El módulo `src/reposicion/random_forest.py` entrena un modelo global por tienda y
familia, con horizonte de siete días. Usa categorías, calendario conocido, rezagos
de ventas y estadísticas de la semana previa al origen. Las variables se reconstruyen
con las revisiones disponibles en cada corte histórico; la imputación se ajusta solo
en entrenamiento. Conserva exactamente las claves y reales del baseline para evaluar.

```bash
.venv/bin/python -m reposicion.random_forest \
  --baseline reports/baseline/2017-01-08 \
  --output reports/random_forest/2017-01-08 \
  --tracking-uri http://localhost:5011
```

Comparación sobre el **8–14 de enero de 2017**, con emisión al **2017-01-08T12:00Z**,
reales disponibles al **2017-02-10T12:00Z** y **12.474 observaciones** en ambos casos:

| Modelo | MAE | WAPE |
|---|---:|---:|
| Baseline semanal | 230,355045 | 48,544283 % |
| Random Forest | 191,136342 | 40,279459 % |

Random Forest reduce ambos errores un **17,03 % relativo** en esta semana. Se entrenó
con 98.010 ejemplos de ocho orígenes anteriores; se excluyeron 1.782 etiquetas
inexistentes del 25 de diciembre. No se ajustaron hiperparámetros con la evaluación.

[Run del candidato en MLflow](http://localhost:5011/#/experiments/2/runs/b9628a0e6bf94d2a878ffa2c82ed0fdd),
verificado `FINISHED`: modelo entrenado, parámetros, métricas, predicciones, comparación,
importancias, trazabilidad, lock y gráficas de reales frente a pronósticos y distribución
de errores. Los doce artefactos se descargaron y verificaron por SHA-256.

Las dependencias nuevas, `scikit-learn==1.9.1` y `matplotlib==3.11.2`, están instaladas
en `.venv` y bloqueadas con hashes bajo Python 3.12. La suite completa pasa 154 pruebas.
[Detalles del diseño y disponibilidad temporal](docs/random_forest.md).
No se asignó `champion`; la comparación de una semana no basta para promover un modelo.

## System Metrics en próximos entrenamientos

El siguiente entrenamiento de Random Forest abrirá su run **antes de preparar las
filas y ajustar el modelo**, con `mlflow.start_run(log_system_metrics=True)`.
No hace falta cambiar el comando de ejecución. Se utiliza `mlflow-skinny==3.17.2`
y `psutil==7.2.2` en `.venv`, fijados en `pyproject.toml` y en el lock con hashes.

El monitor oficial muestrea cada segundo y registra CPU y RAM bajo `system/`,
incluyendo `system/cpu_utilization_percentage`,
`system/system_memory_usage_megabytes` y `system/system_memory_usage_percentage`.
Estas mediciones corresponden al **host que ejecuta Python**, no al contenedor
servidor de MLflow ni exclusivamente al proceso del modelo. El monitor también
puede registrar disco y red. Para ejecuciones menores de un segundo puede no haber
muestras periódicas; no se retrasa el entrenamiento artificialmente.

Además se guardan `training_duration_seconds` (tiempo de `model.fit`, incluida la
codificación e imputación) y `execution_duration_seconds` (desde la preparación de
filas hasta el guardado/subida de resultados, excluyendo la validación inicial del
baseline y el cierre del monitor), medidos con reloj monotónico. La duración total
también se intenta registrar si el trabajo falla. Se mantienen MAE, WAPE, predicciones,
modelo y ambas gráficas de evaluación dentro del mismo run.

El contexto reutilizable está en `src/reposicion/system_metrics.py`. El baseline,
que no ajusta un modelo, conserva su implementación. Esta preparación **no reentrenó**
los modelos existentes ni agregó métricas retrospectivas a sus runs: las nuevas
series temporales se comprobarán en el próximo entrenamiento autorizado.

## HistGradientBoosting: segundo candidato y Model Registry

```bash
.venv/bin/python -m reposicion.hist_gradient_boosting \
  --baseline reports/baseline/2017-01-08 \
  --forest reports/random_forest/2017-01-08 \
  --output reports/hist_gradient_boosting/2017-01-08
```

Reutiliza las variables, disponibilidad histórica y ocho orígenes de entrenamiento
de Random Forest. Se comprueban la trazabilidad y las mismas 12.474 claves/reales
del 8–14 de enero de 2017, con los cortes originales y sin ajustar hiperparámetros
contra ese horizonte. El early stopping está desactivado.

| Modelo | MAE | WAPE |
|---|---:|---:|
| Baseline semanal | 230,355045 | 48,544283 % |
| Random Forest | **191,136342** | **40,279459 %** |
| HistGradientBoosting | 207,908913 | 43,814057 % |

[Run de HistGradientBoosting](http://localhost:5011/#/experiments/2/runs/39562417052c45bb8dece31675763d19):
`FINISHED`, con parámetros, métricas, predicciones, gráficas y System Metrics reales.
CPU y RAM tienen 16 muestras cada una; el ajuste duró 5,730 s y la ejecución 17,364 s.

Model Registry contiene `corporacion_favorita_hist_gradient_boosting`, versión **1**,
`READY`, con el pipeline completo, firma e input example. URI:
`models:/corporacion_favorita_hist_gradient_boosting/1`. No tiene aliases.

El candidato mejora al baseline; Random Forest conserva el menor error en esta
semana. No se asigna `champion`. Los modelos anteriores no se reentrenaron y sus runs
permanecen intactos. [Diseño, comandos y verificación](docs/hist_gradient_boosting.md).

## Walk-forward: cuatro ventanas semanales

La validación temporal ahora también se ejecuta sobre los cortes **8, 15, 22 y 29 de
enero de 2017**, con horizonte de siete días. El último termina el 4 de febrero.
Random Forest e HistGradientBoosting se reentrenan en cada corte con ocho semanas
móviles y las revisiones conocidas entonces; el baseline utiliza la semana previa.
Los tres modelos evalúan exactamente las mismas claves y reales por ventana.

```bash
.venv/bin/python -m reposicion.walk_forward \
  --config configs/walk_forward.yaml \
  --output reports/walk_forward/january_2017 \
  --tracking-uri http://localhost:5011
```

Hay 12.474 observaciones por ventana y **49.896 por modelo**. El agregado micro usa
la suma de errores de todas las ventanas y la suma de ventas, sin promediar los WAPE.
También se registran medias y desviaciones estándar por ventana.

| Modelo | MAE global | WAPE global |
|---|---:|---:|
| Baseline semanal | 107,077 | 22,471 % |
| Random Forest | 112,485 | 23,606 % |
| HistGradientBoosting | 130,979 | 27,487 % |

[Experimento walk-forward en MLflow](http://localhost:5011/#/experiments/3): **15 runs
FINISHED**, doce de ventana y tres agregados, enlazados por
`walk_forward_id=107d7f6f8961472b8fdf46647ed4f224`. Los ajustes ML mantienen System
Metrics, duración, predicciones, pipeline, trazabilidad y gráficas. Los resultados
locales están en `reports/walk_forward/january_2017/`, fuera de Git.

[Fechas, métricas por ventana, agregados y enlaces a cada run](docs/walk_forward.md).
No se elige Champion ni se agregan versiones de validación al Registry. Se conservan
los runs anteriores y no se modifica Airflow ni DVC. La suite pasa 154 pruebas.

## Variables temporales v2: calendario y escala por serie/familia

La nueva variante incorpora feriados conocidos al corte con alcance nacional,
regional y local, fechas trasladadas, días de trabajo y eventos conocidos. Cada
rezago distingue ausencia, cero observado y contexto excepcional. Agrega medianas
de días de semana comparables y medias recientes sin eventos conocidos.

La imputación usa historia comparable de la misma serie y estadísticas aprendidas
solo en entrenamiento por tienda/familia, con respaldo exclusivo de la misma familia.
No usa una mediana global ni rellena ceros observados. Los hiperparámetros, etiquetas,
cuatro cortes y horizonte permanecen iguales. El baseline original se conserva y
sus nuevos pronósticos/reales se comparan exactamente con los archivos anteriores.

```bash
.venv/bin/python -m reposicion.temporal_walk_forward \
  --previous reports/walk_forward/january_2017 \
  --output reports/walk_forward/temporal_v2_january_2017
```

| Modelo | MAE anterior | MAE v2 | WAPE anterior | WAPE v2 |
|---|---:|---:|---:|---:|
| Baseline semanal | 107,077 | 107,077 | 22,471 % | 22,471 % |
| Random Forest | 112,485 | 90,563 | 23,606 % | 19,005 % |
| HistGradientBoosting | 130,979 | 102,022 | 27,487 % | 21,410 % |

[Experimento temporal v2 en MLflow](http://localhost:5011/#/experiments/4): quince runs
nuevos, con métricas por ventana/agregadas, System Metrics, trazabilidad de calendario,
modelos y gráficas. Se conservan los 18 runs anteriores. No se selecciona Champion ni
se modifica Registry, Airflow o DVC. No se añaden dependencias.

[Diseño, supuestos, métricas por ventana y enlaces a runs](docs/variables_temporales_v2.md).
Los cambios se diseñaron tras revisar estos cortes; confirmar generalización requiere
otro período. La suite completa aprueba 154 pruebas.

## CatBoost: candidato inicial sin optimizar

Se agregó `CatBoostRegressor` 1.2.10, instalado en `.venv` y bloqueado con hashes
bajo Python 3.12. Usa los cuatro folds y las variables temporales corregidas v2,
incluyendo la misma imputación por serie/familia y codificación que RF/HGB.
La configuración inicial en `configs/catboost.yaml` fija 300 iteraciones,
profundidad 6, learning_rate=0.05 y semilla 42, CPU con dos hilos de entrenamiento.
No se entrega eval_set, se desactiva use_best_model y no hay búsqueda de parámetros.
El pipeline incorpora un piso físico cero para las ventas pronosticadas.

```bash
.venv/bin/python -m reposicion.catboost_candidate \
  --previous reports/walk_forward/temporal_v2_january_2017 \
  --output reports/walk_forward/catboost_january_2017
```

| Horizonte | MAE CatBoost | WAPE CatBoost |
|---|---:|---:|
| 8–14 enero | 130,750 | 27,554 % |
| 15–21 enero | 93,462 | 19,630 % |
| 22–28 enero | 63,840 | 13,999 % |
| 29 enero–4 febrero | 80,480 | 16,115 % |
| Global, 49.896 registros | 92,133 | 19,335 % |

[Experimento CatBoost en MLflow](http://localhost:5011/#/experiments/5): cuatro runs
de fold y uno agregado, todos FINISHED. Se guardan parámetros explícitos/resueltos,
pipeline completo, CBM nativo, métricas, predicciones, gráficas, System Metrics,
importancias y trazabilidad. Se verificó la recuperación de todas las predicciones.

[Diseño, comparación con RF/HGB v2 y enlaces por fold](docs/catboost.md).
Se conservan los 33 runs anteriores, el baseline, Registry, Airflow y DVC. No se
optimizaron hiperparámetros ni se asignó Champion. La suite aprueba 154 pruebas.

## Modelos disponibles en MLflow Models

Se publicaron **sin reentrenar** los pipelines temporales v2 de los cuatro folds en
[Model Registry](http://localhost:5011/#/models) y Logged Models:

| Modelo registrado | Versiones v2 |
|---|---|
| `corporacion_favorita_random_forest` | 1–4 |
| `corporacion_favorita_hist_gradient_boosting` | 2–5 |
| `corporacion_favorita_catboost` | 1–4 |

Las versiones corresponden a los cortes 8, 15, 22 y 29 de enero, en ese orden. Se
conserva HGB v1 del experimento anterior. Cada pipeline incluye preprocesamiento,
firma y dependencias y está asociado a su run y MAE/WAPE del fold. Las doce versiones
se recuperaron y reprodujeron sus predicciones originales. No hay Champion ni aliases.

[Detalles, carga y registro idempotente sin fit](docs/model_registry.md).

## Ramas y etiquetas Git de modelado

El código se publica por etapas con tags anotados; el PR conjunto no hace merge
automático. [Mapa de ramas y tags](docs/publicacion_modelos.md). Los datos y pesos
entrenados permanecen fuera de Git.

## Pesos actuales versionados con DVC

`models/current.dvc` referencia exclusivamente **12 pipelines actuales y cuatro
archivos nativos CatBoost**, de los cuatro folds temporales v2. Los 16 binarios
ocupan **35.544.890 bytes** y se almacenan en `storage`, el remoto local existente.
Git guarda el puntero; los `.joblib` y `.cbm` permanecen ignorados.

```bash
.venv/bin/dvc pull models/current.dvc -r storage
```

El push agregó 17 objetos incluyendo el índice de directorio. Se verificó una
recuperación desde caché vacía: 16 archivos idénticos por SHA-256, sin borrar ni
alterar fuentes o cachés principales y sin entrenar. No se versionaron simulación,
snapshots, modelos históricos, predicciones ni otros artefactos.

[Alcance exacto, estructura y verificación](docs/modelos_dvc.md). El remoto local
no es accesible desde GitHub ni por docentes en otros equipos; el remoto externo
sigue pendiente.

## Comparación de modelos existentes

[comparacion_modelos en MLflow](http://localhost:5011/#/experiments/6) contiene
cuatro runs comparables, sin entrenamiento: baseline semanal y RF/HGB/CatBoost
con variables temporales v2. Se leen directamente 20 runs fuente (cuatro folds y
un agregado por modelo); se validan fechas, cobertura y agregación ponderada.

Cada run conserva MAE/WAPE globales y por fold, identificadores de sus fuentes,
tablas CSV/Markdown, barras globales/por fold y radar PNG/SVG. El radar usa
`mínimo error del eje / error del modelo`: 1 representa el menor error.
Sus ejes son global y cuatro folds, con paneles MAE/WAPE; ambos son proporcionales
con iguales observaciones y ventas y no aportan evidencias independientes.

La ejecución local y sus identificadores están en
`reports/comparacion_modelos/2026-10-31/runs.json` (ignorado por Git).
Para crear otra comparación, siempre en runs nuevos y un directorio nuevo:

```bash
.venv/bin/python -m reposicion.compare_models --output reports/comparacion_modelos/NUEVA_EJECUCION
.venv/bin/pytest -q tests/test_compare_models.py
```

La configuración de fuentes está en `configs/comparacion_modelos.yaml`.
No se modifican pesos, Airflow, DVC ni aliases de Registry.

## Champion actual

Por indicación del usuario, el alias `champion` de
`corporacion_favorita_random_forest` apunta a la **versión 4** (último fold existente).
URI: `models:/corporacion_favorita_random_forest@champion`.
Run original: `f6062df6a53549a79125fd208aab381d`, entrenamiento hasta 2017-01-28.
La comparación global de cuatro folds permanece en el run
`c33f236952034629ae3e235ab1d4da0e`: MAE 90.562572, WAPE 19.005031 %;
esas métricas evalúan la estrategia con cuatro ajustes, no solo esta versión.

Trazabilidad DVC: `models/current.dvc` →
`models/current/random_forest/fold_4/model.joblib`, directorio
`6758afd54f231ee0e194603f381b7567.dir`, commit
`09fd79b700d11c50e25ccba5c31287f4152a489f`.
Los tags `champion.*` de la versión conservan esas referencias, ambos runs y
SHA-256 del pipeline. Se verificó el hash contra MLmodel y el índice DVC.
No hubo reentrenamiento ni modificación de pesos, métricas, Airflow o DVC.

## Pronóstico semanal en Airflow

DAG `lab1_pronostico_reposicion`: domingos a las **06:00 America/Guatemala**,
configurable en `configs/pronostico.yaml`, `catchup=False` y backfill manual
por corte/snapshot/versión. Consume snapshots validados y el Champion existente
sin entrenar; publica siete días de P10/P50/P90 con linaje y deduplicación.

[Configuración, despliegue, comandos y pruebas reales](docs/pronostico_airflow.md).
Usar el overlay `docker/compose.forecast.yaml` al gestionar Airflow.
La ejecución programada usa un **replay histórico explícito y fijo** en
`simulation_calendar`: emisión 2017-03-05T12:00Z y snapshot completo de 28 días.
El cron físico de 2026 no se usa como fecha de ventas. Repetir el escenario
reutiliza resultados; el avance del corte requiere configuración y snapshot nuevos.
[Reloj simulado, backfill y prueba programada](docs/reloj_simulado.md).

## Seguimiento por Assets en Airflow

`lab1_seguimiento` se activa por **pronósticos confirmados O ventas evaluables**.
La reconciliación diaria (08:00 Guatemala) es opcional y está desactivada en
`configs/seguimiento.yaml`; `catchup=False`. Compara P50 de publicaciones
inmutables con ventas conocidas al corte y registra MAE, WAPE y cobertura
P10–P90 en `corporacion_favorita-seguimiento` de MLflow.
Reevalúa datos tardíos/correcciones en versiones nuevas y reutiliza resultados
sin cambios. [Políticas, despliegue y backfill](docs/seguimiento_airflow.md).


## Dependencias entre DAGs

DAG 1 publica Assets de snapshots y ventas; DAG 2 espera el snapshot confirmado
**solo al llegar su cron semanal**; DAG 3 consume eventos de pronósticos o ventas
independientemente. Un fallo de DAG 2 no publica un Asset y no impide evaluar
pronósticos históricos. Se conserva backfill e idempotencia.

[Arquitectura, migración del catálogo histórico y pruebas](docs/dependencias_assets.md).

## Motor independiente de pedidos sugeridos

`reposicion.orders` transforma los P10/P50/P90 existentes en pedidos por tienda y
familia con costos configurables en `configs/costs.yaml`, sin cargar ni entrenar
modelos. Usa escenarios diarios conjuntos y cuantiles de demanda acumulada;
no suma los cuantiles diarios. Conserva versiones por configuración e inventario.

```bash
.venv/bin/python -m reposicion.orders --forecast-dir reports/uncertainty/2017-03-05-v2 --costs configs/costs.yaml --output-root reports/orders
```

Los costos/inventarios son supuestos ilustrativos explícitos. El plazo de dos días
forma parte del horizonte de siete; el pedido llega el día 3 y cubre días 3–7.
Nueve pruebas aprobadas y 1.782 pedidos generados. Cambiar solo merma 1→5 redujo
las recomendaciones manteniendo los mismos pronósticos y escenarios.
[Política, distribución, validación y resultados](docs/motor_pedidos.md).
El DAG `lab1_pronostico_reposicion` ejecuta este motor después del pronóstico y
solo confirma el Asset cuando también están completos los pedidos.
[Integración, versiones de costos y prueba histórica](docs/pedidos_en_airflow.md).

## Entrega histórica de resultados

`data/entrega.dvc` referencia **17 archivos, 3.621.130 bytes**: publicación de
pronósticos/pedidos 5–11 marzo 2017, seguimiento completo al 2 de abril,
configuración de costos, manifiestos y trazabilidad modelo/run/DVC/Assets.
Se subieron 18 objetos a `google_drive`; status local/cloud sin diferencias y
lectura remota completa verificada por hash. No contiene credenciales ni pesos,
ni copias completas de bases/simulación/snapshots.

El contenido permanece fuera de Git. El puntero es local, todavía sin commit ni
push Git; para recuperarlo en otra computadora primero debe estar disponible
ese metadato y la configuración/autenticación de google_drive (con dvc-gdrive).

```bash
.venv/bin/dvc pull data/entrega.dvc --remote google_drive
```

Inventario: `data/entrega/manifest.json`; descripción: `data/entrega/README.md`.
Verificación de descarga remota: `reports/entrega/verificacion_dvc.json`.
