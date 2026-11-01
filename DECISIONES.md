# Decisiones técnicas y de producto

## D001 — Alcance limitado a la base del proyecto

Se implementan únicamente documentos, metadatos, configuración y estructura mínima
de la etapa 1. Se posponen datos, ingesta, modelos, DAGs, Compose y DVC operativo.
Esto respeta la autorización por etapas y evita código sin comportamiento.

## D002 — Python 3.12 independiente

Se exige `>=3.12,<3.13` y un entorno `.venv` en `lab1`. No se usa el entorno de otro
proyecto. No se encontró Python 3.12 en PATH, Homebrew, Frameworks ni en las ubicaciones
habituales revisadas de pyenv y uv. La creación del entorno queda pendiente.

La alternativa de usar Python 3.14 se descarta porque incumple el requisito.
Se recomienda `brew install python@3.12` desde la terminal del usuario. No se ejecutó
la instalación porque modifica ubicaciones externas al workspace.

## D003 — Dependencias mínimas y bloqueo verificable

Se declaran PyYAML y herramientas de desarrollo: pytest, Ruff y pip-tools.
No se incorporan todavía bibliotecas de ML, DVC ni Airflow al entorno local.
Airflow se ejecutará en una imagen propia basada en su imagen oficial.

Se elige pip-tools 7.6.2 para producir `requirements.lock` con versiones exactas y
hashes a partir de `pyproject.toml`, bajo Python 3.12. No se fabrica un lock sin
resolver y comprobar las dependencias. Falta verificar instalación y compatibilidad.
Se validará por separado el entorno Linux de CI/Docker antes de reutilizar el lock.

## D004 — Estructura sin módulos ficticios

Se crean `configs/`, `src/` y `tests/` con contenido útil. No se generan módulos
vacíos, DAGs de ejemplo, pruebas que solo repitan configuración ni directorios de
artefactos sin uso actual. pytest queda configurado, pero no se afirma que existan
pruebas aprobadas.

## D005 — Configuración externa preliminar

Se separan proyecto, fuentes, pronóstico y costos en YAML. Se dejan en `null` el
horizonte, cuantiles, costos y política de inventario para no inventar decisiones
de negocio. Los parámetros deben justificarse antes de su implementación. No hay
cargador de configuración en esta etapa. `.env.example` no contiene credenciales.

## D006 — Independencia de infraestructura

Se prevén Airflow `3.3.2-python3.12`, PostgreSQL 16 y proyecto Compose `lab1`.
No se reutiliza la imagen personalizada de bicicletas, sus archivos, bases, redes,
volúmenes ni DAGs. No se inició ningún contenedor. MLflow sigue siendo opcional.

## D007 — Git bloqueado por el entorno

Se ejecutó `git init -b main`, que falló con `.git: Operation not permitted`.
El perfil actual permite leer `.git`, pero no inicializarlo. No se intentó eludir
la restricción usando un repositorio externo. Quedan pendientes la inicialización,
los commits, el remoto y la protección de la rama principal.

## D008 — Docker disponible como CLI, daemon inaccesible

`docker version` mostró el cliente 29.9.2 para darwin/arm64, pero denegó el acceso
al socket `/Users/vivianroca/.docker/run/docker.sock`. `docker image ls` falló por
el mismo motivo. Compose reportó v5.6.0. Que Docker funcione en otra terminal no
demuestra acceso desde esta sesión. Las imágenes locales no están verificadas.

## D009 — Inspección de Homebrew limitada

`brew list --versions python@3.12` intentó actualizar metadatos y falló por permisos
de escritura en `/opt/homebrew/var/homebrew/locks`. No se instaló ningún paquete.
La ausencia del intérprete se basa en la búsqueda de ejecutables y ubicaciones,
no en una consulta exitosa del inventario de Homebrew.

## D010 — Contratos futuros conservados

Se mantiene como requisito que el consumidor nunca modifique la bandeja externa,
que todo pronóstico respete la información disponible al corte y que correcciones
y publicaciones tengan versiones trazables. Sus reglas concretas se desarrollarán
en las etapas correspondientes y no se implementan ahora.

## Pendientes para cerrar la etapa 1

1. Completado: Python 3.12.16 disponible y `.venv` local creado y verificado.
2. Completado: dependencias bloqueadas e instaladas; `pip check` y disponibilidad de pytest verificados (ver D013).
3. Completado: Git inicializado en `main`, sin commits ni remoto (ver D015).
4. Completado: acceso a Docker e imágenes oficiales verificados sin iniciar servicios (ver D014).
5. Actualizar el estado documentado con evidencia real de esas verificaciones.

## Verificaciones de los archivos creados

- `pyproject.toml` se analizó correctamente con `tomllib` usando `python3 -B`.
  El Python 3.14 disponible se utilizó únicamente para inspeccionar TOML y archivos,
  sin instalar paquetes ni crear un entorno; no valida compatibilidad con Python 3.12.
- Los cuatro archivos de `configs/` se analizaron correctamente con `YAML.safe_load`
  del Ruby del sistema. Esto verifica sintaxis, no los contratos de negocio futuros.
- Se confirmó que no existen `.venv` ni `.git` y que no se generó un lock ficticio.
- No se ejecutaron pruebas de producto ni se inició infraestructura.

## D011 — Python disponible y entorno creado

Tras la instalación realizada por el usuario, `command -v python3.12` encontró
`/opt/homebrew/bin/python3.12`, que reporta Python 3.12.16. Se ejecutó:

```sh
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -I -c 'import sys, platform; print(sys.version); print(sys.executable); print(sys.prefix); print(sys.base_prefix); print(platform.machine()); assert sys.version_info[:2] == (3,12); assert sys.prefix != sys.base_prefix'
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install 'pip-tools==7.6.2'
.venv/bin/python -m pip list --disable-pip-version-check
```

Se verificaron Python 3.12.16, arquitectura arm64 y un entorno independiente en
`lab1/.venv`, con base en Homebrew. No se modificó ningún otro proyecto.

La instalación de pip-tools falló porque esta sesión no pudo resolver `pypi.org`
(`NameResolutionError`). No es evidencia de que la versión solicitada no exista.
El entorno contiene únicamente pip 26.2.2; faltan el lock, las dependencias y pytest.

También se reintentaron `git init -b main`, `docker version` y `docker image ls`:
persisten los bloqueos de escritura en `.git` y acceso al socket de Docker.
No se iniciaron contenedores.

## D012 — Entorno oficial de lab1

El usuario confirmó que el único entorno del laboratorio será `lab1/.venv` con
Python 3.12. Se recreó tras la eliminación solicitada previamente y se verificó
Python 3.12.16 en ARM64. No se utilizará ningún entorno de otro proyecto.

Tras la indicación de continuar se volvió a ejecutar:

```sh
.venv/bin/python --version
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install --retries 1 --timeout 15 'pip-tools==7.6.2'
```

La instalación continúa bloqueada por `NameResolutionError` al resolver
`pypi.org` desde la ejecución de comandos de esta sesión. No se instalaron las
dependencias ni se generó `requirements.lock`; pytest permanece pendiente.
El README contiene los comandos para completar la instalación desde una terminal
con acceso a PyPI. No se sustituyó PyPI por otra fuente ni se alteraron permisos.

## D013 — Instalación y bloqueo completados

El último reintento accedió correctamente a PyPI desde `lab1/.venv` con Python
3.12.16. Se ejecutaron satisfactoriamente:

```sh
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install --retries 1 --timeout 15 'pip-tools==7.6.2'
.venv/bin/python -m piptools compile --extra dev --generate-hashes --allow-unsafe --output-file requirements.lock --cache-dir /private/tmp/lab1-pip-tools-cache pyproject.toml
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install --require-hashes -r requirements.lock
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m pytest --version
.venv/bin/ruff --version
```

Versiones principales: PyYAML 6.0.3, pytest 9.2.0, Ruff 0.17.3 y pip-tools 7.6.2.
El lock incluye dependencias transitivas y hashes; se instaló con comprobación de
hashes. El proyecto `lab1-reposicion` 0.1.0 quedó instalado en modo editable.
`pip check` no encontró dependencias incompatibles. Se verificaron el intérprete
local, el TOML y los cuatro YAML con las librerías del entorno oficial.

`python -m pytest --collect-only -q` terminó con código 5 y cero pruebas, resultado
esperado porque no hay comportamiento implementado ni casos de prueba todavía.
Esto no se presenta como una suite aprobada. No se agregaron pruebas artificiales.

La comprobación de compatibilidad del lock en Linux/CI sigue pendiente para su
etapa. Los bloqueos anteriores de Git y Docker no se reevaluaron en esta tarea.
No se inició infraestructura ni se implementó funcionalidad de la etapa 2.

## D014 — Acceso a Docker e imágenes verificados

Se ejecutaron `docker version`, `docker compose version` y `docker image inspect`
sobre las imágenes oficiales previstas. Los comandos finalizaron correctamente.
Docker Desktop 4.96.1 responde con Engine 29.9.2 en linux/arm64; el cliente es
29.9.2 para darwin/arm64 y Compose es v5.6.0. El contexto es `desktop-linux`.

Imágenes locales verificadas, todas linux/arm64:

| Imagen | Identificador local |
|---|---|
| `apache/airflow:3.3.2-python3.12` | `sha256:9df9c8be4096b9cc626bd7cb1f2b8c712eef66c59c615f8c7e6200871ca10bd1` |
| `postgres:16` | `sha256:a902560563d3a5661228585f53474c5065e7f273b21ffd77e555a8b5682c5690` |
| `ghcr.io/mlflow/mlflow:v3.17.2` | `sha256:2cc40b3208991940d824d04f339833a0b69507569012aa5ec545690608602fc0` |

Son identificadores locales de imagen, no digests de manifiesto de un registro.
MLflow sigue siendo opcional. No se inspeccionaron recursos del proyecto de bicicletas,
descargaron imágenes, crearon ni iniciaron contenedores. Se actualizó el indicador
de verificación en `configs/project.yaml`. Los errores de socket previos quedan
resueltos en esta comprobación; Git no se reevaluó.

## D015 — Git inicializado y estructura mínima comprobada

Se ejecutó `git init -b main`. Tras fallar por el sandbox, el comando se repitió
con la aprobación de ejecución correspondiente y creó `.git` dentro de `lab1`.
`git status --short --branch` confirmó `No commits yet on main`.

Se comprobó que están presentes los documentos de contexto y decisiones,
`pyproject.toml`, `requirements.lock`, `.env.example`, `.gitignore`, los cuatro
YAML de `configs/` y la documentación de `src/` y `tests/`. No fue necesario crear
módulos vacíos ni ampliar la estructura a etapas no autorizadas.

`git check-ignore` confirmó la exclusión de `.venv/bin/python`, `.env`, una ruta
de datos y una ruta de modelos. No se agregaron archivos al índice, hicieron
commits, configuraron remotos ni publicaron cambios.

La base local de la etapa 1 está preparada. La integración con GitHub, las pruebas
de comportamiento y la infraestructura ejecutable siguen pendientes para su
alcance correspondiente. La etapa 2 no está autorizada.

## D016 — Diagnóstico exploratorio autorizado de las fuentes originales

El usuario autorizó explícitamente diagnosticar los cinco CSV ya descargados,
antes de implementar la simulación y los contratos. Se agregó esta excepción
acotada en `AGENTS.md`; no autoriza ingesta, modelos, DAGs ni servicios.

Se creó `scripts/diagnosticar_fuentes.py`, un análisis local con biblioteca estándar
y SQLite exclusivamente en memoria. No instala dependencias adicionales ni genera
una base persistente. Se eligió frente a incorporar pandas porque el diagnóstico
puede ejecutarse con las herramientas existentes y lectura completa de registros.

El resultado está en `docs/diagnostico_fuentes.md`. Se guarda en `docs/` para que
el informe agregado pueda versionarse; `data/` y los artefactos de `reports/`
mantienen su exclusión de Git. No se añadieron archivos al índice ni hicieron commits.
`test.csv` y `sample_submission.csv` se excluyeron del análisis.

Verificaciones ejecutadas:

