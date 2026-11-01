# Motor independiente de pedidos sugeridos

`reposicion.orders` consume `forecast_quantiles.csv` y `lineage.json` existentes.
No carga modelos ni vuelve a pronosticar. Su integración en el DAG existente se
documenta en [pedidos en Airflow](pedidos_en_airflow.md).
Puede leer el directorio de una publicación con manifiesto (verifica checksums)
o el directorio de los pronósticos previamente generados en reports.

```bash
.venv/bin/python -m reposicion.orders \
  --forecast-dir reports/uncertainty/2017-03-05-v2 \
  --costs configs/costs.yaml \
  --output-root reports/orders
.venv/bin/pytest -q tests/test_orders.py
```

## Configuración y supuestos explícitos

Los valores de `configs/costs.yaml` son **ilustrativos, no costos/inventarios
observados de Corporación Favorita**. Los cinco CSV no contienen existencias.

- Faltante: 5 unidades monetarias por unidad de venta perdida.
- Merma: 1 unidad monetaria por unidad remanente al final del horizonte.
- Horizonte: siete fechas desde el origen del pronóstico, incluyendo el plazo.
- Plazo: dos días; el pedido llega al inicio del tercer día y cubre los días 3–7.
- Existencia inicial y entradas ya comprometidas: cero por defecto, asumidos
  conocidos al corte. `inventory.per_series` permite fijarlos por tienda/familia.
- Las entradas comprometidas llegan junto con el nuevo pedido. No hay otras
  recepciones, restricciones de capacidad, costos fijos, salvamento o entregas.
- Las ventas anteriores a la llegada que no cubra el inventario inicial se pierden;
  no son backorders ni se recuperan con el pedido. Se reportan separadamente.
- Todo remanente del día siete se considera merma. Esa fracción es un supuesto
  fijo de esta política; valores distintos de 1 se rechazan, no se ignoran.
- Cantidades continuas por defecto: las ventas no necesariamente son enteras.
  `quantity_step > 0` permite múltiplos de empaque, comparando costos de los dos
  múltiplos que rodean el óptimo continuo, sin redondear siempre hacia arriba.

Los costos son marginales y deben compartir unidad monetaria por unidad de venta;
no hay un costo de compra adicional en la función objetivo. Se validan como
positivos y finitos. No se confunden valores faltantes con costos/inventarios cero.
Se rechazan configuraciones inválidas, inventarios duplicados/desconocidos, plazos
fuera de 0–6 y series sin siete fechas únicas completas.

Un horizonte de siete días **posterior a la llegada**, con plazo de dos días,
requeriría nueve días de pronósticos. Este motor no inventa esos dos días extra:
su horizonte termina siempre en origin + 6. La columna days_covered_after_arrival
expone los cinco días cubiertos por el pedido con la configuración inicial.

## Distribución acumulada coherente

Tres cuantiles marginales no identifican una distribución conjunta. Se fijan los
siguientes supuestos externos y versionados, sin estimarlos con ventas futuras:

1. Inversa marginal diaria lineal por tramos en probabilidades 0, .1, .5, .9 y 1.
   Los tres puntos interiores son exactamente P10/P50/P90. Los extremos son
   max(0, P10 - 2*(P50-P10)) y P90 + 2*(P90-P50). El factor de cola es configurable.
   Las marginales son no negativas y monótonas, incluyendo masas en cero.
2. Cópula gaussiana con correlación latente común entre días, por defecto 0.35.
   Es un supuesto de dependencia, no una correlación estimada o identificada por
   los tres cuantiles. No equivale necesariamente a la correlación Pearson de ventas.
3. Se generan 8.192 escenarios de siete días con PCG64, semilla estable SHA-256
   por origen/tienda/familia y semilla base 42, usando pares antitéticos.
4. Se suman las demandas dentro de cada escenario. P10/P50/P90 acumulados se
   calculan sobre esas sumas; **nunca se suman los cuantiles diarios**.

