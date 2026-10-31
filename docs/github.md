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
no se cambia la configuración global. No se inicializa DVC ni se crea `entrega-lab1`.

## Qué se publica

Código Python, DAG, configuraciones sin secretos, Compose/Dockerfile, scripts,
pruebas sintéticas, documentación, lock de dependencias y el enunciado PDF pequeño.
Los informes Markdown contienen agregados y checksums de integridad, no datasets.

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