```sh
.venv/bin/python scripts/diagnosticar_fuentes.py
.venv/bin/ruff check scripts/diagnosticar_fuentes.py
.venv/bin/ruff format --check scripts/diagnosticar_fuentes.py
git ls-files -- data
git check-ignore data/original/train.csv data/original/stores.csv data/original/holidays_events.csv data/original/oil.csv data/original/transactions.csv
```

La ejecución completa terminó correctamente; Ruff y formato aprobaron. Las huellas
SHA-256 de los cinco originales coinciden antes y después, y se contrastaron de
nuevo con el informe. Ningún dato está registrado en el índice de Git y los cinco
CSV están ignorados. No se modificaron los originales.

Hallazgos principales:

- Ventas: 3.000.888 filas, 54 tiendas, 33 familias; sin nulos ni duplicados de ID
  o clave tienda–familia–fecha. Cobertura 2013-01-01 a 2017-08-15, salvo cuatro
  25 de diciembre. El 31,30% de las ventas es cero y 462.113 filas tienen parte fraccionaria.
- Tiendas: 54 filas, clave única y sin tiendas desconocidas en ventas o transacciones.
- Petróleo: 1.218 filas, 43 precios vacíos y ausencia de fines de semana. En la
  unión con fechas de ventas hay 521 fechas sin precio observado.
- Transacciones: 83.488 filas; faltan 7.448 pares tienda–fecha presentes en ventas,
  de los cuales 118 tienen ventas agregadas positivas. No tratar ausencia como cero.
- Feriados: 350 eventos sobre 312 fechas; la fecha no es una clave única.
  Su aplicación depende del ámbito geográfico y del traslado del evento.

El informe distingue evidencia de hipótesis de contrato. Los CSV no indican cuándo
se conoció cada dato, sus revisiones ni la vigencia de los atributos de tiendas.
Las políticas de disponibilidad, correcciones, ausencias y unión de eventos quedan
pendientes para la simulación y contratos; no se implementaron en este diagnóstico.

## D017 — Autorización e implementación de la etapa 2

Se autorizan contratos de datos, carga histórica y simulación del origen. Se actualizó
`AGENTS.md` y se creó la rama local `etapa2-contratos-simulacion`, sin commits ni
publicaciones. No se implementaron componentes de la etapa 3, modelos ni DAGs.

Se implementó el paquete de espacio de nombres `reposicion` con módulos funcionales
de contratos, simulación, lectura y CLI. Se mantuvieron las dependencias existentes,
se regeneró el lock y se reinstaló el proyecto en modo editable bajo Python 3.12.

## D018 — Contratos basados en los datos reales

`configs/contracts.yaml` define las columnas reales, tipos, nulabilidad, enumeraciones
y claves. Las ventas usan Decimal finito no negativo; no se exige cantidad entera.
La familia admite valores nuevos y no se fijan las 54 tiendas como universo permanente.
Se valida unicidad global de ID y de fecha–tienda–familia. Transacciones conserva
fecha–tienda. Feriados permite varios eventos por fecha y valida ámbito nacional,
regional o local contra el catálogo geográfico.

Se distingue cero de celda vacía y de fila ausente. Ventas vacías son inválidas;
petróleo vacío es permitido. No se rellenan fechas, familias ni transacciones.
Los errores detienen la publicación del conjunto. Se pospone la cuarentena operativa.

## D019 — Disponibilidad y corte inicial como supuestos

Las políticas están en `configs/availability.yaml`; no proceden de metadatos de Kaggle.
Se elige un corte inicial 2017-01-01 00:00 en America/Guayaquil para disponer de
varios años de histórico y meses posteriores de entregas. Las ventas se conocen al
día siguiente, las transacciones llegan los lunes, el petróleo el siguiente día hábil
y el calendario se actualiza semanalmente. Los eventos no planificados no se anticipan.
Se usa una dimensión de tiendas estática con referencia sintética 2013-01-01 porque
el CSV no contiene vigencias; su fidelidad histórica no puede comprobarse.

En días con eventos planificados e inesperados, el archivo espera la disponibilidad
del último de ellos. Los detalles y horarios están en `docs/etapa2_origen.md`.
No se usa el calendario completo para revelar eventos futuros no anticipables.

## D020 — Correcciones sintéticas y determinismo

La selección de demoras y correcciones usa SHA-256 de semilla, fuente, fecha y
escenario. No depende del reloj ni del orden de filas. Los porcentajes son umbrales,
no cuotas exactas. La versión provisional reduce una medida positiva; siete días
después de su disponibilidad real, otra versión restaura el dato original.
No se alteran ceros ni nulos para crear revisiones. Son particiones completas que
se reemplazan por revisión, no cantidades a sumar ni correcciones históricas reales.

Los originales se conservan intactos y actúan como versión final de referencia.
No se simulan eliminaciones de registros ni correcciones de claves en esta versión.

## D021 — Carga inicial y bandeja externas al consumidor

La salida es `data/simulation/{historical,source_inbox}` más un catálogo. El histórico
contiene las entregas disponibles al corte, no todas las filas por fecha de hecho.
Conserva revisiones previas y un orden de carga; es el lote inicial para la ingesta
futura, sin crear todavía una base operativa ni snapshots del producto.

El generador es un productor externo explícito. `DeliveryCatalog` solo lee y su
método de lectura requiere un corte con zona horaria. No escribe marcas, mueve
archivos ni actualiza la bandeja. El montaje `:ro` se aplicará en infraestructura
posterior; en esta etapa se verifican ausencia de escrituras y persistencia de huellas.

## D022 — Publicación completa e idempotencia

Se eligió SQLite temporal para claves globales y agrupación por fecha sin cargar
los tres millones de filas como objetos simultáneamente en RAM. Se valida todo
antes de publicar, con salida temporal adyacente y renombrado final. Un único
productor por ruta es un supuesto explícito de esta etapa.

La identidad combina versión del generador, contratos, política y hashes de fuentes.
Reejecutar con la misma identidad audita y devuelve la salida sin modificarla.
Una salida de otra identidad, corrupta o con archivos extra provoca un error: nunca
se repara ni sobrescribe una entrega. Se usa otra ruta para otra simulación.

Cada entrega incluye referencia, disponibilidad, revisión, vínculo de corrección,
cantidad de filas, checksums y marcas de escenario. El catálogo conserva la política
completa y hashes de originales y configuración. No se presenta esto como firma
criptográfica ni sustituto del versionado DVC pendiente.

## D023 — Evidencia y cierre de la etapa 2

Se ejecutaron 52 pruebas sintéticas: todas aprobaron. Ruff y formato se verificaron.
Los cinco originales pasaron los contratos completos. Se generaron 5.071 entregas:
4.362 históricas y 709 de bandeja, con 228 demoras y 174 particiones corregidas.
Se verificaron todos los sobres y payloads, la igualdad de conteos finales con cada
original y la idempotencia mediante hashes y tiempos de modificación.

Los cinco SHA-256 originales siguen coincidiendo con el diagnóstico previo y los
datos permanecen ignorados por Git. La evidencia detallada está en
`docs/etapa2_resultados.md`. No se levantaron servicios ni se creó un DAG.
No se avanzará a la etapa 3 sin autorización.

## D024 — Autorización de etapa 3 e infraestructura aislada

El usuario autorizó ingesta, validación y snapshots mediante Airflow, además de
levantar PostgreSQL y MLflow. Se actualizó AGENTS.md y se trabajó en la rama local
`etapa3-ingesta-airflow`, sin commits ni publicaciones. Se mantuvo la prohibición
de alterar originales, regenerar entregas y entrenar modelos.

Se verificaron las imágenes locales y puertos antes de iniciar. Se eligieron 8082
para Airflow y 5011 para MLflow, publicados solo en loopback. PostgreSQL no publica
puerto. Compose crea exclusivamente recursos prefijados `lab1`, sin conexiones a
redes ni reutilización de volúmenes de otros proyectos.

Se construyó una imagen derivada de Airflow sin descargas ni instalaciones: el
runtime ya incluye PyYAML 6.0.3. Se eligió LocalExecutor con API, scheduler y
dag-processor separados. No se necesita Redis ni Celery para este alcance.

## D025 — Persistencia y credenciales de infraestructura

PostgreSQL 16 guarda metadatos de Airflow. MLflow 3.17.2 usa SQLite y artefactos en
dos volúmenes propios, separados de los artefactos operativos. No se instalaron
Airflow ni MLflow en `.venv`. Se generaron secretos locales en `.env`, ignorado por
Git y con permisos 600. SimpleAuthManager administra `admin` para desarrollo local;
los secretos JWT, API y Fernet son independientes y compartidos solo por Airflow.

`make infra-stop` y `make infra-down` conservan volúmenes. La documentación explica
inicio, parada y reconstrucción de imagen. No se recomienda borrar volúmenes como
parte de una parada normal. MLflow se verificó sin crear runs ni experimentos;
solo existe su experimento Default inicializado automáticamente.

## D026 — Pipeline temporal y cuarentena

La lógica independiente está en `ingestion.py`. Descubrir fija los recibos conocidos
al corte, seleccionando la última revisión de cada partición y dimensión de tiendas.
Ingestar verifica y copia a landing; validar comprueba estructura, tipos, referencias,
fechas, conteos y unicidad global mediante SQLite temporal. Solo después se publican
cinco CSV coherentes con el mismo corte. No se expande transacciones por familia ni
se hace una unión multiplicativa con feriados.

Un dato inválido bloquea el snapshot y deja recibo y error en cuarentena; su payload
permanece en landing si había pasado el control de integridad. No se vuelve a una
revisión anterior silenciosamente. Los nulos permitidos, ceros, fechas sin registros
y fuentes todavía ausentes se conservan sin imputar ni provocar fallas artificiales.

## D027 — Linaje, idempotencia y reprocesamiento

La identidad del plan incluye corte, ventana opcional, hashes del manifiesto, contratos
y módulos, generación del origen y recibos. Se archiva el contrato exacto. Los
snapshots incluyen linaje completo y checksums de salidas. Los artefactos se publican
completos mediante temporales, se reutilizan sin reescritura y se auditan al reintentar.
La corrupción se rechaza en lugar de repararse silenciosamente.

La carga histórica y bandeja se montan juntas en solo lectura. Los originales no
se montan en Airflow. El productor externo no se invoca desde el pipeline.
Un corte posterior incorpora correcciones; volver al corte previo conserva su versión.
Cambiar código o contrato produce otro plan y requiere guardar la versión anterior
del código para reproducirla. DVC se implementará en su etapa.

## D028 — DAG manual y prueba de una ventana pequeña

Se elige `schedule=None` para esta etapa, con corte explícito y una ejecución activa.
No se interpreta el intervalo creado por un trigger manual como fecha de conocimiento.
Los reintentos por tarea son seguros y XCom transporta solo IDs o resúmenes, no datos.
La cadencia automática del producto se definirá con el alcance siguiente.

Se ejecutó la referencia 2017-01-18 con cortes 2017-01-20 y 2017-01-27. La revisión 2
ya existía y se publicó el 26 de enero. Las tres ejecuciones reales (inicial, corregida
y repetida) terminaron success. Ventas conserva 1.782 filas y solo cambia una medida.
Las transacciones aún no disponibles al primer corte pasan de 0 a 53 sin fabricar ceros.
El día no contiene eventos: esa ausencia no causó un fallo.

## D029 — Verificaciones finales y límites

72 pruebas sintéticas aprobadas, Ruff/formato sin errores y pip check sin conflictos.
Se comprobó login y API de Airflow, health de MLflow desde la red interna y cinco
contenedores healthy. MLflow contiene cero runs. El DAG no tiene errores de importación.

La repetición preservó contenido y mtime de los 31 archivos operativos. Los 10.150
archivos de originales y simulación conservaron rutas, hashes y mtime. Datos y secretos
siguen fuera de Git. No se hizo una carga operativa completa del histórico: se probó
la ventana pequeña solicitada. No hay problemas bloqueantes en ese alcance.
Evidencia y comandos en `docs/etapa3_resultados.md` y `docs/etapa3_operacion.md`.
No se avanzará al modelado ni a la siguiente etapa sin autorización.

## D030 — Automatismo con control persistente

