# Versionado DVC de los modelos actuales

Se versionan exclusivamente **12 pipelines y cuatro modelos nativos CatBoost**,
correspondientes a los cuatro folds de las variables temporales v2. No se entrenó
ningún modelo, se cambiaron hiperparámetros ni se alteró MLflow.

| Modelo | Pipelines `.joblib` | Nativos `.cbm` |
|---|---:|---:|
| Random Forest temporal v2 | 4 | 0 |
| HistGradientBoosting temporal v2 | 4 | 0 |
| CatBoost temporal v2 | 4 | 4 |
| Total | 12 | 4 |

Los folds siguen los cortes 8, 15, 22 y 29 de enero de 2017. Se copiaron los pesos
existentes de `reports/walk_forward/temporal_v2_january_2017` y
`reports/walk_forward/catboost_january_2017`, conservando sus fuentes intactas.

```text
models/
  current.dvc                  # único puntero nuevo que se guarda en Git
  current/                     # binarios ignorados por Git
    random_forest/fold_1..4/model.joblib
    hist_gradient_boosting/fold_1..4/model.joblib
    catboost/fold_1..4/model.joblib
    catboost/fold_1..4/model.cbm
```

El directorio contiene exactamente los 16 binarios autorizados, **35.544.890 bytes**.
No incluye parámetros, métricas, manifiestos propios, gráficas, predicciones,
simulación, snapshots, modelos históricos ni copias exportadas de Model Registry.
El índice de directorio lo genera DVC automáticamente; no es un artefacto adicional
de entrenamiento.

## Alta y remoto

Comandos utilizados:

```bash
.venv/bin/dvc add --no-relink models/current
.venv/bin/dvc push models/current.dvc -r storage
.venv/bin/dvc status models/current.dvc --cloud -r storage
```

Se conserva el remoto existente `storage` en
`~/dvc-storage/corporacion_favorita`. El push agregó **17 objetos**: 16 contenidos
y el índice `6758afd54f231ee0e194603f381b7567.dir`. Caché y remoto quedaron sincronizados.
`cache.type=copy` y `--no-relink` evitan reemplazar por enlaces los archivos locales.
No se borraron fuentes ni cachés y no se utilizó almacenamiento de otro proyecto.

Git admite únicamente `models/current.dvc` dentro de models. La auditoría valida
ruta `current`, hash de directorio, tamaño y `nfiles=16`; bloquea los demás punteros,
los binarios y los archivos nativos `.cbm`, incluso fuera de models.

## Recuperación y verificación

Desde este repositorio con sus dependencias instaladas:

```bash
.venv/bin/dvc pull models/current.dvc -r storage
```

Para comprobar una recuperación en un clon aislado, sin borrar la caché principal:

```bash
.venv/bin/python scripts/verificar_recuperacion_modelos_dvc.py
```

La prueba efectuada partió sin pesos ni caché: descargó 17 objetos y recuperó los
16 archivos con igual SHA-256 y tamaño. Las fuentes de reports y los cinco CSV
originales conservaron SHA-256 y mtime; los modelos locales y la caché principal
no cambiaron durante la prueba de recuperación. El clon se conserva para inspección.
El informe local `reports/dvc_models/recovery.json` queda fuera de Git y de este
versionado DVC, cuyo alcance sigue siendo solo los 16 archivos.

Se ejecutaron 40 pruebas de auditoría/exclusiones, sin entrenamiento, y Ruff/formato.
No se ejecutan los comandos de ajuste de candidatos ni la suite de modelos para
realizar estas operaciones de almacenamiento.

El remoto es **local a esta máquina**. El puntero en Git no permite que un docente
o GitHub Actions descarguen los pesos sin un remoto externo accesible, que permanece
pendiente. Los cinco originales siguen versionados; simulación, snapshots y modelos
históricos continúan excluidos por instrucción del usuario.
