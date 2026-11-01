# Pronósticos y pedidos: confirmación conjunta en Airflow

Solo se modifica `lab1_pronostico_reposicion`. Conserva el cron semanal, zona
Guatemala, sensor de snapshot confirmado, fechas de corte y backfill.

```text
esperar_snapshot → generar_publicacion → calcular_pedidos → confirmar_publicacion
```

`calcular_pedidos` llama al motor existente `reposicion.orders`, sin cambiar su
algoritmo ni cargar modelos. Consume el bundle generado por la tarea anterior y
`/opt/lab1/forecast_project/configs/costs.yaml`, copia de `configs/costs.yaml` en la
imagen. No vuelve a pronosticar para calcular pedidos. Se conservan los supuestos
ilustrativos del motor: [distribución, costos, plazo e inventario](motor_pedidos.md).

## Punto de confirmación

Los pronósticos y pedidos tienen publicaciones intermedias inmutables independientes.
Solo la última tarea puede emitir el Asset `lab1.pronosticos_publicados`.
Antes de emitirlo, `reposicion.replenishment_publication` verifica:

- Checksums e identidades de ambos bundles.
- Que los pedidos se calcularon para el CSV y linaje exactos del pronóstico.
- Que la copia de costos coincide con su SHA-256 y con los supuestos registrados.
- Que existe un pedido válido por cada tienda/familia del pronóstico, sin duplicados,
  cantidades negativas/no finitas, diferencias de costos o períodos incompatibles.

Después publica atómicamente un paquete completo con cinco archivos:
`forecast_quantiles.csv`, `suggested_orders.csv`, `costs.yaml`, `lineage.json` y
`manifest.json`. El linaje conserva ambos linajes originales, modelo/run/DVC,
versión de costos por contenido y supuestos completos de inventario.

`costs_schema_version` identifica el formato; **costs_version es el SHA-256 del
YAML realmente utilizado**, no un número de versión inventado. El hash de los
supuestos de inventario también se incluye en la identidad y en el evento Asset.
El YAML archivado permite reconstruir precios, existencias, entradas, plazo y
configuración de escenarios, sin depender del archivo vigente en una ejecución futura.

Si falla el motor de pedidos o la comprobación conjunta, no hay confirmación ni
Asset, por la dependencia `all_success`. Puede quedar un pronóstico intermedio
válido para recuperar la ejecución, pero eso no lo convierte en paquete completo.
El seguimiento existente solo autoriza nuevas publicaciones confirmadas mediante
Assets, por lo que tampoco consume ese intermediario como una publicación nueva.
Las publicaciones históricas anteriores continúan vigentes.

## Persistencia e idempotencia

En el volumen `lab1_operational`:

- `forecasts/<forecast_id>/`: pronósticos intermedios existentes.
- `orders/<orders_id>/`: pedidos y costos capturados por el motor.
- `replenishment/<complete_id>/`: paquete completo confirmado.

La identidad conjunta incluye IDs y checksums de ambas publicaciones, costos,
inventario y código de confirmación. Un cambio de costos genera otra versión de
pedidos/paquete; un reintento sin cambios reutiliza todo, sin sobrescribir archivos.
Los Assets pueden volver a notificar una publicación válida y el seguimiento
conserva su deduplicación existente. El evento mantiene el ID/hash del pronóstico
original para compatibilidad, y agrega complete_publication_id, complete_path,
complete_manifest_sha256, orders_publication_id, costs_version y hash de inventario.
No se modifica el DAG de seguimiento ni el de ingesta.

## Backfill y costos archivados

El caso habitual usa `configs/costs.yaml` de la imagen. Para fijar una política
histórica puede indicarse `costs_path` absoluto bajo el directorio de configuración
o `/opt/lab1/operational/costs`. No se permiten rutas a otros proyectos.
`LAB1_COSTS_CONFIG` también permite fijar el archivo si se configura en el entorno
Airflow. El paquete final siempre utiliza la copia capturada por los pedidos,
sin releer una configuración cambiante durante la confirmación.

```bash
docker exec lab1-airflow-scheduler-1 airflow dags trigger lab1_pronostico_reposicion \
  --run-id MI_BACKFILL_CON_PEDIDOS_UNICO \
  --conf '{"origin":"2017-03-05","issued_at":"2017-03-05T12:00:00Z","snapshot_id":"645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0","model_version":"4"}'
```

## Prueba real de extremo a extremo

| Run | Resultado |
|---|---|
| pedidos_fallo_controlado | failed esperado: configuración inexistente; cero paquetes completos y cero Assets |
| pedidos_historico_20170305 | success en sus cuatro tareas |
| pedidos_historico_20170305_reintento | success; pronósticos, pedidos y paquete completo reutilizados |

Resultados: **12.474 pronósticos**, **1.782 pedidos**, 5–11 marzo 2017, Champion v4
existente, llegada 7 marzo bajo plazo dos. Se mantuvo una sola publicación de
pedidos y un solo paquete completo tras el reintento.

- Pronósticos: d9f2d73162c63547301928f740166a5ce5cebd2d1e70c4f397d444d1bec58676.
- Pedidos: 987482f0318cac1b349aaa2cd1cab009cc3635a0b3dd1adc90d25b800c3f00a5.
- Paquete: 1d278a9eafe88cb59fc2e01e77f2723cce7defc403dd56f2b72ef940554f3fd1.
- Costos: 01fc45e5271ef243c47a73cca65e69fbf9b55baa23439a87f07917d6d24760bb.
- Inventario: f0be0567bc2f9ef1d3285445c0d97aaac4ea8acd259bf974f985ea61065720b8.
- Modelo/run original: f6062df6a53549a79125fd208aab381d, sin reentrenamiento.

Copia local para revisión, ignorada por Git:
`reports/replenishment/1d278a9eafe88cb59fc2e01e77f2723cce7defc403dd56f2b72ef940554f3fd1/`.
Informe resumido: `reports/replenishment/e2e.json`.

Catorce pruebas específicas aprobaron, incluidas sensibilidad de costos del motor,
idempotencia conjunta, trazabilidad, órdenes ausentes/incompletas y pedidos ligados
a otro pronóstico. Ruff/formato e importación de Airflow correctos. Los otros dos
DAGs y los motores de pronóstico/pedidos/seguimiento conservaron sus hashes.
No se realizaron operaciones Git ni cambios DVC/modelos. El fallo controlado queda
como evidencia, no se borra el historial. Se recrearon solo procesos Airflow para
aplicar la imagen; PostgreSQL/MLflow y volúmenes permanecen sin recrear.