Se autoriza ejecutar `lab1_ingesta_temporal` cada cinco minutos. Se fija el cron
`*/5 * * * *`, catchup desactivado y una ejecución activa. El DAG se habilita y el
scheduler crea los runs. No se implementa un cron externo ni un bucle que dispare
runs por API. El corte programado procede del intervalo de Airflow y se congela
junto con el catálogo observado bajo el run ID para sus reintentos.

La ruta manual con `as_of` sigue disponible para backfill sobre el maestro. No
modifica el ledger vivo. Las ramas no elegidas aparecen skipped, sin que esto sea
un fallo. El productor externo y el observador no disparan DAGs.

## D031 — Nueva bandeja y publicador progresivo

Se crea `data/operational_inbox` vacía de entregas, sin borrar ningún archivo de
la simulación maestra ni los originales. `release.py` copia payload y sobre exactos,
conservando fechas, revisiones y checksums; nunca regenera datos. La disponibilidad
histórica y la fecha física de liberación se registran separadamente. Las versiones
del catálogo, incluida la vacía, se conservan por hash. Solo el publicador escribe
en la bandeja, con lock de productor y actualización atómica del catálogo.

La primera liberación predeterminada es tiendas, como dimensión necesaria. Las
correcciones requieren la revisión anterior. Se puede elegir un ID o un lote
pequeño con la CLI. Volver a inicializar o publicar un ID no elimina ni duplica datos.
Docker monta también esta bandeja en solo lectura, separada del maestro.

## D032 — Ledger y estado validado acumulado

Se usa SQLite en el volumen persistente existente `lab1_operational`, bajo
`automatic/<stream_id>/`. Registra ciclos, recibos procesados, revisiones activas,
filas validadas y publicaciones. Las claves únicas y BEGIN IMMEDIATE evitan doble
consumo. Los IDs ya procesados se contrastan con sus revisiones y checksums; un
cambio de contenido bajo el mismo ID es un error, no una actualización silenciosa.

Solo se copian y validan los CSV pendientes. Para una publicación completa se lee
el estado previo ya validado de SQLite, sin reingerir payloads anteriores. Un ciclo
vacío registra su resultado y finaliza success sin generar archivos de publicación.
Una corrección sustituye la partición activa y crea una publicación enlazada con
la anterior, que permanece intacta. Cambios de contrato exigen migración explícita
o stream nuevo, evitando ignorar silenciosamente validaciones anteriores.

## D033 — Recuperación transaccional de publicaciones

La publicación se prepara en un directorio persistente antes de confirmar el estado.
Una transacción confirma recibos, filas, resultado y referencia a la publicación.
Después se hace visible el directorio y se marca published. Si el proceso se corta
entre estas operaciones, el próximo intento completa la publicación preparada sin
releer archivos confirmados. También se prueba recuperación antes del commit y
catálogo congelado cuando llegan nuevas entregas durante un reintento.

Los datos inválidos revierten el lote y dejan evidencia en cuarentena. No se marcan
como procesados ni se publican resultados parciales. Los ciclos sin dimensión de
tiendas pueden esperar nuevas entregas sin convertir ausencias en errores de datos.

## D034 — Pruebas del automatismo

La suite sintética aprobó 88 pruebas, incluyendo consumo concurrente, correcciones,
checksum conflictivo, validación semántica, idempotencia, interrupciones en puntos
de commit y separación de backfill. La prueba real se realiza mediante los runs
scheduled del scheduler; el observador solo consulta API y ledger. Los resultados,
IDs y archivos realmente procesados se conservan en
`docs/ingesta_automatica_resultados.md`. No se entrenan modelos ni se generan runs MLflow.

## D035 — Resultado real del scheduler

Los runs scheduled del 2026-10-31 a las 06:10, 06:15 y 06:20 UTC terminaron success.
Procesaron respectivamente tiendas (un CSV, 54 filas), ventas del 2017-01-18 (un
CSV, 1.782 filas) y cero archivos. No se dispararon manualmente esos runs. El ledger
confirma dos recibos únicos y dos publicaciones; el ciclo vacío no produjo otra.
Los 16 archivos de publicaciones y landing conservaron contenido y mtime durante
ese ciclo. El DAG sigue habilitado cada cinco minutos.

Se verificó también backfill manual por la ruta histórica, sin alterar el ledger
vivo. Los 31 artefactos operativos anteriores y las 10.150 entradas originales y de
simulación maestra permanecieron intactos. Las versiones del catálogo preservan el
estado inicial vacío y las dos liberaciones. Airflow mantiene ambos orígenes en
solo lectura; el publicador es el único escritor de la bandeja progresiva.
Los servicios existentes están healthy y MLflow continúa con cero runs.

## D036 — Publicación personal y primera revisión

El usuario autoriza un repositorio público con nombre exacto `corporacion_favorita`
en su cuenta personal. Se verificó la sesión `vivianroca` de tipo User y la ausencia
de un repositorio previo con ese nombre. Se conserva el directorio local lab1.

Como no existían commits, se prepara una base mínima en main y la implementación
en feature/ingesta-airflow, con el primer PR hacia main y sin merge automático.
El remoto origin usa HTTPS sin credenciales embebidas. La identidad de commits
se configura localmente con email noreply, sin modificar Git global.

## D037 — Exclusiones y auditoría antes de publicar

Se amplió .gitignore para proteger datos, modelos, bases, claves y volúmenes también
fuera de las rutas esperadas. .env.example deja sus secretos vacíos. Se implementó
una auditoría de archivos de trabajo, índice e historial completo de las ramas a
enviar, con máximo de 1 MiB por blob y detección de patrones y secretos locales.
Los errores no imprimen los valores sensibles. Quince pruebas verifican la auditoría.

La inspección inicial aprobó 49 archivos, todos pequeños; el mayor fue el PDF de
186.445 bytes. Se repite la auditoría después de crear commits y antes de push,
para comprobar también blobs históricos. No se incluyen datos ni artefactos Docker.

## D038 — CI y protección

El workflow de PR hacia main usa Python 3.12/Ubuntu 24.04, dependencias bloqueadas
con hashes, auditoría de historia, Ruff y pytest. Las acciones oficiales se fijan
a SHAs obtenidos de sus releases, no a tags mutables. El token tiene permiso mínimo
de lectura. La suite local amplía sus 88 casos a 103, todos aprobados.

La política de main requiere PR y check pytest actualizado, también para el administrador.
No requiere aprobación de una segunda cuenta, para evitar un bloqueo de revisión
propia en el laboratorio personal. No se inicializa DVC ni se crea entrega-lab1.
La confirmación del resultado de CI y protección se informa tras verificar GitHub.

## D039 — Diagnóstico del disparo de Actions

El repositorio público y PR #1 se crearon, las ramas se publicaron y la protección
de main se confirmó por API. Actions y el workflow figuran activos; se registraron
eventos opened/reopened del autor OWNER, pero inicialmente no aparecieron runs ni
checks. Se añadió workflow_dispatch para una prueba explícita, manteniendo todos
los eventos automáticos de PR y el mismo job pytest. No se debilita la protección
ni se interpreta la falta de CI como un resultado aprobado.

## D040 — CI remota aprobada y protección confirmada

La actualización del workflow disparó un run real pull_request:
https://github.com/vivianroca/corporacion_favorita/actions/runs/41177434432.
Su log confirma auditoría del historial, Ruff y 103 pruebas aprobadas en Ubuntu
24.04/Python 3.12.15, validando el lock también en Linux x64. La prueba local usa
Python 3.12.16 en ARM64. El diagnóstico manual también aprobó; el resultado de PR
se verificó de forma independiente. El problema inicial de disparo quedó resuelto.

Se vinculó el check requerido pytest a GitHub Actions (app ID 15368), con base
actualizada y aplicación a administradores. La API confirmó PR abierto, checks
SUCCESS y mergeStateStatus CLEAN, sin mergedAt ni autoMergeRequest. El usuario
conserva la decisión de revisar y fusionar. No hay un bloqueo de configuración
pendiente; DVC y entrega-lab1 siguen expresamente fuera de alcance.

## D041 — Rama DVC y dependencia fija

El usuario autoriza inicializar DVC, cinco originales y storage local. Git estaba
limpio en feature/ingesta-airflow. Se confirmó que el usuario ya había fusionado
el PR #1; se actualizó main por fast-forward y se creó feature/dvc desde ese estado.
No se realizó un merge de PR durante esta tarea. DVC no estaba instalado.

Se fijó DVC 3.67.1 en el extra dev de pyproject.toml y se regeneró el lock con hashes
bajo Python 3.12.16. Se instaló exclusivamente en lab1/.venv. El backend local no
requiere plugins cloud; no se instaló todavía dvc-s3.

## D042 — Inicialización Git y cachés separadas

Se usó dvc init con SCM Git, nunca --no-scm. Un primer intento falló por acceso a
la caché global de índices de Homebrew; se conservó el estado parcial en un respaldo
temporal y se completó init. Se fijó una caché de índices del workspace mediante
config.local, ignorado por Git. La caché de datos permanece en .dvc/cache y tampoco
se publica. La configuración compartida usa cache.type copy y analítica deshabilitada.

## D043 — Originales inmutables y excepciones limitadas de Git

Se agregaron con --no-relink únicamente train, stores, holidays_events, oil y
transactions. Suman 123.397.286 bytes. No se agregaron test ni sample_submission,
simulación o snapshots. Los cinco SHA-256 y mtime originales permanecen iguales.

Se revisaron .gitignore y los cinco punteros: Git solo admite esos metadatos bajo
data/original. Los padres deben ser transitables para que DVC descubra las etapas;
los comodines ?* evitan marcar como ignorado el padre con barra final. Se añadió
una prueba de regresión para ese recorrido y la exclusión de datos. La auditoría
valida YAML, MD5, tamaño y ruta de cada puntero; no acepta CSV renombrados ni otros
punteros de datos o configuración privada. La suite completa aprueba 120 casos.

## D044 — Remoto dedicado, push y recuperación real

Se configuró storage por defecto en ~/dvc-storage/corporacion_favorita, con tilde
portable en la configuración versionada. No se reutilizó almacenamiento de otro
proyecto. El push creó cinco objetos; MD5 y tamaños se comprobaron en el destino.
El estado cloud confirma sincronización.

El script verificar_recuperacion_dvc.py clonó el commit e0c6341 localmente sin datos
ni caché, ejecutó pull y recuperó cinco CSV idénticos por SHA-256. Originales y caché
principal conservaron contenido y mtime. El clon y su caché se dejaron disponibles
para inspección; no se eliminaron archivos para simular el fallo o la recuperación.

## D045 — Estrategia posterior y acceso docente

Se inventariaron 10.143 archivos/138.307.715 bytes únicos en la simulación; el hashing
local tardó 1,489 s, sin ejecutar dvc add sobre ella. No es un benchmark de DVC o nube.
Se propone un piloto por partición y punteros de directorio/generación inmutables,
no miles de sidecars ni un ZIP monolítico. Los snapshots cerrados sí muestran
contenidos repetidos y pueden aprovechar deduplicación. No se versionan bases vivas.

storage es un respaldo en esta máquina, no un remoto compartido con docentes.
Se recomienda S3/compatible con prefijo exclusivo y acceso docente de lectura;
el endpoint, plugin fijado y credenciales quedan pendientes de elección/autorización.
La documentación detallada está en docs/dvc.md. No se modifican DAGs ni se entrenan
modelos; no se fusionará el PR ni se creará entrega-lab1.

## D046 — Baseline semanal autorizado y evaluación temporal

Se autoriza únicamente un baseline puntual de siete días, independiente de Airflow
y DVC. Se implementa en src/reposicion/baseline.py: para cada tienda/familia utiliza
el mismo día de la semana previa. No ajusta hiperparámetros, usa covariables futuras
ni convierte ventas a enteros. Entregas o claves ausentes producen error, no ceros.

Se utiliza el catálogo simulado inmutable, porque los snapshots operativos actuales
no contienen una semana completa. La selección usa available_at <= issued_at y la
última revisión conocida. La verdad de evaluación se consulta después de construir
los pronósticos, con otro corte. La prueba sintética verifica que una corrección
posterior no sustituye la versión histórica conocida. El universo son las series
observadas en la semana de referencia; series nuevas requieren una política futura.

