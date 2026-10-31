# Variables temporales v2

Se añade `src/reposicion/temporal_features.py` y una entrada de ejecución
`python -m reposicion.temporal_walk_forward`. El runner común admite extensiones
opcionales: la ruta original sigue disponible para reproducir los experimentos v1.
El código del baseline y los hiperparámetros de ambos estimadores se conservan.

## Calendario conocido, con alcance geográfico

Cada origen histórico de entrenamiento y cada origen de pronóstico selecciona
primero los recibos con `available_at <= as_of`, usando su última revisión.
Solo entonces se leen las entregas `holidays_events` y `stores`. La ubicación
conocida de la tienda determina la aplicación de eventos:

- National: todas las tiendas de la fuente ecuatoriana.
- Regional: coincidencia de `locale_name` con `stores.state`.
- Local: coincidencia de `locale_name` con `stores.city`.

Para el objetivo y para cada rezago 7/14/21/28 se agregan indicadores de feriado
activo y su alcance, fecha trasladada, Work Day y Event conocido. El indicador
`exceptional` señala cualquier registro de calendario aplicable conocido, incluidos
los nominales trasladados. No implica necesariamente cierre de tienda.

Holiday, Transfer, Additional y Bridge son feriados activos cuando `transferred`
es falso. Una fecha nominal con `transferred=True` conserva su indicador de fecha
excepcional, pero no se declara feriado activo. Esto distingue el 1 de enero de
2017 y su traslado al 2 de enero según la fuente. Work Day no se trata como día libre.

Una referencia futura puede usarse si el feriado ya estaba publicado; un Event
conocido después del corte queda excluido. La simulación existente entrega un
archivo por fecha: si mezcla eventos planificados e inesperados, todo ese recibo
puede quedar demorado. Se respeta esa política, sin reconstruir un calendario
anticipado desde los originales. La ausencia de un registro significa **ningún
evento conocido**, no garantiza que el día sea ordinario ni que el calendario esté
completo. Una tienda sin ubicación conocida produce error.

## Rezagos y escala de imputación

Se conservan los rezagos originales y sus indicadores de ausencia. Se agregan
indicadores de cero observado y contexto excepcional. Un cero observado conserva
su valor, incluso en fechas excepcionales; los archivos de ventas no se alteran.

Se calculan además dos variables históricas por tienda/familia:

- `normal_weekday_median` y su conteo: mediana de los rezagos semanales disponibles
  del mismo día de semana sin eventos aplicables conocidos.
- `recent_normal_mean` y su conteo: promedio de observaciones de la semana anterior
  al origen, excluyendo fechas con eventos aplicables conocidos.

Son representaciones adicionales; no eliminan ni sustituyen las ventas observadas
excepcionales. Todas sus fechas de venta preceden al origen y su calendario respeta
lo conocido entonces. Se mantienen también las variables originales para permitir
que el estimador aprenda cómo utilizar cada señal.

Se elimina SimpleImputer global **en la variante v2**. `SeriesFamilyImputer` trabaja
antes de codificar categorías y solo rellena valores ausentes:

1. Para un rezago ausente, usa la mediana comparable disponible de esa misma serie
   en la fila, calculada exclusivamente con historia conocida al origen.
2. Si no existe, usa la mediana de la columna de esa tienda/familia aprendida en el
   entrenamiento del corte.
3. Si la serie carece de estadística, utiliza la mediana de la misma familia ajustada
   en entrenamiento. Nunca toma valores de otra familia ni una mediana global.
4. Sin ninguna referencia válida, aborta explícitamente.

Los rezagos de fechas excepcionales conocidas no alimentan las medianas de relleno.
La transformación conserva los indicadores originales de ausencia y no cambia los
ceros observados. Los estadísticos ajustados usan únicamente las filas del conjunto
de entrenamiento del corte; no se recalculan con validación ni con sus ventas reales.

## Comparación controlada

Se reutiliza `configs/walk_forward.yaml` sin cambios: cortes 8, 15, 22 y 29 de enero
de 2017 a las 12Z, horizonte siete, ocho semanas móviles y verdad al origen +33 días.
No se amplía la historia ni se cambia la pérdida, profundidad, número de árboles,
iteraciones, semilla u otro hiperparámetro del estimador. Cada modelo se ajusta de
nuevo en cada corte con las mismas 98.010 etiquetas y las mismas claves de evaluación.

Antes de publicar cada baseline nuevo, se exige igualdad exacta de predicciones y
evaluación con `reports/walk_forward/january_2017`. Es un run de referencia nuevo,
no una modificación del baseline anterior. Ambos modelos ML comparten la huella del
nuevo conjunto de variables. La trazabilidad incluye todos los recibos de calendario
y ubicación y el `as_of` de cada contexto, junto con los recibos de ventas.

```bash
.venv/bin/python -m reposicion.temporal_walk_forward \
  --previous reports/walk_forward/january_2017 \
  --output reports/walk_forward/temporal_v2_january_2017 \
  --tracking-uri http://localhost:5011
```

La salida debe ser nueva. Los runs se crean en el experimento independiente
`corporacion_favorita-walk-forward-temporal-v2`, con doce runs de ventana y tres
agregados. Se mantienen MAE, WAPE, métricas macro/micro, System Metrics, duración,
predicciones, modelos, gráficas y recibos/checksums. Los artefactos permanecen fuera
de Git. No se sobrescriben resultados previos ni se crean aliases o nuevas versiones
de Registry para estos ajustes de validación. Airflow, DVC y originales no cambian.

