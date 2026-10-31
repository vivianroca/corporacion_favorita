# DVC: primeras fuentes versionadas

## Alcance y estado comprobado

Se inicializó DVC **3.67.1** con integración Git en la raíz de `lab1`, en
`feature/dvc` desde `main` actualizado. El árbol estaba limpio antes de empezar.
La dependencia exacta está en `pyproject.toml`, extra `dev`, y sus dependencias
transitivas y hashes están en `requirements.lock`. No se instaló globalmente.

| Fuente | Bytes |
|---|---:|
| `train.csv` | 121.800.373 |
| `stores.csv` | 1.387 |
| `holidays_events.csv` | 22.309 |
| `oil.csv` | 20.580 |
| `transactions.csv` | 1.552.637 |
| **Total** | **123.397.286** |

Total: 123,397286 MB decimales, aproximadamente 117,68 MiB. `test.csv` y
`sample_submission.csv` permanecen en su ubicación, ignorados y sin punteros DVC.

Git guarda únicamente los cinco `data/original/*.csv.dvc`, `.dvc/config`,
`.dvc/.gitignore` y `.dvcignore`, además de código, configuración y documentación.
Los punteros contienen MD5, tamaño y ruta; no contienen filas de los CSV.
La auditoría valida su esquema y permite solo los cinco nombres requeridos.

## Configuración y comandos usados

La inicialización se hizo una sola vez con `dvc init`, sin `--no-scm`. El primer
intento quedó incompleto por una caché global protegida; se conservó esa metadata
temporal en un respaldo y se completó la inicialización sin borrar datos.

La configuración compartida tiene remoto predeterminado `storage`, URL
`~/dvc-storage/corporacion_favorita`, caché de datos con tipo `copy` y analítica
deshabilitada. `~` se expande al home de quien ejecuta DVC: no es un servidor remoto.
No se utilizó el almacenamiento de otro proyecto.

Comandos de la primera carga, ya ejecutados:

```sh
.venv/bin/dvc remote add -d storage '~/dvc-storage/corporacion_favorita'
.venv/bin/dvc add --no-relink data/original/train.csv data/original/stores.csv data/original/holidays_events.csv data/original/oil.csv data/original/transactions.csv
.venv/bin/dvc push -r storage -j 4
.venv/bin/dvc status --cloud -r storage
```

No repetir `init` ni `remote add` en un clon que ya contiene `.dvc` y el remoto.
Para uso habitual basta consultar, actualizar conscientemente los punteros si cambian
las fuentes autorizadas, y enviar o recuperar objetos:

```sh
.venv/bin/dvc --version
.venv/bin/dvc remote list
.venv/bin/dvc status
.venv/bin/dvc push -r storage
.venv/bin/dvc pull -r storage
```

`--no-relink` evita recrear los originales desde la caché durante el alta. Se
comprobaron SHA-256 y mtime antes y después: no cambiaron. Los cinco objetos remotos
se verificaron también por MD5 y tamaño en `storage/files/md5/<prefijo>/<resto>`.

## Caché de datos frente a caché de índices

- `.dvc/cache` contiene los objetos de datos; está fuera de Git.
- `.dvc/tmp/site-cache` contiene índices temporales del repositorio.
- `.dvc/config.local` fija la caché de índices dentro de este workspace y está
  ignorado. No se publica una ruta absoluta privada como configuración compartida.

En un clon nuevo, si el sistema restringe la caché global de DVC, configurar una
ubicación propia antes de operar:

```sh
DVC_SITE_CACHE_DIR="$PWD/.dvc/tmp/site-cache" .venv/bin/dvc config --local core.site_cache_dir "$PWD/.dvc/tmp/site-cache"
```

Las reglas de Git dejan transitables `data/` y `data/original/`, pero ignoran su
contenido salvo los cinco punteros y una eventual `.gitignore` local. Se usan
comodines con al menos un carácter (`?*`) para que el recorrido de DVC no descarte
los directorios padre al consultarlos con barra final. Una prueba verifica tanto
el recorrido como la exclusión de CSV, simulaciones y archivos de la competencia.

## Recuperación sin borrar datos ni caché

Se implementó y ejecutó:

```sh
.venv/bin/python scripts/verificar_recuperacion_dvc.py
```

El script clona la revisión Git local en un directorio temporal independiente,
comprueba que no contiene CSV ni objetos en caché y ejecuta `dvc pull -r storage`.
Su caché de datos e índices son distintas de las del proyecto principal. Recuperó
**5 archivos**, por **123.397.286 bytes**, con los mismos SHA-256.