El origen elegido fue 2017-01-08: primera fecha comprobada a partir del día 8 con
semana completa disponible, sin seleccionar por métricas. Emisión 12:00Z de ese día;
evaluación al 2017-02-10T12:00Z. Se evaluaron 12.474 claves con cobertura idéntica.
MAE=230.35504495348724, WAPE=0.4854428315163875 (fracción), sin afirmar que una semana
represente el desempeño general. Para ventas reales todas cero, WAPE se declara
indefinido; no se sustituye por cero. Las fechas comerciales siguen Ecuador y no
alteran la zona del scheduler.

MLflow existente registró el run b9e248ac36984fa893ada7b81b375892 en el experimento
corporacion_favorita-baselines, FINISHED, con cinco artefactos comprobados por API.
Se usa REST con biblioteca estándar, sin cambiar dependencias ni requirements.lock.
Los artefactos locales permanecen en reports/ ignorado por Git. Se exige una carpeta
nueva por ejecución para evitar sobrescrituras; cada ejecución crea su propio run.
No se modifican originales, simulación, DAGs, servicios ni configuración DVC.

## D047 — Primer candidato Random Forest y comparación pareada

La autorización se amplía únicamente a RandomForestRegressor con horizonte siete,
sin modificar Airflow ni DVC ni asignar champion. Se mantiene el baseline existente
y se comprueban sus contratos, catálogo, predicciones, claves y reales por igualdad.
Ambos modelos evalúan 12.474 observaciones del 8–14 de enero de 2017, con emisión
2017-01-08T12:00Z y evaluación 2017-02-10T12:00Z.

Se entrena un modelo global con codificación de tienda/familia/calendario, horizonte,
rezagos 7/14/21/28 y promedio/conteo de los siete días anteriores al origen. Ocho
orígenes semanales anteriores reconstruyen las variables con su disponibilidad real
simulada a las 12Z de cada origen. Las etiquetas se seleccionan al corte final de
entrenamiento y siempre tienen fecha anterior al horizonte evaluado. No se usan
ventas del horizonte como variables, ni revisiones futuras, ni particiones aleatorias.

Los faltantes no se interpretan como ceros: NaN más indicadores y medianas ajustadas
solo con entrenamiento. Las columnas enteramente ausentes conservan una constante
junto al indicador. Se excluyen etiquetas inexistentes y se registra su cantidad:
1.782 del 25 de diciembre; quedan 98.010 filas. El universo de series sigue siendo
el conocido por el baseline. No hay ajuste de hiperparámetros contra la evaluación.
Parámetros: 64 árboles, profundidad 16, mínimo cinco muestras por hoja,
max_features=0.7, random_state=42 y n_jobs=2.

Se fijaron scikit-learn 1.9.1 y matplotlib 3.11.2; se resolvió requirements.lock con
hashes bajo Python 3.12.16 y se instaló en .venv. DVC permanece en 3.67.1; no se
modifica su configuración ni sus punteros. pip-tools necesitó acceso a su caché
fuera del sandbox y terminó correctamente. pip check no detectó incompatibilidades.

MLflow registró el run b9628a0e6bf94d2a878ffa2c82ed0fdd, experimento
corporacion_favorita-candidatos, FINISHED. MAE=191.13634188309385,
WAPE=0.40279459487483094 como fracción: reducción relativa 17.025328 % frente al
baseline. Se guardaron doce artefactos, incluyendo pipeline joblib, predicciones,
comparación, lock, trazabilidad y dos PNG; se descargaron y verificaron sus SHA-256.
El modelo queda como artefacto del run, sin promoverlo al registro ni crear aliases.

La suite completa aprueba 129 pruebas y Ruff/formato. El resultado representa una
semana y mantiene sobrepronóstico agregado varios días: no justifica aún promoción.
La implementación y comandos se documentan en docs/random_forest.md y README.md.

## D048 — System Metrics para los siguientes entrenamientos

Se autoriza preparar CPU, RAM y duración sin volver a entrenar los modelos existentes.
psutil 7.2.2 ya estaba en .venv como dependencia transitiva; ahora se fija explícitamente.
Se añade mlflow-skinny 3.17.2 para utilizar el monitor oficial de MLflow, y se actualiza
requirements.lock con hashes bajo Python 3.12. No se modifica Airflow ni DVC.

Antes el cliente REST creaba el run al finalizar el trabajo y no podía muestrear el
entrenamiento. Random Forest ahora utiliza training_run, que abre el run antes de
preparar las filas y usa log_system_metrics=True. Se muestrea cada segundo con una
muestra por publicación. La CPU y la memoria corresponden al host de ejecución,
no al proceso aislado ni al contenedor MLflow. Se documenta la posible ausencia de
muestras en trabajos inferiores al intervalo; no se inventan valores retrospectivos.

Se registra training_duration_seconds alrededor de model.fit y execution_duration_seconds
con reloj monotónico alrededor de preparación, ajuste, evaluación y subida de artefactos.
La duración total también se intenta registrar ante fallos; el contexto cierra el run
y restaura URI e intervalos. Se rechaza reutilizar un run activo. MAE, WAPE, predicciones,
modelo y gráficas se conservan. El baseline sin ajuste mantiene el cliente existente.

La comprobación se limita a tests aislados del ciclo de vida y al colector oficial
CPU/RAM en este entorno. No se ejecutan comandos de entrenamiento ni se crean runs
ficticios en el servidor. La verificación de series reales publicadas se realizará
en el siguiente entrenamiento autorizado. No se asigna champion ni se alteran métricas
históricas para simular que estuvieron instrumentadas.

Resultado de esta preparación: 134 pruebas aprobadas; Ruff, formato y pip check
correctos. El colector oficial de CPU/RAM funciona en .venv. Las consultas de ambos
runs existentes coinciden íntegramente con su estado anterior (parámetros, métricas,
tags y metadatos). No se ejecutó entrenamiento real ni se modificaron esos runs.

## D049 — HistGradientBoosting autorizado, System Metrics reales y Registry

Se autoriza un nuevo candidato HistGradientBoostingRegressor y su registro en Model
Registry, sin modificar Airflow ni DVC ni asignar champion. Se reutilizan las funciones
de variables, lecturas por disponibilidad y entrenamiento de Random Forest. Se exige
la misma trazabilidad de entrenamiento y las mismas claves y reales de evaluación.
No se reentrenan ni se modifican los runs anteriores.

Se fijaron antes del resultado: loss=poisson (ventas no negativas, sin redondeo),
learning_rate=0.08, max_iter=150, max_leaf_nodes=31, min_samples_leaf=20,
l2_regularization=1.0, max_bins=255, random_state=42 y early_stopping=False.
No se hace selección aleatoria interna ni búsqueda sobre el horizonte de evaluación.
La codificación e imputación coinciden exactamente con Random Forest. El pipeline
acepta DataFrame para poder usar el formato sklearn/pyfunc de MLflow y conservar
el preprocesamiento dentro del modelo registrado. Se limita fit/predict a dos hilos.

Se agregó pandas 3.1.0 para el formato MLflow, con lock y hashes bajo Python 3.12.
La primera prueba detectó que MLflow elegía skops por defecto; se fijó cloudpickle
explícitamente, ya instalado, y se comprobó la recuperación del modelo propio.
No fue necesario instalar skops ni cambiar infraestructura.

98.010 filas y ocho orígenes anteriores, emisión 2017-01-08T12:00Z y evaluación
2017-02-10T12:00Z. Las 12.474 observaciones del 8–14 de enero coinciden con los dos
modelos anteriores. MAE=207.9089128775264, WAPE=0.4381405728932026 como fracción.
Mejora al baseline, pero Random Forest sigue con menor error; no se reajustan los
parámetros tras observarlo ni se concluye desempeño general con una sola semana.

Run 39562417052c45bb8dece31675763d19, FINISHED. Se verificaron 16 muestras de CPU/RAM
del host, ajuste de 5.730457833000401 segundos y ejecución de 17.364074500001152.
Model Registry: corporacion_favorita_hist_gradient_boosting, versión 1, READY,
sin aliases. Se guardan artefactos y gráficas, y un MLflow Model con firma y ejemplo
de entrada, además de comparación con baseline y Random Forest.
La suite aprueba 137 pruebas; Ruff/formato y pip check correctos. Las advertencias
no bloqueantes de dependencias se documentan en docs/hist_gradient_boosting.md.

Verificación posterior: la versión 1 recuperada desde Registry reproduce las
12.474 predicciones por sklearn y pyfunc (tolerancia 1e-12). Los doce artefactos
del run conservan SHA-256 idénticos al descargarlos. Los dos runs anteriores
conservan íntegramente estado, parámetros, métricas, tags y metadatos.

## D050 — Walk-forward real de cuatro cortes, sin selección de Champion

Se autoriza reentrenar los candidatos ML por corte para validación, ampliando la
restricción anterior de no reentrenamiento. Se crean resultados y runs nuevos sin
sobrescribir los históricos. Configuración externa en configs/walk_forward.yaml;
lógica independiente en src/reposicion/walk_forward.py, sin modificar Airflow o DVC.

Se eligen los domingos 8, 15, 22 y 29 de enero de 2017 a las 12Z, para mantener el
origen previo y cuatro cortes semanales de enero; el último horizonte termina el
4 de febrero. Los cuatro tienen la historia semanal disponible que exige el baseline.
No se omiten ventanas ni se imputan ceros para lograr comparación. Se conserva un
universo de 1.782 series, 12.474 filas por ventana y 49.896 por modelo.

Se usa ventana móvil (rolling), no expansiva: ocho semanas de etiquetas conocidas
al corte, como en los candidatos anteriores. Los inicios ML son 2016-11-13,
2016-11-20, 2016-11-27 y 2016-12-04; fines 2017-01-07, 14, 21 y 28. Cada corte
mantiene 98.010 etiquetas, excluyendo 1.782 inexistentes del 25 de diciembre.
Se reconstruyen variables con revisiones disponibles en cada origen histórico.
Ambos candidatos comparten filas y etiquetas, verificables por SHA-256; se ajustan
ocho pipelines nuevos sin warm start ni búsqueda de hiperparámetros. El baseline
no ajusta parámetros y utiliza solo la última semana conocida.

La verdad de evaluación se consulta con desfase fijo de 33 días desde cada emisión:
10, 17 y 24 de febrero y 3 de marzo a las 12Z. Es una elección de evaluación para
conservar la maduración del primer experimento, no un SLA inferido de los CSV.
Los reales se leen después de predecir para cada modelo y nunca entran al ajuste.
La igualdad de fechas/claves/reales se exige para los tres modelos por ventana.

El agregado MAE usa error total dividido por número de filas; WAPE usa error total
dividido por ventas totales, no media de WAPE. Se publican además media y desvío
poblacional de cada métrica por ventana. Un WAPE indefinido no se sustituye por cero.
La prueba sintética comprueba ocho instancias nuevas, cortes de disponibilidad,
igualdad de muestras, ventanas semanales, agregación ponderada y ceros/duplicados.

Ejecución real 107d7f6f8961472b8fdf46647ed4f224, experimento MLflow 3:
12 runs modelo/ventana y tres agregados, todos FINISHED. MAE/WAPE globales:
baseline 107.0769410822611 / 0.22470658133215438;
Random Forest 112.48541399213852 / 0.23605654562439596;
HistGradientBoosting 130.97906021517966 / 0.2748664329553512.
Las fracciones WAPE se muestran como porcentajes en README y docs/walk_forward.md.

Cada run de ventana guarda predicciones, evaluación, gráficos y trazabilidad; los
ML además su pipeline, métricas de duración y System Metrics del host. No se generan
versiones de Registry para estos ajustes de validación ni se promueve un candidato.
La suite completa aprueba 142 pruebas y Ruff/formato. No cambian dependencias.

Verificación final: 15 runs FINISHED, métricas idénticas a archivos locales, CPU/RAM
y duración en los ocho entrenamientos ML. Se descargaron 116 artefactos con SHA-256
idénticos. Los tres runs previos y todas las versiones/aliases de Registry conservan
su estado anterior. La auditoría de publicación pasa y Git confirma ausencia de
cambios en DAGs, Docker, configuración DVC y punteros de originales.

## D051 — Variables temporales v2, sin alterar baseline ni hiperparámetros