## Pruebas

Se verifican alcance nacional/regional/local, traslado, publicación anticipada de
feriados y exclusión de eventos aún no disponibles. Otras pruebas distinguen cero,
ausencia y excepción; comprueban escalas de familias muy distintas y rechazo de una
familia sin historia. Se comparan todos los hiperparámetros con los estimadores v1.
El recorrido sintético de los cuatro cortes se ejecuta tanto en v1 como en v2,
verificando disponibilidad de todos los recibos y ocho instancias ajustadas nuevas.
La suite completa aprueba 149 pruebas; Ruff y formato pasan.

## Resultados de los cuatro cortes

Experimento **4**, [MLflow temporal v2](http://localhost:5011/#/experiments/4), grupo `38f20499009a405da5231d65382aed8d`.

| Modelo | MAE v1 | MAE v2 | WAPE v1 | WAPE v2 | Run agregado v2 |
|---|---:|---:|---:|---:|---|
| Baseline semanal | 107,077 | 107,077 | 22,471 % | 22,471 % | [Ver](http://localhost:5011/#/experiments/4/runs/86b0765299de456fbce9e28ea144e99a) |
| Random Forest | 112,485 | 90,563 | 23,606 % | 19,005 % | [Ver](http://localhost:5011/#/experiments/4/runs/517dc691cef148ae8959e73e9419cded) |
| HistGradientBoosting | 130,979 | 102,022 | 27,487 % | 21,410 % | [Ver](http://localhost:5011/#/experiments/4/runs/930b74f64c4a4331a5286de6c5e46802) |

Cada modelo mantiene **49.896 observaciones**, 12.474 por ventana. El WAPE global usa sumas de errores y ventas, no promedios de porcentajes.

| Corte | Modelo | MAE v2 | WAPE v2 | Run |
|---|---|---:|---:|---|
| 2017-01-08 | Baseline semanal | 230,355 | 48,544 % | [Ver](http://localhost:5011/#/experiments/4/runs/766463a1cb3049afbb83374638ca7984) |
| 2017-01-08 | Random Forest | 135,404 | 28,535 % | [Ver](http://localhost:5011/#/experiments/4/runs/345119eb3dd14096b45747d504612b6f) |
| 2017-01-08 | HistGradientBoosting | 168,461 | 35,501 % | [Ver](http://localhost:5011/#/experiments/4/runs/9f9464790529419b80d6a6cad8929c87) |
| 2017-01-15 | Baseline semanal | 53,426 | 11,221 % | [Ver](http://localhost:5011/#/experiments/4/runs/d7c4055fff6947d5ac03935b96dae826) |
| 2017-01-15 | Random Forest | 97,319 | 20,440 % | [Ver](http://localhost:5011/#/experiments/4/runs/1c6e44ce790f4a67b24beaae71c6b507) |
| 2017-01-15 | HistGradientBoosting | 91,388 | 19,194 % | [Ver](http://localhost:5011/#/experiments/4/runs/e2030b1ae9d94dd7a619deb870ca2aaf) |
| 2017-01-22 | Baseline semanal | 54,222 | 11,890 % | [Ver](http://localhost:5011/#/experiments/4/runs/d299b02215334d1cb44c84cbd238bb1a) |
| 2017-01-22 | Random Forest | 51,709 | 11,339 % | [Ver](http://localhost:5011/#/experiments/4/runs/6ac0c9215b2c4585b19c5849bc6a97d6) |
| 2017-01-22 | HistGradientBoosting | 60,358 | 13,236 % | [Ver](http://localhost:5011/#/experiments/4/runs/3c40f95ebea24dab9d2a54163d5b32e8) |
| 2017-01-29 | Baseline semanal | 90,305 | 18,082 % | [Ver](http://localhost:5011/#/experiments/4/runs/7c8ff79900d54b1ebc68ff1ffdf71e05) |
| 2017-01-29 | Random Forest | 77,818 | 15,582 % | [Ver](http://localhost:5011/#/experiments/4/runs/f6062df6a53549a79125fd208aab381d) |
| 2017-01-29 | HistGradientBoosting | 87,883 | 17,597 % | [Ver](http://localhost:5011/#/experiments/4/runs/3b04fbd56a374f28aa7d0965d6778885) |

RF reduce su error agregado un 19,489 % relativo respecto a v1; HGB un 22,108 %. Ambos superan al baseline en el agregado, pero no en todas las ventanas.

Este experimento mide el paquete conjunto de calendario, indicadores, referencias robustas e imputación; no identifica el aporte separado de cada cambio. Los cuatro cortes ya se inspeccionaron para diseñar las variables: constituyen una comparación de desarrollo, no una evaluación final independiente. Se mantiene disponibilidad temporal correcta, y queda pendiente confirmar generalización en otro período. No se selecciona Champion.

Verificación final: quince runs en FINISHED y métricas idénticas a sus archivos
locales; System Metrics en los ocho entrenamientos ML. Se comprobaron **72 contextos
de calendario** sin recibos publicados después de su corte y **116 artefactos**
descargados con SHA-256 idénticos. Los ocho estimadores guardados conservan todos
los hiperparámetros de v1. Los 18 runs anteriores, Registry y el código del baseline
mantienen su estado previo; las predicciones/reales del baseline son idénticos byte
a byte en las cuatro ventanas. La auditoría de publicación pasa.
