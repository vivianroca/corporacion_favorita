# Laboratorio 1 — Motor de Reposición de Inventario

Producto propuesto para generar pronósticos y pedidos por tienda y familia con
trazabilidad mediante Git, DVC y Airflow. Están implementadas la base y la
**etapa 3: ingesta, validación y snapshots temporales con Airflow**. La infraestructura
exclusiva de lab1 incluye PostgreSQL y MLflow. No se entrenan modelos.

## Estado actual

- Archivos de contexto, metadatos y configuración inicial creados.
- Python 3.12.16 disponible en `/opt/homebrew/bin/python3.12`; `.venv` local creado y verificado en ARM64.
- `lab1/.venv` es el único entorno oficial del laboratorio.
- Repositorio público: [corporacion_favorita](https://github.com/vivianroca/corporacion_favorita).
- Ingesta integrada en main; versionado inicial de datos preparado en `feature/dvc`.
- Docker CLI y Engine 29.9.2 accesibles; Compose v5.6.0 disponible. Imágenes oficiales previstas verificadas en linux/arm64.
- Dependencias instaladas y bloqueadas con hashes en `requirements.lock` para Python 3.12/macOS ARM64.
- pytest 9.2.0: 120 pruebas aprobadas, más integración real con el scheduler y recuperación aislada DVC.
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
- El DAG sondea `data/operational_inbox` cada tres horas con cron `0 */3 * * *`,
  en la zona horaria `America/Guatemala` (UTC−6): minuto cero de las horas 00, 03, 06, 09,
  12, 15, 18 y 21. Un ledger persistente registra IDs, revisiones y checksums;
  solo se ingieren archivos pendientes.
- Se mantiene `catchup=False`: Airflow no crea automáticamente ejecuciones de
  intervalos pasados pendientes. Esto no descarta entregas atrasadas ni correcciones:
  el siguiente ciclo sigue detectando los archivos pendientes mediante el ledger.
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

No se modifican los originales ni se regeneran las entregas existentes. No se
entrenan modelos ni se registran experimentos ficticios. La siguiente etapa requiere
autorización. El remoto DVC externo y el producto de pronóstico se implementarán en su alcance.