Se autoriza incorporar calendario conocido e indicadores de rezagos excepcionales,
y eliminar imputación global que mezcla familias. La extensión opcional del runner
mantiene reproducible la ruta v1; la nueva entrada temporal_walk_forward usa un
experimento independiente. No se toca el código del baseline ni los parámetros de
RF/HGB, y no se amplía el entrenamiento ni se modifican cortes o evaluación.

Se seleccionan por disponibilidad y revisión los recibos de holidays_events y stores
para cada origen histórico y de pronóstico. National aplica a todas las tiendas;
Regional al estado y Local a la ciudad. Se distinguen feriado activo, traslado,
Work Day y Event. transferred=True conserva contexto excepcional pero no se marca
feriado activo. No se infieren cierres reales de tienda ni se inventa conocimiento
anticipado de eventos. El simulador entrega por fecha: cuando mezcla planificados e
inesperados, se respeta la publicación conservadora de todo el recibo. Sin registro
solo significa sin evento conocido, no certeza de día ordinario.

Se mantienen rezagos observados y flags de ausencia; se agregan flags de cero real
y contexto excepcional, mediana de rezagos semanales ordinarios y promedio reciente
sin eventos conocidos con sus conteos. Las nuevas referencias usan exclusivamente
ventas anteriores al origen y calendario conocido entonces. Los ceros no se borran.

SeriesFamilyImputer sustituye SimpleImputer global únicamente en v2. Primero usa
rezagos comparables conocidos de la misma serie para rellenar un rezago ausente;
luego medianas de columna por serie/familia ajustadas en entrenamiento; después
respaldo de la misma familia. Si no hay historia válida, aborta. Nunca mezcla familias,
no ajusta estadísticas con validación y excluye rezagos excepcionales de las medianas
de relleno. Los flags originales de ausencia se conservan después de imputar.

Pruebas: alcance territorial, traslado, eventos aún no publicados, ceros/ausencias,
escalas de familias, igualdad exacta de hiperparámetros y recorridos completos v1/v2.
149 pruebas aprobadas y Ruff/formato correctos. No se añaden dependencias.

Resultado real: grupo 38f20499009a405da5231d65382aed8d, experimento MLflow 4,
corporacion_favorita-walk-forward-temporal-v2. Sobre 49.896 registros por modelo:
baseline MAE=107.0769410822611, WAPE=0.22470658133215438;
RF v2 MAE=90.5625721282446, WAPE=0.19005031124255538;
HGB v2 MAE=102.02235699583552, WAPE=0.21409927131155868.
Los tres modelos mantienen las mismas cuatro ventanas y las 98.010 etiquetas por
ajuste ML. El baseline reproduce exactamente sus predicciones y reales anteriores.

Se publican runs y artefactos nuevos, sin sobrescribir v1 ni crear aliases o versiones
de Registry para validación. No se selecciona Champion. Los resultados corresponden
al paquete de nuevas variables e imputación, no a una ablación de efectos individuales.
Como enero se inspeccionó para diseñar las variables, la comparación es de desarrollo;
queda pendiente un período independiente para estimar generalización sin selección.

Verificación posterior: 15 runs nuevos FINISHED, System Metrics en los ocho ajustes,
72 contextos de calendario sin recibos posteriores al corte, 116 artefactos con
SHA-256 idénticos al descargarlos. Los ocho estimadores persistidos conservan sus
hiperparámetros v1. Se comprobó igualdad íntegra de los 18 runs anteriores y Registry,
y hash idéntico del código baseline. Sus archivos forecast/evaluation coinciden
byte a byte en los cuatro cortes. Auditoría de publicación aprobada.

## D052 — CatBoost inicial con cuatro folds y variables temporales v2

Se autoriza CatBoostRegressor sin optimización ni Champion. Se añade catboost 1.2.10
con wheel cp312 macOS universal2, fijado en pyproject y requirements.lock generado
bajo Python 3.12; se instala únicamente en .venv. Sus dependencias graphviz y plotly
quedan bloqueadas; no se requiere ejecutar Graphviz ni instalar herramientas globales.
La generación de hashes terminó correctamente tras descargar/resolver dependencias.

Se conserva configs/walk_forward.yaml y la variante temporal v2: disponibilidad,
calendario por alcance, indicadores de ausencia/cero/excepción y relleno por serie
con respaldo exclusivo de la misma familia. La primera versión utiliza DictVectorizer
igual a RF/HGB, sin introducir además codificación categórica nativa. Se exige igual
huella de filas/etiquetas, trazabilidad, calendario, cortes y claves/reales evaluados.
Los 98.010 ejemplos por fold y 49.896 registros evaluados coinciden con v2.

Parámetros fijados antes de medir: 300 iteraciones, profundidad 6, learning_rate=0.05,
RMSE con métrica MAE, semilla 42, CPU, dos hilos de ajuste, boosting_type Plain,
has_time True, use_best_model False y allow_writing_files False. No hay eval_set,
early stopping, búsqueda ni selección de iteración. Los defaults resueltos se guardan
con get_all_params. Se mantienen las etiquetas fraccionarias; la predicción aplica
piso cero fijo, guardado dentro del pipeline, sin elegir ese piso por validación.
El CBM contiene el estimador crudo y requiere el preprocesamiento y ese piso.

Se crean cinco runs nuevos en corporacion_favorita-catboost-temporal-v2, experimento 5,
grupo f34f181e5d82463db7c2aba64ce572d9: cuatro folds y agregado micro/macro.
MAE global=92.13316590687047, WAPE=0.19334628472750431 como fracción.
Por fold MAE/WAPE: 130.75032781366866 / 0.2755390461206494;
93.46232316370083 / 0.1963012306306949;
63.84011581900496 / 0.13999281546031304;
80.47989683110742 / 0.1611502476797976.
Hay 9.473 predicciones crudas negativas en total; los pronósticos evaluados aplican
el piso cero y la métrica registra sus cantidades por fold de forma transparente.

Se guardan pipeline joblib, CBM, parámetros, importancias, predicciones, evaluación,
lock, gráficos y trazabilidad; CPU/RAM y duración se registran en cada ajuste.
Una verificación entre procesos detectó que la clase definida en la CLI se serializaba
bajo __main__. Se movió a catboost_model.py, se agregó una prueba de regresión y se
volvieron a guardar los estados ya ajustados, sin repetir entrenamientos ni alterar
los CBM originales, métricas o predicciones. La corrección se marca en los cuatro
runs propios y su lineage. No se modifican runs anteriores al inicio de esta tarea.

Verificación final: cinco runs FINISHED, 300 árboles por fold y sin evaluación interna.
Se recuperan las 49.896 predicciones desde joblib y CBM con preprocesamiento/piso,
tolerancia 1e-12. Las medianas y columnas codificadas coinciden con RF v2. Se descargan
59 artefactos con SHA-256 idénticos. Los 33 runs previos, versiones/aliases de Registry
y código baseline conservan su estado. No se modifican Airflow, DVC ni originales.
154 pruebas aprobadas; Ruff/formato y pip check correctos. Los resultados son de
comparación de desarrollo sobre enero ya inspeccionado, no evaluación final inédita.

## D053 — Registro de modelos ya ajustados, sin nuevos entrenamientos

El usuario autoriza publicar los modelos existentes en Models de MLflow y recalca
que no se vuelvan a entrenar. Se publican los doce pipelines temporales v2 de los
cuatro folds: RF versiones 1–4, HGB versiones 2–5 y CatBoost versiones 1–4. Se conserva
HGB versión 1 y su Logged Model del experimento anterior. La autorización de registro
actual amplía la decisión previa de mantener los ajustes de validación solo como
artefactos. No implica selección de Champion ni promoción de ninguna versión.

register_models.py carga los estados joblib existentes y reconstruye únicamente las
entradas de inferencia conocidas al corte para verificar sus predicciones. No contiene
llamadas a fit ni crea runs de entrenamiento. Se empaqueta el pipeline completo con
firma, ejemplo, código y dependencias, formato sklearn/pyfunc mediante cloudpickle.
Se crean Logged Models vinculados a los runs de origen, se publican sus artefactos
y se crean versiones de Registered Models apuntando a esos modelos, todos READY.

Para mostrar MAE/WAPE en Logged Models se reutiliza el mismo evento histórico
(valor/timestamp/step) con model_id. El backend MLflow 3.17.2 deduplica los eventos
del run, hecho verificado comparando sus historiales antes/después. Se agregan las
asociaciones de modelos a outputs de sus runs sin modificar info, parámetros, tags,
valores o historiales de métricas. Los resultados globales siguen en runs agregados;
las versiones muestran las métricas de su propio fold, sin confundir ambos niveles.

Se verifica por pyfunc la recuperación de las doce versiones y sus 12.474 predicciones
por modelo, tolerancia 1e-12, además de estados READY y métricas asociadas. Se conservan
38 runs, sus metadatos/datos e historiales, y la versión 1 anterior de HGB. El script se
repitió sin crear duplicados. El mapa local registrations.json está ignorado por Git.
No hubo nuevos entrenamientos, hiperparámetros, dependencias, aliases o stages de
promoción. No se modifican Airflow ni DVC. Ruff y formato pasan; la comprobación de
esta tarea se realiza exclusivamente con carga/inferencia y lectura de metadatos.

## D054 — Separación en commits, ramas y tags Git autorizados

El usuario autoriza publicar el código pendiente por ramas y aclara que las etiquetas
son tags de Git, sin comentarios añadidos a archivos de modelos. Se respalda primero
el trabajo y se separa en siete etapas acumulativas, documentadas en
docs/publicacion_modelos.md. El lock compartido se versiona desde Random Forest;
no se generan locks con otro intérprete ni se modifican datos o pesos entrenados.

Cada etapa se valida, se audita y recibe un tag anotado lab1-*. Se prepara un PR
conjunto feature/modelos-pronostico hacia main. No se hace merge, no se crea
entrega-lab1 y no se selecciona Champion. Se conserva la exclusión de secretos,
CSV, simulaciones, snapshots, modelos, predicciones y almacenamiento Docker.

## D055 — Solo doce pipelines y cuatro CBM en DVC

El usuario autoriza exclusivamente los doce pipelines actuales de los cuatro folds
(RF/HGB temporales v2 y CatBoost) y los cuatro nativos CatBoost. Excluye simulación,
snapshots y modelos históricos; tampoco se añaden métricas, parámetros, predicciones,
gráficas o paquetes de Registry al conjunto DVC. No se entrena ni deserializa un modelo.

Se crea feature/dvc-modelos-actuales desde main actualizado, que ya contiene el PR #3
fusionado por el usuario. Los pesos se copian sin modificar sus fuentes en reports,
agrupados en models/current. Un único puntero models/current.dvc representa exactamente
16 binarios y 35.544.890 bytes. Se conserva el remoto storage dedicado del laboratorio,
cache.type copy y --no-relink; no se regenera la simulación ni se toca el entorno externo.

El push agregó 17 objetos: 16 pesos y el índice 6758afd54f231ee0e194603f381b7567.dir.
El estado cloud confirma sincronización. Se recuperaron en un clon sin pesos/caché,
mediante pull explícito de ese único puntero. Coinciden los 16 SHA-256 y tamaños.
No se borraron cachés, los modelos locales/cache principal no cambiaron al recuperar,
y los 16 archivos fuente de reports y cinco CSV conservan contenido y mtime.

La exclusión Git mantiene transitables los padres para descubrir el nuevo puntero,
pero no expone binarios. La auditoría permite solo models/current.dvc, con índice de
directorio, destino current y nfiles=16; rechaza otros punteros y se añade defensa
explícita para .cbm. Cuarenta pruebas de auditoría/exclusiones pasan sin fit, con
Ruff/formato correctos. El informe de recuperación local queda ignorado por Git/DVC.

No cambian versiones de MLflow, aliases, pesos o hiperparámetros. El remoto local
no habilita acceso docente externo; permanece pendiente un remoto compartido.

## D056 — Comparación a partir de runs existentes

Se crea `comparacion_modelos` (experimento 6) con cuatro runs nuevos FINISHED,
comparison_id=49b104b634f8472f8b4ae2675ad4bada. Fuentes explícitas: baseline/RF/HGB
del grupo temporal v2 38f20499009a405da5231d65382aed8d y CatBoost del grupo
f34f181e5d82463db7c2aba64ce572d9. No se mezclan candidatos históricos v1.
Se copian las métricas originales, validando cuatro ventanas idénticas, horizonte
siete días, emisión/evaluación, cobertura y denominadores ponderados globales.

