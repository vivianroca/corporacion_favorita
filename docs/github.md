# GitHub, Pull Requests y CI

## Repositorio y ramas

Repositorio personal público: [vivianroca/corporacion_favorita](https://github.com/vivianroca/corporacion_favorita).
El directorio local conserva el nombre `lab1`. El remoto `origin` usa HTTPS y no
incluye tokens ni credenciales en su URL.

`main` contiene una base mínima de documentación, reglas, exclusiones y workflow.
La implementación del laboratorio se entrega para revisión en
`feature/ingesta-airflow`, mediante un Pull Request hacia `main`. El primer PR
incluye contratos, simulación, ingesta, snapshots, automatismo, infraestructura y
pruebas ya verificadas. No se hace merge automáticamente.

Los commits usan identidad noreply de GitHub configurada solo en este repositorio;
no se cambia la configuración global. El versionado inicial DVC se prepara en
`feature/dvc`; no se crea `entrega-lab1`.

## Qué se publica

Código Python, DAG, configuraciones sin secretos, Compose/Dockerfile, scripts,
pruebas sintéticas, documentación, lock de dependencias y el enunciado PDF pequeño.
Los informes Markdown contienen agregados y checksums de integridad, no datasets.
DVC agrega exclusivamente cinco punteros `.csv.dvc` de originales y configuración
compartida sin credenciales. La caché y `.dvc/config.local` permanecen fuera de Git.

Se excluyen datos originales, simulaciones, bandeja operativa, resultados, modelos,
entornos, `.env`, bases de datos, claves privadas y volúmenes. `.env.example`
mantiene vacíos todos los valores de secretos. Los tests construyen sus datos en
directorios temporales y no requieren Kaggle ni Docker.

## Auditoría previa a cada envío

```sh
.venv/bin/python scripts/auditar_publicacion.py --working-tree
.venv/bin/python scripts/auditar_publicacion.py --staged
.venv/bin/python scripts/auditar_publicacion.py --refs main feature/ingesta-airflow
```

La auditoría revisa rutas, tipos de archivo, enlaces simbólicos, tamaño máximo de
1 MiB por blob, patrones conocidos de tokens/claves y coincidencias con los secretos
del `.env` local sin mostrarlos. El modo historial revisa todos los commits y blobs
alcanzables desde las ramas que se enviarán, no solo el árbol final. También se
ejecuta en CI, donde no se necesita ni existe el `.env` de desarrollo.

Es una defensa específica del laboratorio, no una garantía general de detección de
cualquier secreto arbitrario. Nunca usar `git add -f` para datos o credenciales.

## GitHub Actions

`.github/workflows/ci.yml` se ejecuta al abrir, actualizar o reabrir un PR hacia
`main`. El job se llama **`pytest`**, nombre estable para la protección de rama.
Incluye además `workflow_dispatch` para diagnóstico manual sobre la rama feature;
esto no sustituye el disparo automático de los PRs.

El runner usa Ubuntu 24.04 y Python 3.12. Las acciones oficiales de checkout y setup
están fijadas a commits completos, comprobados contra sus releases oficiales.
El token solo tiene permiso de lectura y no queda persistido en el checkout.

El job instala `requirements.lock` con hashes, instala el paquete sin resolver
dependencias adicionales, ejecuta `pip check`, audita el historial, revisa Ruff y
ejecuta pytest. No inicia Docker, lee datos de Kaggle, utiliza secretos privados ni
registra experimentos en MLflow.

El estado autoritativo de CI está en Checks del PR y en
[GitHub Actions](https://github.com/vivianroca/corporacion_favorita/actions).

## Protección de main

La política requiere un Pull Request y el check **`pytest`** exitoso y actualizado
respecto a la base. Se aplica también al administrador y bloquea force-push y borrado.
El PR no se fusiona automáticamente.

No se exige una aprobación adicional de otra cuenta: es un laboratorio personal y
el autor no puede aprobar su propio PR. Esto mantiene obligatorios PR y CI sin
crear un bloqueo que requiera añadir colaboradores. El usuario revisa y decide el merge.

Después de cambiar la rama base o el código, se debe esperar de nuevo al resultado
de Checks antes de fusionar. Cualquier ajuste futuro a esta protección debe ser
explícito; no se desactiva para forzar un merge.

## Verificación del primer PR

El repositorio público y el PR #1 se crearon correctamente, y se confirmó la
protección por API. GitHub registró opened/reopened, pero inicialmente no creó runs
ni check suites. Se mantuvo el PR abierto y bloqueado y se añadió un disparo manual
de diagnóstico. No se presenta la ausencia de un check como una CI aprobada.
La actualización del workflow disparó correctamente `pull_request`. La
[ejecución de referencia](https://github.com/vivianroca/corporacion_favorita/actions/runs/41177434432)
aprobó auditoría, Ruff y **103 pruebas** en Ubuntu 24.04 con Python 3.12.15.
La ejecución manual de diagnóstico también aprobó, pero no se usó para sustituir
la comprobación automática del PR. El estado de Checks del último commit sigue
siendo la autoridad antes del merge.

La protección exige el check `pytest` de la aplicación GitHub Actions (app ID 15368),
base actualizada y PR, con aplicación a administradores. El PR permanece abierto,
sin auto-merge. Esa primera revisión precedió a DVC; su configuración posterior
se documenta en [dvc.md](dvc.md). El tag de entrega permanece sin crear.
