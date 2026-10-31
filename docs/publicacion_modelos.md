# Publicación de modelos: ramas, commits y tags

Las ramas están encadenadas: cada etapa añade sus archivos sobre las anteriores.
Los tags anotados identifican snapshots de código/configuración; no contienen pesos,
datos o artefactos MLflow. No son aliases de Model Registry y no eligen Champion.

| Rama | Tag | Contenido añadido |
|---|---|---|
| `feature/baseline-semanal` | `lab1-baseline-v1` | Agregar baseline semanal sin leakage y tracking de resultados |
| `feature/random-forest` | `lab1-random-forest-v1` | Agregar Random Forest y System Metrics reproducibles |
| `feature/hist-gradient-boosting` | `lab1-hist-gradient-boosting-v1` | Agregar HistGradientBoosting y persistencia MLflow |
| `feature/walk-forward` | `lab1-walk-forward-v1` | Agregar walk-forward de cuatro ventanas con metricas ponderadas |
| `feature/variables-temporales` | `lab1-variables-temporales-v2` | Agregar calendario por disponibilidad e imputacion por serie y familia |
| `feature/catboost` | `lab1-catboost-v1` | Agregar candidato CatBoost con folds y variables temporales v2 |
| `feature/model-registry` | `lab1-model-registry-v1` | Publicar pipelines existentes en MLflow Models y documentar hitos Git |

La rama `feature/modelos-pronostico` integra las siete etapas para un PR hacia main.
No se hace merge automáticamente ni se crea entrega-lab1.

Se preserva un respaldo verificado de todos los cambios previos antes de organizar
los commits. Código, pruebas, configuración y documentación se publican en Git.
CSV originales/predicciones, simulación, snapshots, joblib/CBM, bases, volúmenes y
credenciales permanecen excluidos. Los cinco CSV originales se referencian mediante
los punteros DVC existentes; los pesos siguen en MLflow. No se inicializa ni modifica DVC.

El lock compartido y pyproject de toda la pila de modelado se incluyen desde la etapa
Random Forest, donde aparecen las primeras dependencias de ML/System Metrics. Evita
reconstruir locks intermedios y conserva las versiones/hashes ya verificadas bajo
Python 3.12; la implementación de cada candidato se añade en su rama correspondiente.

Las pruebas de cada checkpoint usan únicamente datos sintéticos y temporales. No se
ejecutan los comandos de entrenamiento operativo ni se modifica el estado de MLflow.
La validación Linux/Python 3.12 se realiza mediante GitHub Actions en el PR.