Cada run registra 14 artefactos: tablas global/por fold/completa, normalización,
informe Markdown, fuentes JSON, configuración y tres gráficas PNG/SVG.
Se verificaron por hash los 56 archivos descargados y por igualdad las métricas
globales y de los 16 folds. Los 38 runs previos y Registry (versiones/aliases)
conservan exactamente sus metadatos anteriores. No se entrenó, cargó ni registró
ningún modelo ni se asignó Champion. Siete pruebas numéricas pasan sin fit.

El radar normaliza por el mínimo de cada eje; si es cero, asigna 1 a errores cero
y 0 a los positivos. MAE/WAPE son proporcionales con la cobertura compartida:
se documenta su redundancia, sin interpretar sus perfiles como evidencia doble.
La comparación refleja ventanas de desarrollo, no una evaluación final nueva.
Los artefactos permanecen fuera de Git y no se modifica DVC ni Airflow.
Matplotlib emitió avisos de caché Fontconfig no escribible durante la primera
creación; generó correctamente los seis gráficos y se inspeccionó el radar.

## D057 — Alias champion de Random Forest existente

El usuario autoriza explícitamente promover Random Forest sin reentrenar.
Se asignó `champion` a corporacion_favorita_random_forest versión 4 READY,
el fold con corte más reciente, no el fold con menor error individual.
Run fuente f6062df6a53549a79125fd208aab381d; entrenamiento termina 2017-01-28.
Se conserva validation_only=true: sigue siendo un modelo del walk-forward,
no un ajuste nuevo a toda la historia ni evidencia de validación independiente.

Tags de versión vinculan el run agregado 517dc691cef148ae8959e73e9419cded,
comparación c33f236952034629ae3e235ab1d4da0e, models/current.dvc, ruta fold_4,
commit 09fd79b700d11c50e25ccba5c31287f4152a489f y directorio DVC
6758afd54f231ee0e194603f381b7567.dir. SHA-256 del pipeline:
bb71d5bf8116b80c8b1fb409b7420a514b2dae90e93e87d064f6235e178583ef.
Coincide con metadata.trained_pipeline_sha256 del MLmodel registrado y el MD5
coincide con el índice de directorio DVC, cuyo hash también se verificó.
La consulta por alias resuelve versión 4/run correcto; el run original conserva
exactamente su contenido previo. Registro local reports/champion/random_forest_v4.json.
No se crearon versiones ni runs, no se entrenó/deserializó ningún modelo y no
se modificaron pesos, otros aliases, Airflow o DVC. Sin commits/publicación Git.

## D058 — Incertidumbre empírica del Champion sin reentrenar

Se implementa reposicion.uncertainty: resuelve champion a versión inmutable,
carga el pyfunc existente y utiliza errores firmados actual-prediction de los
folds RF del mismo grupo temporal v2, descargados directamente de MLflow.
Solo acepta períodos anteriores al origen y evaluated_at <= issued_at. Rechaza
Champion con entrenamiento/evaluación posteriores al corte. La política usa
fechas históricas simuladas, no timestamps de creación física de MLflow en 2026.

Calibración por familia y horizonte, agrupando tiendas de la misma familia;
mínimo 30 residuos, sin fallback global entre familias. Cuantiles empíricos
lineales 0.1/0.5/0.9 sumados a la predicción puntual y truncados a cero. P50
corrige el sesgo mediano, no se identifica la media del bosque con la mediana.
Se garantiza orden, pero no cobertura nominal: no es intervalo conformal ni
validación independiente; hay solo cuatro ventanas y posible deriva temporal.

Ejemplo: emisión 2017-03-05T12:00:00Z, horizonte 5–11 marzo 2017, después de la
última evaluación disponible el 3 de marzo. Champion versión 4, mismo run/puntero
DVC documentados en D057. Se guardan 12.474 filas únicas para 1.782 series en
reports/uncertainty/2017-03-05-v2/forecast_quantiles.csv y lineage.json, con
versión/run/tags DVC, hashes de evaluations y entregas/calendario seleccionados
por disponibilidad. Se mantienen originales y resultados anteriores intactos.

Dos pruebas pytest sin fit pasan; verificación completa de salida confirma
cuantiles finitos, no negativos, ordenados y calibración suficiente. Primera
ejecución falló por directorio de descarga inexistente; se corrigió y se usó un
directorio nuevo sin sobrescribir el intento. No se entrenan modelos ni se
modifican Airflow, DVC o metadatos/runs/aliases de MLflow; sin operaciones Git.

Comando reproducible (destino nuevo):
.venv/bin/python -m reposicion.uncertainty --origin 2017-03-05 --issued-at
2017-03-05T12:00:00Z --output reports/uncertainty/OTRA_EJECUCION

## D059 — DAG semanal de inferencia y publicación sobre snapshots

Se autoriza lab1_pronostico_reposicion en Airflow 3.3.2 sin reentrenar ni modificar
lab1_ingesta_temporal. Cron configurable 0 6 * * 0, America/Guatemala,
catchup=False, max_active_runs=1. El corte automático es data_interval_end; el
backfill fija origin/issued_at/snapshot_id y opcionalmente model_version.

La lógica de inferencia reutiliza uncertainty mediante inyección de catálogo de
snapshot, contrato y versión fijada. SnapshotCatalog consume exclusivamente CSV
validados con checksums/recibos, as_of <= corte, validación histórica vinculada
y 28 fechas de historia. No filtra snapshots posteriores para fingir un as-of.
Mantiene ceros/ausencias y rechaza historia incompleta, contratos incompatibles
o selección ambigua. No modifica snapshots, bandeja ni originales.

Publicaciones independientes por identidad: corte/origen, snapshot/hash, código,
contrato, versión/run/source MLflow y calibración/hashes. Lock de archivo, stage
privado y rename atómico aseguran recuperación e idempotencia; una revisión
produce otra identidad. Un retry verifica el bundle antes de reutilizarlo.
Se conserva linaje del Champion/DVC/Git y de todas las entregas seleccionadas.
No se modifica el alias, pesos ni se crean runs de entrenamiento.

Se extendió la imagen local desplegada lab1-airflow:3.3.2, agregando solo el nuevo
DAG/proyecto y un venv de inferencia. Se conserva sin reconstruir su DAG de ingesta
(hash desplegado antes/después acfe21b2596ec5be86c749d76259d8d97d67bf655bc59e35dbfb2836c5b92842).
El archivo local dags/lab1_ingesta_temporal.py también conserva su contenido previo.
Se recrearon únicamente API/scheduler/dag-processor con la imagen nueva y los
volúmenes existentes. PostgreSQL/MLflow no se recrearon. El overlay es
 docker/compose.forecast.yaml; debe mantenerse en futuros comandos Compose.

Las dependencias del venv se aislaron de Airflow: 52 paquetes con versiones/hashes
extraídos del lock existente Python 3.12 y cierre Linux sin extras. La resolución
pip-compile por red no completó; se conservó el lock existente, sin inventar nuevas
versiones. La instalación Linux --require-hashes y pip check fueron correctos.
No se instalaron paquetes globales ni se usó otro proyecto.

Prueba real: el DAG de ingesta existente generó el snapshot
645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0 mediante
pronostico_snapshot_20170305 (success), corte 2017-03-05T12:00Z y referencias
2017-02-05 a 2017-03-11. No se regeneraron entregas ni se modificó su DAG.
El nuevo DAG ejecutó prueba_pronostico_20170305 y
prueba_pronostico_20170305_reintento: ambos success. El segundo devolvió reused=True.
Existe una única publicación 9d1027c938284a2604b84a0ff2b2ae17e9ec3035d4c5fb793b46cc6d93873594,
con 12.474 claves únicas, 1.782 series, 5–11 marzo, cuantiles no negativos ordenados.
SHA256 forecast=64c2375c90fac0298a964e425148d40b988fbd09c57de5a9908950a116f14d8d,
conservado después del reintento; todos los archivos coinciden con el manifiesto.

DAG habilitado, sin errores de importación; cron/zona/catchup comprobados en runtime.
Seis pruebas específicas sin fit, Ruff y formato correctos. El scheduler produjo
también scheduled__2026-10-25T12:00:00+00:00: failed, sin publicación, al faltar
historia de 2026. Esa limitación de datos permanece explícita: para operación
semanal real se requieren snapshots recientes; para simulación usar backfill.
No se ejecutan operaciones Git ni cambios DVC. Detalles en docs/pronostico_airflow.md.

## D060 — Día de emisión local y backfill manual coherente

El run manual__2026-11-01T00:27:05.358292+00:00 tenía conf vacía. El DAG derivaba
origin en Guatemala mientras forecast_publication y uncertainty comparaban con
fecha UTC: una emisión a medianoche UTC corresponde al día anterior local y
fallaba con Origen incompatible con emisión. Se centraliza validate_origin en
forecast_time.py usando America/Guatemala y timestamps con zona obligatoria.
Se mantiene rechazo de fechas realmente incompatibles.

Un manual sin origen/emisión usa el as_of del último snapshot validado con
historia suficiente en su propio corte; snapshots parciales no se eligen y los
corruptos fallan. Si se especifica snapshot_id, la selección queda fijada.
La fecha/intervalo del run solo es límite de descubrimiento, con logical_date o
ahora como fallback cuando el trigger CLI no tiene intervalo. No se introduce
esa fecha actual en la inferencia. Con solo origin, se usa 06:00 Guatemala de ese
día. Un scheduled conserva estrictamente data_interval_end: no se retrocede su
corte silenciosamente para evitar errores de disponibilidad.

No se relajan los controles: snapshot <= emisión, recibos disponibles, historia
previa al origen, Champion entrenado/evaluado antes del corte, residuos evaluados
y períodos terminados antes del origen. Datos 2013–2017 no permiten simular con
el Champion actual orígenes anteriores a su entrenamiento/evaluación de 2017.
No hay reentrenamiento, modificación de ingesta, de pesos, de DVC ni operaciones Git.

Se desplegó la imagen corregida conservando la base local y volúmenes. Hash del
DAG de ingesta desplegado sigue acfe21b2596ec5be86c749d76259d8d97d67bf655bc59e35dbfb2836c5b92842;
el archivo local tampoco cambia (7a401ee866fbda4e47063a51c2488a7b6e983aa7c417589a43ca65b757dd6bd8).

Pruebas reales: correccion_historica_20170305_utc success, origin=2017-03-05,
issued_at=2017-03-06T00:30:00Z (fecha local 5 marzo); publicación
55cd6e960a20f1c29f1de57c2380fdfc12b1dccb4bc055305a554cc7b362028c.
correccion_manual_sin_conf success, corte efectivo del snapshot 2017-03-05T12:00Z;
publicación de2ddbae6c7f48e932d7b2260f1eb2e1491ba46529da7ed4f45898d4ccf1f77e.
Ambos usan snapshot 645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0,
Champion v4, 12.474 pronósticos para 5–11 marzo. Se verifican hashes del bundle y
0 <= P10 <= P50 <= P90 en todas las filas. Diez pruebas específicas aprobadas,
Ruff/formato correctos y sin errores de importación. Runs fallidos previos no se
borran. Informe local reports/uncertainty/correccion_fechas_resultados.json.

## D061 — Seguimiento diario de predicciones inmutables

Se implementa lab1_seguimiento, cron 0 8 * * *, America/Guatemala,
catchup=False, max_active_runs=1; configuración externa seguimiento.yaml.
Solo orquesta reposicion.monitoring en el venv de inferencia existente.
MAE/WAPE sobre P50 y cobertura inclusiva P10–P90 sobre pares observados; se
registran completitud y pendientes separadamente. No se evalúan días abiertos,
no se imputan ausencias con cero y WAPE indefinido se omite. Sin pares observados
se persiste estado pendiente, sin fabricar métricas ni runs MLflow.

Se leen exclusivamente snapshots de ingesta con as_of <= evaluación y recibos
conocidos. Por defecto se combinan las últimas revisiones por fecha entre
snapshots completos/incrementales: un snapshot reciente parcial no hace olvidar
verdad anterior. Una corrección reemplaza toda su partición; una fila eliminada
no se rellena desde una revisión vieja. Misma revisión con distinto payload
falla. snapshot_id fija replay de un único snapshot. Se validan hashes, contrato,
claves y vínculo a validación. No se leen originales ni se modifica la bandeja.