Resultados reales:

- Push: `5 files pushed`.
- Estado de nube: `Cache and remote 'storage' are in sync.`
- Pull aislado: `5 files fetched and 5 files added`.
- Originales y caché principal: contenido y mtime sin cambios.
- El clon de prueba queda conservado para inspección, sin eliminar cachés.

El informe detallado está en `data/dvc_recovery_report.json`, ignorado por Git.
La recuperación inicial se verificó sobre el commit `e0c6341`; las adiciones
posteriores de documentación no cambian los punteros. El clon y su caché ocupan
espacio adicional temporal; no se usó limpieza destructiva como parte de la prueba.

## Simulación y snapshots: medición y estrategia posterior

No se agregaron a DVC en esta etapa.

| Conjunto inspeccionado | Archivos | Bytes lógicos | Contenidos únicos | Bytes únicos |
|---|---:|---:|---:|---:|
| Simulación maestra | 10.143 | 138.307.715 | 10.143 | 138.307.715 |
| Snapshots históricos en volumen | 18 | 240.769 | 10 | 164.174 |
| Publicaciones automáticas en volumen | 12 | 82.442 | 8 | 80.958 |

El inventario completo y hashing MD5 de la simulación tardó 1,489 s en esta máquina.
Es una medida de lectura local, **no** un benchmark de `dvc add`, de push ni de nube.
La simulación tiene 5.071 CSV, 5.071 sobres y un manifiesto. Su primera carga
implicaría más de diez mil objetos más índices, sin ahorro inicial por contenido
idéntico; caché y remoto añadirían aproximadamente 276,6 MB lógicos, además de
metadatos y asignación física. Se debe medir latencia y cantidad de operaciones,
no solo bytes, antes de habilitar esa carga.

Estrategia propuesta:

1. Conservar ahora fuentes originales, código y políticas deterministas. Permiten
   reconstruir la generación maestra con su identidad y checksums, sin almacenar
   todas las entregas generadas por adelantado.
2. Cuando se requiera conservar una generación exacta, versionar **un directorio
   inmutable por generación** o particiones por fuente/mes, con pocos punteros DVC
   y sus índices de directorio; no crear diez mil archivos `.dvc` en Git.
3. Hacer primero un piloto aislado de una partición representativa: medir alta,
   push y pull, número de objetos, bytes únicos y espacio físico. No tocar la
   bandeja operativa que está montada en solo lectura en Airflow.
4. Versionar solo snapshots/publicaciones completos y cerrados, por su ID y con
   manifiesto de linaje. DVC puede reutilizar CSV idénticos entre snapshots; una
   modificación de un archivo completo genera otro objeto completo, no un delta
   por filas. Retener todas las versiones necesarias para reproducir resultados.
5. No versionar en caliente `control.sqlite`, bases PostgreSQL/MLflow, logs ni
   volúmenes completos. Si se necesita un respaldo del ledger, producir antes un
   export consistente e inmutable mediante la API de backup de SQLite.

No se recomienda como primera opción un ZIP monolítico: reduce objetos pero
invalida el archivo entero al cambiar una entrega y pierde deduplicación granular.
Una representación consolidada por partición solo se considerará tras el piloto,
preservando un manifiesto que permita reconstruir rutas y verificaciones originales.

## Acceso del equipo docente

El remoto `storage` funciona **en esta máquina**; ni un clon público de GitHub ni
un runner hospedado pueden leer su directorio home. Falta seleccionar y habilitar
un almacenamiento externo para compartir los objetos, no para compartir el código.

Se recomienda un bucket S3 o compatible con prefijo exclusivo del laboratorio y
acceso de lectura para el docente. Mantener `storage` como respaldo local y agregar
otro remoto, por ejemplo `docente`, cuando exista el bucket y se autoricen accesos.
Se deberá fijar también la dependencia del backend S3 en el lock. Las credenciales
se entregan por perfil/variables de entorno o `.dvc/config.local`, nunca en Git.
No se creó un bucket, no se configuraron credenciales ni se contrató almacenamiento.

Referencias oficiales: [alta y no-relink](https://doc.dvc.org/command-reference/add),
[remotos](https://doc.dvc.org/command-reference/remote/add) y
[S3](https://doc.dvc.org/user-guide/data-management/remote-storage/amazon-s3).
