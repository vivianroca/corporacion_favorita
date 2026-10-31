# Validación temporal walk-forward

`src/reposicion/walk_forward.py` evalúa los tres modelos con cuatro orígenes
semanales definidos en `configs/walk_forward.yaml`. Usa una ventana móvil de ocho
semanas para los candidatos ML, consistente con el entrenamiento anterior. Cada
modelo ML y sus transformaciones se instancian y ajustan de nuevo en cada origen:
son ocho ajustes independientes, sin warm start ni selección de hiperparámetros.

| Ventana | Emisión UTC | Horizonte evaluado | Etiquetas elegibles de entrenamiento ML | Reales disponibles al corte UTC |
|---|---|---|---|---|
| 1 | 2017-01-08 12:00 | 2017-01-08–2017-01-14 | 2016-11-13–2017-01-07 | 2017-02-10 12:00 |
| 2 | 2017-01-15 12:00 | 2017-01-15–2017-01-21 | 2016-11-20–2017-01-14 | 2017-02-17 12:00 |
| 3 | 2017-01-22 12:00 | 2017-01-22–2017-01-28 | 2016-11-27–2017-01-21 | 2017-02-24 12:00 |
| 4 | 2017-01-29 12:00 | 2017-01-29–2017-02-04 | 2016-12-04–2017-01-28 | 2017-03-03 12:00 |

Los cuatro cortes comienzan en enero; el horizonte del último termina en febrero.
12:00 UTC equivale a 07:00 en Ecuador y 06:00 en Guatemala. El horizonte es diario
por tienda/familia. El baseline no se ajusta: toma la semana inmediatamente anterior
al origen (1–7, 8–14, 15–21 y 22–28 de enero, respectivamente).

## Disponibilidad y comparación justa

Cada entrenamiento usa solo etiquetas con fecha anterior al horizonte, disponibles
al emitir. Para crear cada ejemplo histórico se reconstruyen las variables con las
revisiones conocidas a las 12:00 UTC de su propio origen, mediante DeliveryCatalog.
Las correcciones conocidas después no se incorporan retrospectivamente a variables.
Las nuevas revisiones conocidas en un origen posterior sí pueden entrar entonces.

Se mantienen las variables y parámetros anteriores: rezagos 7/14/21/28, promedio y
conteo de la semana previa, indicadores de ausencia, tienda/familia y calendario.
La codificación y las medianas se ajustan solo con entrenamiento. Se conservan ceros
y ventas fraccionarias. No se imputan etiquetas ni reales. Las etiquetas inexistentes
se excluyen y contabilizan; la fecha ausente 2016-12-25 está en las cuatro ventanas
móviles. Cada corte entrena con 98.010 filas en los datos reales actuales.

El código comprueba previamente que los cuatro orígenes tengan la historia semanal
que exige el baseline; si falta, aborta en lugar de omitir una ventana o rellenar con
ceros. También exige el mismo universo de series entre ventanas y las mismas claves
y ventas reales entre los tres modelos en cada una. No se recortan las observaciones
para favorecer un modelo. Se evalúan 12.474 registros por ventana y 49.896 por modelo.

Los reales se consultan después de predecir para cada modelo, con un desfase fijo de
33 días desde la emisión. Este es un supuesto de evaluación, elegido para mantener
el criterio de maduración del experimento anterior, no un SLA inferido del origen.
No afecta el corte de entrenamiento ni habilita datos futuros como variables.

## Métricas y trazabilidad

Cada combinación modelo/ventana genera su propio run con MAE y WAPE, parámetros,
identificadores/checksums de entregas, predicciones, evaluación por clave, gráficas
de reales frente a pronósticos y distribución de errores. Los candidatos ML guardan
su pipeline entrenado. Todos usan el contexto de System Metrics; CPU/RAM y duración
se registran mientras trabajan. Un baseline muy corto puede no producir muestras
periódicas. Los modelos ML sí deben producirlas en esta ejecución real.

Los dos modelos ML comparten las mismas filas y etiquetas de entrenamiento y el
mismo SHA-256 del conjunto en cada ventana. La representación usada para ese hash
es JSON determinista de Python con NaN para ausencia; es una huella interna, no un
archivo de intercambio. Los recibos y sus cortes se guardan por separado.

Los parámetros `training_start`/`training_end` describen el calendario común de
historia elegible ML; en el baseline, `training_rows=0` y los recibos indican su
referencia efectiva de siete días. No se ajusta un modelo con ocho semanas para
obtener el baseline.

Los resultados agregados se guardan en otros tres runs, uno por modelo:

- `mae = suma de errores absolutos / número total de observaciones`.
- `wape = suma de errores absolutos / suma total de ventas reales`.
- `mae_mean`, `wape_mean`: medias de las métricas de las cuatro ventanas.
- `mae_std`, `wape_std`: desviaciones estándar poblacionales, `ddof=0`.

WAPE se registra como fracción; multiplicar por 100 para porcentaje. El WAPE global
no es la media simple de los cuatro WAPE. Si una ventana no tiene ventas reales
positivas, su WAPE es indefinido y no entra en la media; se registra la cantidad de
ventanas con WAPE definido. El agregado conserva el error de todas las observaciones.

Los quince runs comparten el parámetro `walk_forward_id` en el experimento
`corporacion_favorita-walk-forward`. Los doce runs de ventana además tienen la misma
etiqueta. Los agregados registran `run_role=aggregate` como parámetro; `windows.csv`
contiene los enlaces por ID a los runs originales. Son runs independientes, no runs
anidados, para reutilizar el contexto de entrenamiento sin alterar otros runs activos.

