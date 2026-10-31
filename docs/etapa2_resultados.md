# Evidencia de la etapa 2

## Verificación sobre los cinco originales

Generación: `f3c5cd35b788c7e6db85fc209249dfb1c34a27754791f5dad0ee8e168c2b15bf`.

Corte histórico: `2017-01-01T05:00:00Z` (2017-01-01 00:00 en America/Guayaquil).

Entregas verificadas: **5071**; histórico: **4362**; bandeja: **709**.

| Fuente | Filas originales | Fechas de referencia | Filas conocidas al corte inicial, última revisión | Demoras | Particiones corregidas |
|---|---:|---:|---:|---:|---:|
| holidays_events | 350 | 312 | 299 | 0 | 0 |
| oil | 1,218 | 1,218 | 1,043 | 60 | 34 |
| stores | 54 | 1 | 54 | 0 | 0 |
| train | 3,000,888 | 1,684 | 2,594,592 | 87 | 88 |
| transactions | 83,488 | 1,682 | 71,073 | 81 | 52 |

El histórico conserva todas las revisiones conocidas al corte. La columna de filas cuenta únicamente la última revisión disponible por partición, evitando duplicar medidas. En tiendas, la fecha de referencia es sintética; en feriados, la carga puede incluir eventos futuros planificados.

## Comprobaciones realizadas

- Validación completa de esquemas, tipos, nulabilidad, claves y relaciones sobre los originales.
- Reejecución con los mismos parámetros sin modificar contenido ni tiempos de modificación de ningún archivo generado.
- Auditoría de todos los sobres y CSV, incluidos archivos extra o faltantes.
- Coincidencia de los cinco SHA-256 originales con el diagnóstico inicial.
- Conteos de filas de todas las particiones finales iguales a los originales para cada fuente.
- Lectura por corte disponible y revisiones comprobadas con escenarios sintéticos.

## Pruebas automatizadas

Comando: `.venv/bin/python -m pytest -q`.

Resultado: **52 passed**. Datos sintéticos independientes de Kaggle; casos de tipo, claves, geografía, disponibilidad, retrasos, correcciones, idempotencia, corrupción, rutas, publicación atómica y CLI.

Ruff: `.venv/bin/ruff check src/reposicion tests scripts` — sin errores.

Esta evidencia no implica entrenamiento, ingesta operativa ni creación de DAGs. No se agregaron datos a Git ni se modificaron los originales.