Costos e inventarios no intervienen en la semilla. Comparar costos conserva los
mismos escenarios y cuantiles de demanda, aislando el efecto económico. Son
resultados Monte Carlo bajo supuestos explícitos, sin garantía de cobertura real.

## Decisión económica e inventario durante el plazo

Para cada escenario, sea B la demanda antes de la llegada, A la demanda desde la
llegada hasta el final, H el inventario inicial e I las entradas comprometidas:

- Existencia disponible al llegar = max(H - B, 0) + I.
- Demanda neta X = A - existencia disponible al llegar.
- Ventas perdidas antes de llegada = max(B - H, 0), independientes de la cantidad nueva.

Con Cu=faltante y Cm=merma, el fractil crítico es Cu/(Cu+Cm). El pedido continuo
es max(0, cuantil empírico de X en ese fractil). Se usa `inverted_cdf`, que da un
minimizador del costo lineal empírico. La función objetivo incluye:

Cu * E[ventas perdidas antes de llegada + max(X-Q,0)] + Cm * E[max(Q-X,0)].

Así se evita descontar dos veces el inventario consumido antes de la llegada o
tratar las ventas perdidas como un pedido pendiente. La salida incluye costos
esperados, faltante previo inevitable, merma esperada y cuantiles de demanda total.
No se agregan cantidades entre familias con unidades potencialmente diferentes.

## Publicación, trazabilidad e idempotencia

Cada tienda/familia genera una fila en `suggested_orders.csv`. La publicación
contiene también costs.yaml, lineage.json y manifest.json. El linaje conserva
el run/modelo/DVC del pronóstico original, hashes de entradas, configuración completa,
semilla, método y versiones Python/NumPy/SciPy. No se leen ventas reales futuras.

Se reutiliza el publicador atómico existente con lock y hashes. La identidad
incluye **costs_sha256**: cambiar la configuración produce otra versión, sin
sobrescribir recomendaciones anteriores. Repetir la misma ejecución reutiliza
el resultado verificado. El destino debe estar separado del origen de pronósticos.
No se modifican CSV originales, pronósticos, modelos, DVC, Git ni Airflow.

## Pruebas y demostración con los datos existentes

Nueve pruebas sin entrenamiento cubren: sensibilidad cambiando solo costos,
escenarios comunes, acumulación distinta a sumar P90 diarios, efecto de dependencia,
inventario/plazo/entradas y ventas perdidas, cantidades fraccionarias/múltiplos,
validación, ausencia de fechas e idempotencia con preservación de históricos.

Se procesaron los 12.474 pronósticos existentes (5–11 marzo 2017), obteniendo
**1.782 pedidos**. Con plazo dos, la recepción es el 7 de marzo. Se cambió únicamente
merma de **1 a 5**, conservando faltante=5, inventario, pronósticos y simulación:

| Ejemplo | Merma 1 | Merma 5 |
|---|---:|---:|
| Tienda 1, AUTOMOTIVE: pedido | 30.650866 | 16.207156 |
| Fractil crítico | 0.833333 | 0.500000 |

Las 1.782 recomendaciones disminuyeron en esta muestra. Los cuantiles acumulados
quedaron exactamente iguales y el CSV de pronósticos conservó su SHA-256. En general,
una serie determinista, sin demanda o con inventario suficiente puede mantener el
mismo pedido al cambiar costos: no se fuerza una diferencia artificial.

Publicaciones:

- Base: reports/orders/84d211420fd506085ae5176219645db33640079faabdb875111841b83f95fb30/.
- Merma 5: reports/orders/f50801688cb13f2c5799c6da49f424869479c4be36babb8c133d2a226a2c69f7/.
- Configuración alternativa e informe: reports/orders_sensitivity/.

Estos resultados permanecen ignorados por Git; no se realizaron operaciones Git.