## Ejecución y alcance

```bash
.venv/bin/python -m reposicion.walk_forward \
  --config configs/walk_forward.yaml \
  --output reports/walk_forward/january_2017 \
  --tracking-uri http://localhost:5011
```

Para repetir, elegir una nueva carpeta: se rechazan salidas existentes. Los resultados
previos se conservan y los artefactos siguen ignorados por Git. La lógica y semillas
son reproducibles; cada ejecución recibe nuevos IDs de tracking y tiempos reales.
No se reutilizan modelos ajustados en otros cortes. No se crean nuevas versiones de
Registry para estos ajustes de validación ni se asignan aliases, stages o Champion.
No se modifican Airflow, DVC, originales ni entregas simuladas.

Las pruebas incluyen un recorrido sintético de los cuatro cortes que verifica ocho
instancias entrenadas distintas, revisiones por disponibilidad y comparación pareada.
También prueban ventanas superpuestas, agregación ponderada, WAPE indefinido y rechazo
de observaciones repetidas. La selección o promoción de un modelo queda pendiente
de autorización; comparar errores no constituye elegir Champion.

## Resultados de la ejecución real

Grupo de ejecución: `107d7f6f8961472b8fdf46647ed4f224`. Experimento **3**: [MLflow walk-forward](http://localhost:5011/#/experiments/3).

| Corte | Modelo | MAE | WAPE | Run |
|---|---|---:|---:|---|
| 2017-01-08 | Baseline semanal | 230,355 | 48,544 % | [Ver](http://localhost:5011/#/experiments/3/runs/512cabbfd5f243389141b8d773a3bf5b) |
| 2017-01-08 | Random Forest | 191,136 | 40,279 % | [Ver](http://localhost:5011/#/experiments/3/runs/a13360d320b14295986e29b57fa7cace) |
| 2017-01-08 | HistGradientBoosting | 207,909 | 43,814 % | [Ver](http://localhost:5011/#/experiments/3/runs/298981cde4e346529aefe7478f14d940) |
| 2017-01-15 | Baseline semanal | 53,426 | 11,221 % | [Ver](http://localhost:5011/#/experiments/3/runs/087e5260dc17444aa89f77eb9af62015) |
| 2017-01-15 | Random Forest | 98,815 | 20,754 % | [Ver](http://localhost:5011/#/experiments/3/runs/3bf1259a8cfe4412a3dfafa6acadc334) |
| 2017-01-15 | HistGradientBoosting | 94,958 | 19,944 % | [Ver](http://localhost:5011/#/experiments/3/runs/057257ece9184fb9b0ee04b802269d6b) |
| 2017-01-22 | Baseline semanal | 54,222 | 11,890 % | [Ver](http://localhost:5011/#/experiments/3/runs/2ebd78ecf0e74a84aefddef17e24b0a3) |
| 2017-01-22 | Random Forest | 82,230 | 18,032 % | [Ver](http://localhost:5011/#/experiments/3/runs/15ac4b72a8de40fb9eb5aa655005a36f) |
| 2017-01-22 | HistGradientBoosting | 113,305 | 24,846 % | [Ver](http://localhost:5011/#/experiments/3/runs/be8ad88a80e748568d47151edf873855) |
| 2017-01-29 | Baseline semanal | 90,305 | 18,082 % | [Ver](http://localhost:5011/#/experiments/3/runs/08cedc86fe774751acbac2256de617aa) |
| 2017-01-29 | Random Forest | 77,760 | 15,570 % | [Ver](http://localhost:5011/#/experiments/3/runs/0aaddac318ab4f2cbd8325915e07ed0e) |
| 2017-01-29 | HistGradientBoosting | 107,744 | 21,574 % | [Ver](http://localhost:5011/#/experiments/3/runs/4fc4eb64de7b44bf8d17192d5f283664) |

Agregados micro sobre **49.896 observaciones por modelo**:

| Modelo | MAE global | WAPE global | MAE medio ± desvío | WAPE medio ± desvío (puntos porcentuales) | Run |
|---|---:|---:|---:|---:|---|
| Baseline semanal | 107,077 | 22,471 % | 107,077 ± 72,717 | 22,434 ± 15,310 | [Ver](http://localhost:5011/#/experiments/3/runs/395c3b06d182491da65282389d6969e4) |
| Random Forest | 112,485 | 23,606 % | 112,485 ± 46,082 | 23,659 ± 9,769 | [Ver](http://localhost:5011/#/experiments/3/runs/6e80b010dd9b487d9c20655faee3a170) |
| HistGradientBoosting | 130,979 | 27,487 % | 130,979 ± 44,911 | 27,545 ± 9,558 | [Ver](http://localhost:5011/#/experiments/3/runs/0f53c1af6d884bf784c80d926a872b50) |

Las ventas reales agregadas suman 23.776.388,838131398 en cada modelo. Los quince runs finalizaron correctamente. El orden de errores del agregado difiere del primer corte; se informa la comparación sin seleccionar Champion.

Verificación final: los quince runs están en `FINISHED` y sus métricas coinciden con
los archivos locales. Los ocho entrenamientos ML tienen historiales de CPU/RAM y
duración. Se descargaron los **116 artefactos** y todos conservaron SHA-256 idéntico.
Los tres runs anteriores y el inventario de versiones/aliases de Registry coinciden
con el estado previo. La suite completa aprueba **142 pruebas**; Ruff y formato
correctos, y auditoría de publicación sin datos/artefactos sensibles en Git.
