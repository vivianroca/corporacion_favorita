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
