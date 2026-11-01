# Restauración del Champion sin entrenamiento

La restauración no necesita el MLflow original, sus volúmenes ni `reports/`.
Requiere el código del proyecto, su entorno Python 3.12 con `requirements.lock`,
acceso autenticado al remoto DVC y un servidor MLflow 3.17.2 vacío.
No reconstruye todo el laboratorio: no genera simulación ni snapshots y no
configura los DAGs. Es un paso explícito de preparación del modelo.

## Artefactos indispensables

| Puntero | Contenido |
|---|---|
| `models/current.dvc` | Los 16 pesos existentes. Se usa únicamente `random_forest/fold_4/model.joblib`; no se duplican pesos. |
| `models/champion_restore.dvc` | Siete archivos: cuatro `evaluation.csv` originales, metadatos de los runs, entrada/salida de comprobación y manifiesto SHA-256. |

El paquete nuevo ocupa **4.024.988 bytes**. Conserva los cuatro folds RF temporal
v2 de enero de 2017, con sus IDs originales, MAE/WAPE y fechas de entrenamiento,
emisión y disponibilidad de evaluación. No incluye credenciales ni System Metrics
de una ejecución nueva. Las métricas copiadas son resultados históricos, no
evidencia de nuevos entrenamientos.

El manifiesto también vincula el SHA-256 del pipeline y del puntero DVC existente.
Se verifica el inventario exacto, los checksums, las revisiones de dependencias y
la consistencia temporal de los residuos antes de deserializar pesos o escribir
en el servidor destino. DVC no autentica por sí mismo a un editor del manifiesto:
se deben obtener código y punteros del repositorio de confianza.

## Recuperar y restaurar

Desde la raíz del repositorio, con el entorno instalado:

```bash
.venv/bin/dvc pull models/current.dvc models/champion_restore.dvc --remote google_drive
.venv/bin/python -m reposicion.champion_restore verify
.venv/bin/python -m reposicion.champion_restore restore --uri http://localhost:5011
```

El servidor indicado debe estar vacío respecto del modelo registrado
`corporacion_favorita_random_forest`. El comando rechaza versiones ajenas para
evitar sobrescribir una promoción existente. **No ejecutar contra el MLflow
original como si fuera vacío**: este ya tiene sus versiones y Champion.

El acceso a Google Drive requiere permiso de lectura sobre la carpeta compartida
y autenticación local de DVC. Las credenciales OAuth permanecen en
`.dvc/config.local` y en el almacén de autenticación local, nunca en el paquete.
El usuario del docente debe disponer de sus permisos/configuración; no se
distribuyen las credenciales de esta máquina.

La restauración crea un experimento cuyo nombre incorpora la identidad del
paquete y cuatro runs marcados `restoration_only=true`. Conserva todos los
parámetros necesarios para el consumidor de cuantiles y publica cada validación
como `evaluation.csv`. Registra el pipeline existente y verifica su carga y
predicción antes de asignar `champion`.

En un Registry vacío la versión restaurada es **1**, aunque corresponde a la
versión fuente **4**. No se crean versiones ficticias para reproducir el número.
Los tags `restore.source_version`, `restore.source_run_id`, `restore.bundle_id`
y los tags `champion.*` conservan el linaje original. El resultado del comando
incluye el mapa completo entre IDs fuente e IDs destino. Los pronósticos deben
usar el alias o la versión devuelta, no asumir que sigue existiendo la versión 4.

Repetir el comando verifica y reutiliza los mismos cuatro runs y la misma versión.
Puede reanudar una interrupción antes de registrar el modelo sin crear otros runs.
Una alteración de residuos o pesos publicados provoca un error, no una reparación
silenciosa. Hay un lock por URI en `reports/champion_restore/locks`; las
invocaciones concurrentes deben ejecutarse desde el mismo host/directorio de
locks. No se ofrece exclusión distribuida entre máquinas distintas.

## Prueba real realizada

Se creó un servidor temporal separado, sin los volúmenes del laboratorio:

```bash
docker run --pull never --rm -d --name lab1-mlflow-restore-test \
  -p 127.0.0.1:5012:5000 ghcr.io/mlflow/mlflow:v3.17.2 \
  mlflow server --host 0.0.0.0 --port 5000 --workers 1 \
  --backend-store-uri sqlite:////tmp/restore.db --serve-artifacts \
  --artifacts-destination /tmp/artifacts --allowed-hosts 'localhost:*,127.0.0.1:*'
.venv/bin/python -m reposicion.champion_restore restore --uri http://localhost:5012
.venv/bin/python -m reposicion.champion_restore restore --uri http://localhost:5012
```

Resultado: **4 runs, 1 versión READY, alias champion → 1**, sin duplicados al
repetir. El modelo corresponde al run original
`f6062df6a53549a79125fd208aab381d` y al pipeline SHA-256
`bb71d5bf8116b80c8b1fb409b7420a514b2dae90e93e87d064f6235e178583ef`.

Con la simulación existente, el motor original de cuantiles se ejecutó contra el
servidor restaurado para `origin=2017-03-05`, emisión `2017-03-05T12:00:00Z`:

```python
from reposicion.uncertainty import run

run("2017-03-05", "2017-03-05T12:00:00Z",
    "reports/champion_restore/inference", "http://localhost:5012")
```

Se compararon las mismas claves de fecha/tienda/familia y las columnas
`point_prediction`, `p10`, `p50`, `p90` contra
`data/entrega/publicacion/forecast_quantiles.csv`: **12.474 filas, diferencia
máxima 0.0**, cuantiles ordenados y no negativos. La comprobación admite
`rtol=1e-12`, `atol=1e-9` por diferencias flotantes entre plataformas.
No se cambian los filtros originales: solo residuos de períodos anteriores al
origen y disponibles al corte; el modelo fuente está evaluado al 3 de marzo.

El informe local está en `reports/champion_restore/verification.json`, ignorado
por Git. El MLflow original conservó sus 51 runs (parámetros, métricas y estado)
y el alias original en versión 4. El servidor de prueba se retira al finalizar:

```bash
docker stop lab1-mlflow-restore-test
```

## Sincronización y pruebas

Comandos ejecutados para versionar y sincronizar:

```bash
.venv/bin/dvc add --no-relink models/champion_restore
.venv/bin/dvc push models/champion_restore.dvc models/current.dvc --remote google_drive
.venv/bin/dvc status models/champion_restore.dvc models/current.dvc --remote google_drive --cloud --json
```

Se subieron **8 objetos nuevos** (siete archivos y su índice); los pesos existentes
ya estaban disponibles. El estado cloud fue `{}` para ambos punteros.
La verificación independiente descarga los objetos del remoto a una carpeta
temporal sin usar la caché de contenidos local y comprueba MD5/SHA-256.

```bash
.venv/bin/python -m pytest -q tests/test_champion_restore.py tests/test_uncertainty.py tests/test_publication_audit.py
```

**65 pruebas aprobadas**: idempotencia, recuperación de interrupciones, protección
del Registry ajeno, corrupción local/remota, no fuga temporal, seguridad del nuevo
puntero y conservación de las restricciones anteriores. Los tests usan un cliente
en memoria y no entrenan modelos. Ruff y la auditoría de publicación pasan.