La identidad usa publicación/hash originales, recibos y verdad efectiva, contrato
y código. Un nuevo corte sin cambios reutiliza resultado/run; datos tardíos y
correcciones producen una evaluación nueva. Locks y rename atómico existentes
protegen publicación local. MLflow busca por evaluation_id, recupera el run y
completa solo metadatos, métricas o artefactos faltantes, validando los existentes.
Se conservan los originales y evaluaciones anteriores. Registro en experimento
corporacion_favorita-seguimiento (8) con cuatro artefactos por evaluación y
referencias al modelo/run/version/DVC y snapshots/recibos de verdad.

Se ejecutó la ingesta existente, sin modificarla, con seguimiento_reales_20170402,
corte 2017-04-02T12:00Z, referencias 5–11 marzo, creando snapshot
1a87a6e7b4ec739577325d6a0b7eb2cf6b58ce23f47e8d5b5daec4636856257e.
La imagen agrega únicamente el tercer DAG/módulo/configuración sin nuevas
dependencias; se recrean solo procesos Airflow, con PostgreSQL/MLflow y volúmenes
conservados. Hash ingesta acfe21b2596ec5be86c749d76259d8d97d67bf655bc59e35dbfb2836c5b92842,
pronóstico a6fd38839c8f42786341d261fd85d6d0a8f3db125e916ef4bdd3bfa4f80e403b,
ambos iguales antes/después. Los archivos locales de esos DAGs tampoco cambian.

Pruebas históricas finales seguimiento_historico_final_20170402 y
seguimiento_historico_final_reintento: success; el segundo retorna reused=True.
Evaluación d45e9e65afa0067c0f1326d7a4cdfcd6916950c50ca53150f41dd832f6d700a6,
run MLflow 683aca87742145d48322ad3f04b353c6 FINISHED. Se evaluaron 12.474 filas
(100 %, cero pendientes), pronóstico 5–11 marzo del Champion v4:
MAE P50 77.26379684508039; WAPE 0.16173741413512321;
cobertura P10–P90 0.8002244668911336. Se comprobaron artefactos remotos y unicidad
del run por evaluación. Todas las publicaciones originales conservan sus hashes.

Nueve pruebas específicas pasan sin cargar/entrenar modelos. Cubren ceros/ausencias,
WAPE indefinido, cobertura, retrasos/correcciones, días futuros, duplicados,
composición/reemplazo de particiones, salida JSON y publicación idempotente.
Ruff/formato correctos y sin errores de importación. Un mensaje stdout del SDK
provocó reintentos en las primeras pruebas: se corrigió redirigiendo stdout del
SDK a stderr, con prueba de regresión. Las ejecuciones finales pasaron al primer
intento y se conserva el historial previo. No se reentrena, no se cambia Champion,
DVC ni se realizan operaciones Git. Detalles en docs/seguimiento_airflow.md.

## D062 — Dependencias nativas por Assets y cron semanal independiente

Se autoriza modificar exclusivamente la orquestación de los tres DAGs. Se agregan
orchestration.py (metadatos/preflight/catálogo inicial) y airflow_dependencies.py
(Assets/aliases) sin editar módulos de negocio, contratos, métricas ni modelos.
DAG 1 mantiene su programación desplegada cada tres horas y Guatemala; se alinea
el archivo local con esa configuración antes de añadir eventos. Alias condicionales
publican snapshots verificados y ventas cerradas relevantes para pronósticos;
publication_id=None no emite eventos. Replays manuales pueden volver a notificar
una publicación válida: entrega al menos una vez, consumo idempotente.

DAG 2 conserva cron semanal puro 0 6 * * 0, sin AssetOrTimeSchedule. Un sensor
nativo reschedule exige snapshot válido al corte y un evento exitoso de ingesta
con ID/hash exactos. Fija su entrada en XCom y llama al módulo existente. La última
tarea verifica el bundle y confirma el Asset de pronóstico. Fallos anteriores no
emiten ese Asset. Un archivo escrito sin confirmación no autoriza seguimiento.

DAG 3 usa FORECASTS | SALES, no AND: puede evaluar históricos aun cuando el
pronóstico actual falle. Por defecto se activa solo por Assets; cron diario
configurable queda como reconciliación opcional, daily_reconciliation=false.
Usa cortes de negocio de eventos y máximo conocido de eventos de ventas para
permitir evaluar pronósticos históricos recién confirmados. Un as_of explícito
siempre tiene prioridad, sin extenderse al watermark de eventos posteriores.

Se migra una sola vez el catálogo de tres publicaciones previas válidas en
operational/orchestration/legacy_forecasts.json, sin modificar sus bytes. Nuevas
publicaciones requieren eventos nativos exitosos y hashes coincidentes; no se
añaden automáticamente por descubrir archivos. El catálogo y los eventos de
MLflow/Assets persisten en volúmenes de lab1. Sin nueva dependencia Python, cambios
DVC ni operaciones Git. PostgreSQL/MLflow y volúmenes conservados; se recrean solo
los tres procesos Airflow con imagen construida desde la base local.

Pruebas reales: assets_snapshot_20170305 (success, evento 1),
assets_ventas_20170402 (success, eventos 2/3), assets_pronostico_20170305
(success, evento 4) y assets_ventas_despues_fallo (success, eventos 5/6).
Native scheduler creó tres DAG Runs de seguimiento success, consumiendo
respectivamente eventos 3, 4 y 6. El tercero reutiliza cuatro evaluaciones con
reused=True, sin nuevos eventos métricos ni runs MLflow. Sourceforecast autorizado
nuevo c677c4335f149a7b2b95c3687d9c7ae5e498ae226f4dd81049f980a1d6f42958,
12.474 filas, horizonte 5–11 marzo 2017 y Champion v4 existente. MLflow eval run
52ecf01dc1b3461d9de95390365046d0. Cortes emitidos marzo/abril 2017, separados de
los timestamps físicos de ejecución de noviembre 2026.

assets_pronostico_fallo_controlado usa versión inexistente 999999: failed esperado,
cero eventos y cero activaciones adicionales. Se verificó antes de volver a
notificar ventas; después seguimiento histórico volvió a funcionar sin depender
de ese fallo. assets_sondeo_sin_novedades: success, cero entregas y cero Assets.
La primera solicitud de ese sondeo usó una logical_date ocupada y no creó un run;
se reintentó con fecha única sin borrar ni alterar el run previo.

Se verifica cron semanal en runtime, sensor reschedule y cero DAG Runs de
pronóstico disparados por Assets. Todos los módulos de negocio ya presentes en
la publicación previa conservan sus hashes. Los tres pronósticos históricos
conservan bytes; la inferencia nueva difiere numéricamente a lo sumo 3.64e-12,
dentro de tolerancia verificada, sin cambiar pesos/código. No se interpreta esa
comparación flotante como igualdad de bytes; idempotencia usa la publicación
inmutable existente. Doce pruebas específicas sin entrenamiento pasan y no hay
errores de importación. Detalles y pruebas en docs/dependencias_assets.md e informe
local ignorado reports/assets/verificacion.json. El fallo controlado se conserva.

## D063 — Pedidos por costos sobre escenarios conjuntos, sin tocar modelos/Airflow

Se autoriza un motor independiente reposicion.orders que reutiliza cuantiles
existentes. No se ejecutan modelos ni se calculan nuevamente pronósticos.
configs/costs.yaml deja de ser borrador: faltante=5, merma=1, unidad monetaria
abstracta, plazo=2 días y horizonte de siete desde emisión. Son valores ilustrativos,
no estimaciones de costos/inventario real. Inventario inicial/entradas=0 por defecto,
con overrides por tienda/familia conocidos al corte; ventas perdidas, sin backorders,
entradas en la fecha de llegada y 100 % del remanente tratado como merma al cierre.
Cantidades continuas preservan ventas fraccionarias; múltiplos opcionales se eligen
comparando costo empírico, sin imponer redondeo hacia arriba.

La llegada al inicio del día L+1 cubre únicamente los 7-L días restantes; no se
extrapola a L+7 días sin pronósticos. El inventario disponible a la llegada se
calcula por escenario tras consumir la demanda previa, sin descontarlo dos veces.
El faltante previo inevitable se reporta y se incluye como costo fijo del escenario.
Se minimiza costo marginal lineal de faltante/merma usando cuantil de demanda neta
post-llegada, fractil Cu/(Cu+Cm), bajo restricción de pedido no negativo.

Distribución explícita: inversa marginal lineal por tramos compatible con los tres
cuantiles, colas acotadas por factor 2 y piso cero; cópula normal equicorrelacionada
con rho latente=0.35, 8192 escenarios antitéticos y PCG64/SHA-256 por serie/fecha,
semilla 42. Se suman demandas de escenarios, nunca cuantiles diarios. Dependencia
y colas no se identifican con tres cuantiles: se declaran como supuestos externos,
sin estimarlos con información futura ni prometer cobertura real. Costos/inventario
no alteran escenarios, permitiendo sensibilidad aislada con números aleatorios comunes.

Se reutiliza atomic_publish con linaje y versiones: entrada, costos, código y
runtime forman identidad; una configuración distinta crea otra publicación sin
sobrescribir. Salidas: suggested_orders.csv, costs.yaml, lineage.json y manifest.
Se conserva todo el linaje del pronóstico, modelo/run/DVC. Se rechazan costos
faltantes/no positivos, cuantiles inválidos y series sin siete fechas únicas.
Sin nuevas dependencias y sin operaciones Git, DVC o cambios en Airflow/modelos.

Nueve pruebas pytest pasan sin entrenamiento. La prueba end-to-end cambia solamente
costos en el mismo YAML y conserva demanda, semilla, pronósticos y resultados previos;
comprueba más pedido cuando aumenta el costo relativo de faltante y reutilización
al repetir. También se prueban acumulación, correlación, inventario/plazo/entradas,
ventas perdidas, cantidades fraccionarias/múltiplos y entradas inválidas.

Ejecución real sobre reports/uncertainty/2017-03-05-v2: 12.474 pronósticos existentes
para 5–11 marzo, 1.782 recomendaciones; llegada 7 marzo. Publicación base
84d211420fd506085ae5176219645db33640079faabdb875111841b83f95fb30. Cambiar únicamente
merma de 1 a 5 (faltante sigue 5) produce publicación
f50801688cb13f2c5799c6da49f424869479c4be36babb8c133d2a226a2c69f7:
las 1.782 recomendaciones disminuyen; ejemplo tienda 1/AUTOMOTIVE 30.650866→16.207156.
Los cuantiles acumulados quedan idénticos y el SHA de pronósticos sigue
64c2375c90fac0298a964e425148d40b988fbd09c57de5a9908950a116f14d8d.
Repetir la base devuelve reused=True. Informes y resultados locales en reports/orders
y reports/orders_sensitivity, ignorados por Git. Detalles en docs/motor_pedidos.md.

## D064 — Confirmación conjunta de pronóstico y pedidos en DAG 2

Se autoriza integrar el motor existente solo en lab1_pronostico_reposicion,
sin modificar ingesta, seguimiento, modelos ni realizar operaciones Git.
Se añade calcular_pedidos después del pronóstico y antes de confirmar_publicacion;
usa reposicion.orders y configs/costs.yaml sin cambiar el algoritmo existente.
El cron semanal, sensor, corte y backfill permanecen. costs_path opcional fija
configuración archivada bajo configs del proyecto o operational/costs, sin permitir
rutas a otros proyectos. Por defecto usa el YAML incluido en la imagen.

Nuevo helper reposicion.replenishment_publication comprueba integridad de ambos
bundles, su enlace exacto por hashes, costos/supuestos y una fila válida de pedido
por tienda/familia. Un paquete completo atómico conserva ambos CSV, costos,
lineage y manifest. Su identidad versiona pronóstico/pedidos, costos e inventario.
El Asset existente se emite solo tras este commit, con status=complete y los IDs,
hashes y versión de costos. Se mantiene el ID/hash del pronóstico en el evento
para compatibilidad con el seguimiento sin modificar ese DAG.

costs_version es SHA-256 de la copia real del YAML y costs_schema_version=1 define
su formato. El linaje contiene los supuestos completos de inventario, plazo,
model/run/DVC y ambos linajes originales. No se relee una configuración vigente
distinta al confirmar: se usa la copia inmutable utilizada por el motor.
Intermedios pueden quedar tras un fallo, pero no se emite Asset ni se marca un
paquete completo si faltan pedidos. Así el seguimiento no autoriza esa publicación
nueva incompleta; los históricos previamente válidos no se invalidan.

Prueba negativa pedidos_fallo_controlado (costos inexistentes): forecast success,
pedidos failed tras su retry, confirmación upstream_failed; cero Assets/paquetes.
Prueba positiva pedidos_historico_20170305: cuatro tareas success. Horizonte
5–11 marzo 2017, snapshot 645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0,
Champion v4/run f6062df6a53549a79125fd208aab381d existente. Se publican 12.474
pronósticos y 1.782 pedidos. pedidos_historico_20170305_reintento: success, con
reused=True en pronóstico, pedidos y paquete completo; una única salida de cada
pedido/paquete, sin sobreescribir ni recalcular resultados existentes.

Forecast d9f2d73162c63547301928f740166a5ce5cebd2d1e70c4f397d444d1bec58676;
orders 987482f0318cac1b349aaa2cd1cab009cc3635a0b3dd1adc90d25b800c3f00a5;
complete 1d278a9eafe88cb59fc2e01e77f2723cce7defc403dd56f2b72ef940554f3fd1.
Costos 01fc45e5271ef243c47a73cca65e69fbf9b55baa23439a87f07917d6d24760bb;
inventario f0be0567bc2f9ef1d3285445c0d97aaac4ea8acd259bf974f985ea61065720b8.
Inventario inicial/entradas cero, ventas perdidas, merma total al cierre, plazo
dos, costos ilustrativos faltante5/merma1: se conservan los supuestos de D063.

Catorce pruebas sin modelos aprobaron: consistencia/versiones, idempotencia,
fallos y sensibilidad de costos. Ruff/formato e importación correctos; checksum
de los otros DAGs y motores existentes idéntico antes/después. Solo se recrearon
procesos Airflow para aplicar imagen con nuevo helper/DAG; PostgreSQL/MLflow y
volúmenes conservados. Copia íntegra de revisión en reports/replenishment/<complete>/,
informe e2e.json; ambos ignorados por Git. No se reentrena ni cambia DVC/Registry.
Documentación en docs/pedidos_en_airflow.md.

## D065 — Reloj histórico explícito para el pronóstico programado

El run scheduled__2026-11-01T12:00:00+00:00 falló porque el sensor recibió
el intervalo físico 2026 como corte de datos. Los snapshots disponibles son
históricos: solo 645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0
contiene los 28 días previos necesarios para 2017-03-05. El snapshot más reciente
parcial para seguimiento no sirve de historia de inferencia. No se altera ese
control ni se imputa historia inexistente.

Se agrega forecast_clock.py, sin modelos, y simulation_calendar en pronostico.yaml:
modo historical_replay, replay favorita_2017_03_05, datos 2013-01-01 a 2017-08-15
según diagnóstico train, origen 2017-03-05, emisión 12Z y snapshot explícito.
El cron semanal y catchup=False no cambian. El escenario es fijo y reproducible;
no se avanza artificialmente por semana física ni se elige el último snapshot.
Para avanzar se necesita cambiar expresamente la política y un snapshot compatible.
No existe fallback a ahora() ni al intervalo de 2026 como fecha de ventas.

Se preservan backfills explícitos; origin sin emisión deriva 06 Guatemala.
El backfill nativo utiliza su intervalo histórico, con validación de dominio.
Manual sin corte usa replay configurado; snapshot explícito sin corte resuelve su
fecha bajo límite histórico, y vuelve a validarla tras selección. Se valida día
local, 28 días previos y siete de horizonte dentro del calendario. El modelo y
residuos siguen con disponibilidad temporal existente, sin ajustes ni reentrenamiento.

El reloj se registra en logs/XCom y metadata del Asset final con política completa,
SHA de política, fechas físicas y fechas/snapshot resueltos. No se incluyen las
fechas físicas en la identidad de resultados: un nuevo cron con el mismo escenario
reutiliza las publicaciones. No se alteran los publicadores, el motor de pedidos,
validación de snapshots o módulos/modelos existentes ni los otros dos DAGs.

Prueba real: se reabrieron exactamente las cuatro tareas del run scheduled de hoy
usando la función nativa clear_task_instances(run_on_latest_version=True). Se
conservaron run_type=scheduled, fecha lógica e intervalo físico 2026-11-01T12Z;
no se creó un run manual disfrazado ni se ajustó la fecha de la base de datos.
La selección de la versión actual evita reutilizar la definición serializada vieja.
Los intentos fallidos previos permanecen en logs. El run terminó success y volvió
a terminar success tras otro clear para comprobar idempotencia.

Corte efectivo 2017-03-05T12Z, origen 2017-03-05, historia exacta 2017-02-05 a
2017-03-04 (28 días), todos los recibos disponibles al corte. Resultado: 12.474
pronósticos y 1.782 pedidos, 5–11 marzo. Segundo intento reutiliza las tres salidas:
forecast bdf4290355b5f55a5f082dba182228c00833e9d1ceda42160d03e2805f86615d,
orders 18537175d56fbeea52a6d118398d24675d8bf0d3971b1bf3d191f6ba9e8a86d6,
complete d4215a0192e655e2f7fecaa29e575bddf77ab6d24f6e99b33e9932c524789613.
Política SHA c168b3e407c5124dd01aea1ae05049792552d4f55c83921007eac84080587ba3.

Diecisiete pruebas específicas pasan sin modelos; controles existentes de historia
incompleta siguen activos. Ruff/formato/importación correctos. Hash de los otros
DAGs y módulos de negocio/validación idéntico antes/después. Nueva imagen solo
agrega helper de reloj y configuración/DAG2; se recrean procesos Airflow para
aplicarla, conservando PostgreSQL/MLflow y volúmenes. No se cambia DVC ni se hacen
operaciones Git. Informe reports/simulated_clock/verification.json; detalles en
docs/reloj_simulado.md.

## D066 — Entrega histórica curada en DVC y google_drive

El usuario autoriza data/entrega con una sola publicación histórica de pronósticos,
pedidos y seguimiento, sin regenerar predicciones ni entrenar, sin DAGs ni commits
ni push Git. Esta autorización amplía explícitamente el alcance DVC previo; no se
agregan simulación, pesos históricos, CSV originales o snapshots completos.

Se selecciona la publicación completa d4215a0192e655e2f7fecaa29e575bddf77ab6d24f6e99b33e9932c524789613,
forecast bdf4290355b5f55a5f082dba182228c00833e9d1ceda42160d03e2805f86615d,
orders 18537175d56fbeea52a6d118398d24675d8bf0d3971b1bf3d191f6ba9e8a86d6,
horizonte 5–11 marzo 2017, emisión 2017-03-05T12Z. Seguimiento exacto
72fb79dec85a4a924c132c08747de3dad8b528452a26671b67ebf83e1d3163ef,
evaluado al 2017-04-02T12Z con corrección r0002 del 5 de marzo; run MLflow
9de3d4d5fc064c70a618afbf260dead8 FINISHED. Son 12.474 pronósticos/pares observados
y 1.782 pedidos, cero pendientes. Se comprueban claves, cuantiles originales,
checksums y concordancia de métricas existentes: MAE77.26379684508039,
WAPE0.16173741413512321 y cobertura0.8002244668911336.

Se copian sin alterar los bundles completos y de seguimiento, sus manifiestos
fuente, solo manifiestos de snapshots, metadatos MLflow y evento Asset. Los linajes
fuente ya embebidos no se duplican como archivos. No se copian credenciales,
.env, tokens, bases, volúmenes o modelos. El paquete tiene inventario SHA-256 y
README; lista cerrada de tipos y revisión de campos sensibles, sin archivos con
contenido duplicado por hash. Los cuantiles que conserva evaluation.csv son la
evidencia original de emparejamiento, no otra publicación regenerada.

DVC 3.67.1: dvc add --no-relink data/entrega. Se añade exclusivamente la excepción
!/data/entrega.dvc al gitignore para permitir su metadato; todos los contenidos
siguen excluidos de Git. El índice Git conserva su hash, sin staging/commit/push.
Se mantiene google_drive configurado por el usuario, sin cambiar configuración
ni autenticación. Driver existente dvc-gdrive3.0.1; sin instalaciones nuevas.

Puntero data/entrega.dvc: md5 13f375fa5bd804bc83ba5b7a3b76546e.dir,
17 archivos, 3.621.130 bytes. Push específico --remote google_drive: 18 objetos
subidos (17 archivos y el índice). Status local y cloud del único objetivo={};
se descargaron temporalmente del remoto el índice y los 17 objetos mediante su
ODB, verificando MD5 de índice y SHA-256 de cada archivo frente a data/entrega.
No se borró ni reemplazó la caché de DVC o los artefactos originales.
Informe fuera del target en reports/entrega/verificacion_dvc.json para no alterar
el paquete después de versionarlo. README/inventario dentro del target.

Los DAGs se conservan. No se hacen commits ni push de Git. El nuevo puntero y
excepción gitignore quedan locales, pendientes de publicación autorizada. Antes
de publicar ese metadato por Git habrá que ampliar su lista permitida en
scripts/auditar_publicacion.py y bloquear el driver gdrive en dependencias; no
se modifican estos componentes para esta entrega de artefactos.


### D067 — Auditoría de entrega y dependencias Google Drive (2026-11-01)

Se permite exclusivamente data/entrega.dvc como puntero de directorio con un
output relativo entrega, hash MD5 .dir, tamaño entero no negativo y exactamente
17 archivos. Se conservan las validaciones de campos, secretos, enlaces y
restricciones de originales/modelos; el contenido de data/entrega sigue excluido.
Las pruebas rechazan otros punteros, rutas externas, campos adicionales y
metadatos inválidos, incluyendo enteros booleanos.

Se incorporan dvc-gdrive 3.0.1 y PyDrive2 1.21.2 a dev junto a DVC 3.67.1.
Se fija la combinación instalada pyOpenSSL 24.2.1, cryptography 43.0.3 y
AsyncSSH 2.21.1: la resolución inicial sin estas restricciones conservaba
cryptography 50.0.2 y elegía un OpenSSL distinto al probado localmente.
requirements.lock se regenera con pip-tools 7.6.2 bajo Python 3.12.16 y hashes.
Sus 156 versiones coinciden con el entorno instalado. No se instalan paquetes.

Verificación: 52 pruebas de seguridad pasan; Ruff y formato pasan; auditoría
del árbol de trabajo pasa; pip check sin incompatibilidades; instalación
--dry-run --require-hashes sin cambios; imports DVC/Drive/OpenSSL/AsyncSSH
correctos. No se realizó una instalación limpia: el dry-run verifica el
entorno existente y no vuelve a descargar paquetes ya satisfechos.
No se modifican DAGs, modelos, datos ni credenciales, ni se hacen operaciones
de staging, commit, push o merge. Las credenciales siguen en config.local.


### D068 — Preparación de siete commits locales (2026-11-01)

Por autorización del usuario se organiza el trabajo pendiente en siete commits
funcionales en feature/comparacion-modelos, sin push, merge ni PR. Antes de
modificar el índice se guarda respaldo de los 48 archivos pendientes, sus hashes,
HEAD y un patch binario en /private/tmp/lab1-pre-commits-20261101-162314.
No se incluyen archivos ignorados ni credenciales en ese respaldo de código.

Validación previa: pytest completo, 221 pruebas aprobadas y tres advertencias
no bloqueantes (detección de cores, esquema entero MLflow y deprecación pandas);
Ruff check/formato y auditoría del árbol de trabajo aprobados. Los tests ejercitan
modelos sintéticos locales; no se ejecutan entrenamientos del laboratorio ni
se alteran sus modelos o runs existentes. Cada commit se prepara con rutas
explícitas y auditoría del índice. Datos y artefactos permanecen fuera de Git;
solo se incorpora el puntero DVC autorizado de la entrega.
